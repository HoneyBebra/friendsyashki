from abc import ABC, abstractmethod
from uuid import UUID

from src.models.message_statuses import MessageStatus
from src.models.messages import Message


class BaseMessagesRepository(ABC):
    @abstractmethod
    async def create(
        self,
        dialog_id: UUID,
        sender_id: UUID,
        text: str,
        client_message_id: str,
    ) -> Message:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, message_id: UUID) -> Message | None:
        raise NotImplementedError

    @abstractmethod
    async def get_by_dialog(
        self,
        dialog_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Message]:
        raise NotImplementedError

    @abstractmethod
    async def set_status(
        self,
        message_id: UUID,
        user_id: UUID,
        status: str,
    ) -> MessageStatus:
        raise NotImplementedError
