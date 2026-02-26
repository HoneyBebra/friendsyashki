import time
from typing import Literal
from uuid import UUID

from jose import jwt

from src.core.config import settings
from src.exceptions.jwt import WrongTokenType


async def create_token(
        sub: UUID | str,
        token_type: Literal["access", "refresh"],
) -> str:
    iat = time.time()
    raw_data = {
        "sub": str(sub),
        "iat": iat,
    }

    if token_type == "access":
        raw_data["exp"] = iat + settings.access_token_expire
    elif token_type == "refresh":
        raw_data["exp"] = iat + settings.refresh_token_expire
    else:
        raise WrongTokenType

    to_encode = raw_data.copy()
    to_encode.update({"type": token_type})
    encoded_jwt = jwt.encode(
        claims=to_encode,
        key=settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return encoded_jwt
