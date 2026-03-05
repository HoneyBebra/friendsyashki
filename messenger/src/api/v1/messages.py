import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.dependencies.auth import get_current_user_id
from src.exceptions.dialogs import AuthServiceUnavailableError
from src.exceptions.messages import (
    ClientMessageIdConflictError,
    DialogNotFoundError,
    NotDialogParticipantError,
)
from src.gRPC.client import get_login_by_user_id
from src.models.messages import Message
from src.repositories.dialogs import DialogsRepository
from src.repositories.messages import MessagesRepository
from src.schemas.v1.messages import MessageResponse, MessagesListResponse, SendMessageRequest
from src.services.messages import MessagesService
from src.ws.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dialogs", tags=["messages"])


def get_messages_service(
    messages_repository: MessagesRepository = Depends(),
    dialogs_repository: DialogsRepository = Depends(),
) -> MessagesService:
    return MessagesService(
        messages_repository=messages_repository,
        dialogs_repository=dialogs_repository,
    )


async def _message_to_response(message: Message) -> MessageResponse:
    try:
        sender_login = await get_login_by_user_id(message.sender_id)
    except ValueError:
        raise AuthServiceUnavailableError from None
    return MessageResponse(
        id=message.id,
        dialog_id=message.dialog_id,
        sender_login=sender_login,
        text=message.text,
        client_message_id=message.client_message_id,
        created_at=message.created_at,
    )


@router.get(
    "/{dialog_id}/messages",
    response_model=MessagesListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_messages(
    dialog_id: UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0, le=10000),
    current_user_id: UUID = Depends(get_current_user_id),
    service: MessagesService = Depends(get_messages_service),
) -> MessagesListResponse:
    try:
        messages = await service.get_messages(
            dialog_id=dialog_id,
            user_id=current_user_id,
            limit=limit,
            offset=offset,
        )
    except DialogNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except NotDialogParticipantError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant of this dialog",
        ) from exc
    except AuthServiceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    return MessagesListResponse(
        messages=[await _message_to_response(m) for m in messages],
    )


@router.post(
    "/{dialog_id}/messages",
    response_model=MessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_message(
    dialog_id: UUID,
    body: SendMessageRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    service: MessagesService = Depends(get_messages_service),
) -> MessageResponse:
    try:
        message, participant_ids = await service.send_message(
            dialog_id=dialog_id,
            sender_id=current_user_id,
            text=body.text,
            client_message_id=body.client_message_id,
        )
    except DialogNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except NotDialogParticipantError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant of this dialog",
        ) from exc
    except ClientMessageIdConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except AuthServiceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    response = await _message_to_response(message)
    await ws_manager.broadcast_to_users(
        participant_ids,
        {"event": "new_message", "payload": response.model_dump(mode="json")},
    )
    connected_ids = ws_manager.get_connected_user_ids(participant_ids)
    for user_id in connected_ids:
        if user_id != current_user_id:
            try:
                await service.messages_repository.set_delivered_if_sent(
                    message.id, user_id
                )
            except Exception as e:
                logger.warning(
                    "Failed to set delivered for message_id=%s user_id=%s: %s",
                    message.id,
                    user_id,
                    e,
                )
    return response
