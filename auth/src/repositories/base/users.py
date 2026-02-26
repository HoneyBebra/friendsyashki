from abc import ABC, abstractmethod
from uuid import UUID

from src.models.users import Users


class BaseUsersRepository(ABC):
    """Abstract class describing working with database."""

    @abstractmethod
    async def create(
            self,
            login: str,
            password_hash: str,
            encrypted_email: str | None = None,
            encrypted_phone_number: str | None = None,
            email_hash: str | None = None,
            phone_number_hash: str | None = None,
    ) -> Users:
        raise NotImplementedError

    @abstractmethod
    async def read(
            self,
            login: str | None = None,
            phone_number_hash: str | None = None,
            email_hash: str | None = None,
            limit: int | None = None,
            offset: int | None = None,
            order_by: str | None = None,
    ) -> list[Users]:
        raise NotImplementedError

    @abstractmethod
    async def update(
            self,
            user_id: UUID,
            login: str | None = None,
            password: str | None = None,
            phone_number: str | None = None,
            email: str | None = None,
    ) -> Users:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, user_id: UUID) -> None:
        raise NotImplementedError
