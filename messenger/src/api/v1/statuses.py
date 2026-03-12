import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.dependencies.auth import get_current_user_id
from src.exceptions.messages import MessageNotFoundError, NotDialogParticipantError
from src.repositories.dialogs import DialogsRepository
from src.repositories.messages import MessagesRepository
from src.schemas.v1.messages import MessageReadResponse
from src.services.messages import MessagesService
from src.ws.manager import ws_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/messages", tags=["statuses"])


def get_messages_service(
    messages_repository: MessagesRepository = Depends(),
    dialogs_repository: DialogsRepository = Depends(),
) -> MessagesService:
    return MessagesService(
        messages_repository=messages_repository,
        dialogs_repository=dialogs_repository,
    )


@router.post(
    "/{message_id}/read",
    response_model=MessageReadResponse,
    status_code=status.HTTP_200_OK,
)
async def mark_message_read(
    message_id: UUID,
    current_user_id: UUID = Depends(get_current_user_id),
    service: MessagesService = Depends(get_messages_service),
) -> MessageReadResponse:
    try:
        msg_status, participant_ids = await service.mark_as_read(
            message_id=message_id,
            user_id=current_user_id,
        )
    except MessageNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except NotDialogParticipantError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant of this dialog",
        ) from exc

    if msg_status is not None:
        await ws_manager.broadcast_to_users(
            participant_ids,
            {
                "event": "message_read",
                "payload": {
                    "message_id": str(message_id),
                    "user_id": str(current_user_id),
                    "status": "read",
                },
            },
        )

    return MessageReadResponse(
        message_id=message_id,
        status="read",
    )
