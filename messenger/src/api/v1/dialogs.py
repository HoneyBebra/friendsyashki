from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.dependencies.auth import get_current_user_id
from src.exceptions.dialogs import AuthServiceUnavailableError, SelfDialogError, UserNotFoundError
from src.gRPC.client import get_login_by_user_id
from src.models.dialogs import Dialog
from src.repositories.dialogs import DialogsRepository
from src.schemas.v1.dialogs import (
    CreateDirectDialogRequest,
    DialogResponse,
    DialogsListResponse,
    ParticipantResponse,
)
from src.services.dialogs import DialogsService
from src.ws.manager import ws_manager

router = APIRouter(prefix="/dialogs", tags=["dialogs"])


def get_dialogs_service(
    dialogs_repository: DialogsRepository = Depends(),
) -> DialogsService:
    return DialogsService(dialogs_repository=dialogs_repository)


async def _dialog_to_response(dialog: Dialog) -> DialogResponse:
    participants_resp = []
    for p in dialog.participants:
        try:
            login = await get_login_by_user_id(p.user_id)
        except ValueError:
            raise AuthServiceUnavailableError from None
        participants_resp.append(
            ParticipantResponse(login=login, joined_at=p.joined_at),
        )
    return DialogResponse(
        id=dialog.id,
        type=dialog.type.value,
        title=dialog.title,
        participants=participants_resp,
        created_at=dialog.created_at,
    )


@router.get(
    "",
    response_model=DialogsListResponse,
    status_code=status.HTTP_200_OK,
)
async def get_dialogs(
    current_user_id: UUID = Depends(get_current_user_id),
    service: DialogsService = Depends(get_dialogs_service),
) -> DialogsListResponse:
    dialogs = await service.get_user_dialogs(current_user_id)
    return DialogsListResponse(
        dialogs=[await _dialog_to_response(d) for d in dialogs],
    )


@router.post(
    "/direct",
    response_model=DialogResponse,
    status_code=status.HTTP_200_OK,
)
async def create_or_get_direct_dialog(
    body: CreateDirectDialogRequest,
    current_user_id: UUID = Depends(get_current_user_id),
    service: DialogsService = Depends(get_dialogs_service),
) -> DialogResponse:
    try:
        dialog = await service.create_or_get_direct(
            current_user_id=current_user_id,
            target_login=body.target_login,
        )
    except SelfDialogError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot create a dialog with yourself",
        ) from exc
    except UserNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except AuthServiceUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable",
        ) from exc

    response = await _dialog_to_response(dialog)
    participant_ids = [p.user_id for p in dialog.participants]
    await ws_manager.broadcast_to_users(
        participant_ids,
        {"event": "new_dialog", "payload": response.model_dump(mode="json")},
    )
    return response
