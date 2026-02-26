from fastapi import Depends
from redis.asyncio import Redis

from src.db.redis import get_redis_session
from src.repositories.base.jwt_token import BaseJwtTokenRepository


class JwtTokenRepository(BaseJwtTokenRepository):
    def __init__(
            self,
            redis_session: Redis = Depends(get_redis_session),
    ) -> None:
        self.redis_session = redis_session

    async def set_token_to_blacklist(self, token: str, expires_in: int) -> None:
        await self.redis_session.setex(
            name=token,
            time=expires_in,
            value="none",
        )

    async def is_token_in_blacklist(self, token: str) -> bool:
        return bool(await self.redis_session.exists(token))
