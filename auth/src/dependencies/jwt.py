from typing import Any

from fastapi import Cookie, Depends, HTTPException, status
from jose import ExpiredSignatureError, JWTError, jwt
from pydantic import ValidationError

from src.core.config import settings
from src.schemas.v1.jwt import UserJwtSchema
from src.services.users import UsersService


async def get_access_token_data(
    access_token: str | None = Cookie(default=None, alias=settings.access_token_key_in_cookie),
    user_service: UsersService = Depends(),
) -> tuple[UserJwtSchema, str]:
    jwt_schema, token = await __get_token_data(access_token, user_service)
    if jwt_schema.type != "access":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid credentials",
        )
    return jwt_schema, token


async def get_refresh_token_data(
    refresh_token: str | None = Cookie(default=None, alias=settings.refresh_token_key_in_cookie),
    user_service: UsersService = Depends(),
) -> tuple[UserJwtSchema, str]:
    jwt_schema, token = await __get_token_data(refresh_token, user_service)
    if jwt_schema.type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid credentials",
        )
    return jwt_schema, token


async def __get_token_data(
        token: str | None,
        user_service: UsersService,
) -> tuple[UserJwtSchema, str]:
    token = await __check_raw_token(token)
    await __raise_if_jwt_in_blacklist(token, user_service)
    payload = await __get_payload(token)
    jwt_schema = await __get_jwt_schema(payload)

    return jwt_schema, token


async def __check_raw_token(token: str | None) -> str:
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Credentials are not provided",
        )
    return token


async def __raise_if_jwt_in_blacklist(token: str, user_service: UsersService) -> None:
    if await user_service.jwt_token_repository.is_token_in_blacklist(token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token in blacklist",
        )


async def __get_payload(token: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token=token,
            key=settings.jwt_secret_key,
            algorithms=settings.jwt_algorithm,
        )
        return payload
    except ExpiredSignatureError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Token is outdated",
        ) from e
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(e),
        ) from e


async def __get_jwt_schema(payload: dict[str, Any]) -> UserJwtSchema:
    try:
        return UserJwtSchema(**payload)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid credentials",
        ) from e
