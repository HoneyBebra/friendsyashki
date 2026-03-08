import grpc
from fastapi import HTTPException

from src.db.postgres import get_session
from src.db.redis import get_redis_session
from src.dependencies.jwt import get_access_token_data
from src.gRPC.protos import user_pb2, user_pb2_grpc
from src.repositories.jwt_token import JwtTokenRepository
from src.repositories.users import UsersRepository
from src.services.users import UsersService


class GrpcServer(user_pb2_grpc.UserServicer):  # type: ignore[name-defined]
    def __init__(self, user_service: UsersService) -> None:
        super().__init__()

        self.user_service = user_service

    async def GetUserInfoByToken(  # noqa: N802
        self,
        request: user_pb2.GetUserInfoByTokenRequest,  # type: ignore[name-defined]
        context: grpc.aio.ServicerContext,
    ) -> user_pb2.GetUserInfoByTokenResponse:  # type: ignore[name-defined]
        try:
            user_data, token = await get_access_token_data(
                access_token=request.access_token,
                user_service=self.user_service,
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
        users = await self.user_service.users_repository.read(login=request.login)

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
        from uuid import UUID

        try:
            user_id = UUID(request.id)
        except ValueError:
            context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
            context.set_details("Invalid user id")
            return user_pb2.GetUserByIdResponse()  # type: ignore[attr-defined]

        user = await self.user_service.users_repository.read_by_id(user_id)
        if not user:
            context.set_code(grpc.StatusCode.NOT_FOUND)
            context.set_details("User not found")
            return user_pb2.GetUserByIdResponse()  # type: ignore[attr-defined]

        return user_pb2.GetUserByIdResponse(id=str(user.id), login=user.login)  # type: ignore[attr-defined]


async def get_grpc_session() -> GrpcServer:
    return GrpcServer(
        user_service=UsersService(
            users_repository=UsersRepository(session=await anext(get_session())),
            jwt_token_repository=JwtTokenRepository(redis_session=await anext(get_redis_session())),
        )
    )
