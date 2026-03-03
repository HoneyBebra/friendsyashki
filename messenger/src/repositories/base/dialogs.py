from abc import ABC, abstractmethod
from uuid import UUID

from src.models.dialogs import Dialog


class BaseDialogsRepository(ABC):
    @abstractmethod
    async def create(self, dialog_type: str, title: str | None = None) -> Dialog:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id(self, dialog_id: UUID) -> Dialog | None:
        raise NotImplementedError

    @abstractmethod
    async def get_user_dialogs(self, user_id: UUID) -> list[Dialog]:
        raise NotImplementedError

    @abstractmethod
    async def add_participant(
        self, dialog_id: UUID, user_id: UUID
    ) -> None:
        raise NotImplementedError
