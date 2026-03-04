from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from src.dependencies.auth import get_current_user_id
from src.exceptions.dialogs import AuthServiceUnavailableError, SelfDialogError, UserNotFoundError
from src.repositories.dialogs import DialogsRepository
from src.schemas.v1.dialogs import CreateDirectDialogRequest, DialogResponse, ParticipantResponse
from src.services.dialogs import DialogsService

router = APIRouter(prefix="/dialogs", tags=["dialogs"])


def get_dialogs_service(
    dialogs_repository: DialogsRepository = Depends(),
) -> DialogsService:
    return DialogsService(dialogs_repository=dialogs_repository)


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

    return DialogResponse(
        id=dialog.id,
        type=dialog.type.value,
        title=dialog.title,
        participants=[
            ParticipantResponse(
                user_id=p.user_id,
                joined_at=p.joined_at,
            )
            for p in dialog.participants
        ],
        created_at=dialog.created_at,
    )
