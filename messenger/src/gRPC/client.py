import logging
from uuid import UUID

import grpc  # type: ignore[import-not-found]

from src.core.config import settings
from src.gRPC.protos import user_pb2, user_pb2_grpc

logger = logging.getLogger(__name__)

_channel: grpc.aio.Channel | None = None
_stub: user_pb2_grpc.UserStub | None = None


async def open_auth_grpc_channel() -> None:
    global _channel, _stub  # noqa: PLW0603
    target = f"{settings.auth_grpc_host}:{settings.auth_grpc_port}"
    _channel = grpc.aio.insecure_channel(target)
    _stub = user_pb2_grpc.UserStub(_channel)
    logger.info("Auth gRPC channel opened: %s", target)


async def close_auth_grpc_channel() -> None:
    global _channel, _stub  # noqa: PLW0603
    if _channel is not None:
        await _channel.close()
        _channel = None
        _stub = None
        logger.info("Auth gRPC channel closed")


def get_auth_stub() -> user_pb2_grpc.UserStub:
    if _stub is None:
        raise RuntimeError("Auth gRPC channel is not initialized")
    return _stub


async def get_user_id_by_token(access_token: str) -> UUID:
    stub = get_auth_stub()
    request = user_pb2.GetUserInfoByTokenRequest(access_token=access_token)  # type: ignore[attr-defined]
    response: user_pb2.GetUserInfoByTokenResponse = await stub.GetUserInfoByToken(request)  # type: ignore[attr-defined]
    try:
        return UUID(response.id)
    except ValueError as e:
        logger.warning("Invalid user id from auth service: %s", response.id)
        raise ValueError("Invalid user id from auth service") from e


async def get_user_id_by_login(login: str) -> UUID:
    stub = get_auth_stub()
    request = user_pb2.GetUserByLoginRequest(login=login)  # type: ignore[attr-defined]
    response: user_pb2.GetUserByLoginResponse = await stub.GetUserByLogin(request)  # type: ignore[attr-defined]
    try:
        return UUID(response.id)
    except ValueError as e:
        logger.warning("Invalid user id from auth service: %s", response.id)
        raise ValueError("Invalid user id from auth service") from e
