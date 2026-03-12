from uuid import UUID

import grpc  # type: ignore[import-untyped]

from src.exceptions.dialogs import AuthServiceUnavailableError, SelfDialogError, UserNotFoundError
from src.gRPC.client import get_user_id_by_login
from src.models.dialogs import Dialog
from src.repositories.dialogs import DialogsRepository


class DialogsService:
    def __init__(self, dialogs_repository: DialogsRepository) -> None:
        self.dialogs_repository = dialogs_repository

    async def get_user_dialogs(self, user_id: UUID) -> list[Dialog]:
        return await self.dialogs_repository.get_user_dialogs(user_id)

    async def get_user_dialogs_with_previews(self, user_id: UUID) -> tuple[list[Dialog], dict]:
        """Получить диалоги пользователя с превью последних сообщений."""
        dialogs = await self.dialogs_repository.get_user_dialogs(user_id)
        dialog_ids = [d.id for d in dialogs]
        last_messages = await self.dialogs_repository.get_last_messages(dialog_ids)
        return dialogs, last_messages

    async def create_or_get_direct(
        self, current_user_id: UUID, target_login: str
    ) -> tuple[Dialog, bool]:
        """Создать или найти существующий direct-диалог.

        Возвращает кортеж (dialog, created), где created=True, если диалог был создан.
        """
        target_user_id = await self._resolve_target_user(target_login)

        if current_user_id == target_user_id:
            raise SelfDialogError

        existing = await self.dialogs_repository.get_direct_dialog(current_user_id, target_user_id)
        if existing is not None:
            return existing, False

        dialog = await self.dialogs_repository.create_with_participants(
            dialog_type="direct",
            participant_ids=[current_user_id, target_user_id],
        )
        return dialog, True

    @staticmethod
    async def _resolve_target_user(target_login: str) -> UUID:
        try:
            return await get_user_id_by_login(target_login)
        except grpc.aio.AioRpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise UserNotFoundError(target_login) from e
            if e.code() in (
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
                grpc.StatusCode.INTERNAL,
            ):
                raise AuthServiceUnavailableError from e
            raise
