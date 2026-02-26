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
            return user_pb2.GetUserInfoByTokenResponse()  # type: ignore[name-defined]

        return user_pb2.GetUserInfoByTokenResponse(id=str(user_data.sub))  # type: ignore[name-defined]


async def get_grpc_session() -> GrpcServer:
    return GrpcServer(
        user_service=UsersService(
            users_repository=UsersRepository(session=await anext(get_session())),
            jwt_token_repository=JwtTokenRepository(redis_session=await anext(get_redis_session())),
        )
    )
