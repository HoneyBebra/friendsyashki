from contextlib import asynccontextmanager
from typing import AsyncIterator
from uuid import UUID

import grpc
from fastapi import HTTPException

from src.db.postgres import get_session
from src.db.redis import get_redis_session
from src.dependencies.jwt import get_access_token_data
from src.gRPC.protos import user_pb2, user_pb2_grpc
from src.repositories.jwt_token import JwtTokenRepository
from src.repositories.users import UsersRepository
from src.services.users import UsersService


@asynccontextmanager
async def _create_user_service() -> AsyncIterator[UsersService]:
    """Создаёт UsersService с собственными DB и Redis сессиями.

    Корректно закрывает обе сессии после использования, откатывает DB-транзакцию
    при ошибке.
    """
    db_gen = get_session()
    redis_gen = get_redis_session()
    db_session = await anext(db_gen)
    redis_session = await anext(redis_gen)
    try:
        yield UsersService(
            users_repository=UsersRepository(session=db_session),
            jwt_token_repository=JwtTokenRepository(redis_session=redis_session),
        )
    finally:
        await db_gen.aclose()
        await redis_gen.aclose()


class GrpcServer(user_pb2_grpc.UserServicer):  # type: ignore[name-defined]
    async def GetUserInfoByToken(  # noqa: N802
        self,
        request: user_pb2.GetUserInfoByTokenRequest,  # type: ignore[name-defined]
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.GetUserInfoByTokenResponse:  # type: ignore[name-defined]
        async with _create_user_service() as user_service:
            try:
                user_data, token = await get_access_token_data(
                    access_token=request.access_token,
                    user_service=user_service,
                )
            except HTTPException as e:
                context.set_code(grpc.StatusCode.PERMISSION_DENIED)
                context.set_details(e.detail)
                return user_pb2.GetUserInfoByTokenResponse()  # type: ignore[attr-defined]

            return user_pb2.GetUserInfoByTokenResponse(  # type: ignore[attr-defined]
                id=str(user_data.sub),
                login=user_data.login or "",
            )

    async def GetUserByLogin(  # noqa: N802
        self,
        request: user_pb2.GetUserByLoginRequest,  # type: ignore[name-defined]
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.GetUserByLoginResponse:  # type: ignore[name-defined]
        async with _create_user_service() as user_service:
            users = await user_service.users_repository.read(login=request.login)

            if not users:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("User not found")
                return user_pb2.GetUserByLoginResponse()  # type: ignore[attr-defined]

            u = users[0]
            return user_pb2.GetUserByLoginResponse(id=str(u.id), login=u.login)  # type: ignore[attr-defined]

    async def GetUserById(  # noqa: N802
        self,
        request: user_pb2.GetUserByIdRequest,  # type: ignore[name-defined]
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.GetUserByIdResponse:  # type: ignore[name-defined]
        try:
            user_id = UUID(request.id)
        except ValueError:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Invalid user id")
            return user_pb2.GetUserByIdResponse()  # type: ignore[attr-defined]

        async with _create_user_service() as user_service:
            user = await user_service.users_repository.read_by_id(user_id)
            if not user:
                context.set_code(grpc.StatusCode.NOT_FOUND)
                context.set_details("User not found")
                return user_pb2.GetUserByIdResponse()  # type: ignore[attr-defined]

            return user_pb2.GetUserByIdResponse(id=str(user.id), login=user.login)  # type: ignore[attr-defined]


def create_grpc_server() -> GrpcServer:
    return GrpcServer()
