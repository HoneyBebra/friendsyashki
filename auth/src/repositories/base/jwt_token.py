from abc import ABC, abstractmethod


class BaseJwtTokenRepository(ABC):
    @abstractmethod
    async def set_token_to_blacklist(self, token: str, expires_in: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def is_token_in_blacklist(self, token: str) -> bool:
        raise NotImplementedError
