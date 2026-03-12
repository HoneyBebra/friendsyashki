from uuid import UUID

from src.exceptions.messages import (
    ClientMessageIdConflictError,
    DialogNotFoundError,
    MessageNotFoundError,
    NotDialogParticipantError,
)
from src.models.message_statuses import MessageStatus
from src.models.messages import Message
from src.repositories.dialogs import DialogsRepository
from src.repositories.messages import MessagesRepository


class MessagesService:
    def __init__(
        self,
        messages_repository: MessagesRepository,
        dialogs_repository: DialogsRepository,
    ) -> None:
        self.messages_repository = messages_repository
        self.dialogs_repository = dialogs_repository

    async def send_message(
        self,
        dialog_id: UUID,
        sender_id: UUID,
        text: str,
        client_message_id: str,
    ) -> tuple[Message, list[UUID]]:
        dialog = await self.dialogs_repository.get_by_id(dialog_id)
        if dialog is None:
            raise DialogNotFoundError(dialog_id)

        participant_ids = {p.user_id for p in dialog.participants}
        if sender_id not in participant_ids:
            raise NotDialogParticipantError(sender_id, dialog_id)

        existing = await self.messages_repository.get_by_client_message_id(client_message_id)
        if existing is not None:
            if existing.dialog_id == dialog_id and existing.sender_id == sender_id:
                return existing, list(participant_ids)
            raise ClientMessageIdConflictError(client_message_id)

        message = await self.messages_repository.create(
            dialog_id=dialog_id,
            sender_id=sender_id,
            text=text,
            client_message_id=client_message_id,
        )
        return message, list(participant_ids)

    async def get_messages(
        self,
        dialog_id: UUID,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        dialog = await self.dialogs_repository.get_by_id(dialog_id)
        if dialog is None:
            raise DialogNotFoundError(dialog_id)

        participant_ids = {p.user_id for p in dialog.participants}
        if user_id not in participant_ids:
            raise NotDialogParticipantError(user_id, dialog_id)

        return await self.messages_repository.get_by_dialog(
            dialog_id=dialog_id,
            limit=limit,
            offset=offset,
        )

    async def mark_as_read(
        self,
        message_id: UUID,
        user_id: UUID,
    ) -> tuple[MessageStatus | None, list[UUID]]:
        """Пометить сообщение как прочитанное.

        Возвращает (status, participant_ids).
        status=None означает, что сообщение уже было прочитано (идемпотентность).
        """
        message = await self.messages_repository.get_by_id(message_id)
        if message is None:
            raise MessageNotFoundError(message_id)

        dialog = await self.dialogs_repository.get_by_id(message.dialog_id)
        if dialog is None:
            raise DialogNotFoundError(message.dialog_id)

        participant_ids = {p.user_id for p in dialog.participants}
        if user_id not in participant_ids:
            raise NotDialogParticipantError(user_id, message.dialog_id)

        status = await self.messages_repository.set_read_if_not_read(message_id, user_id)
        return status, list(participant_ids)
