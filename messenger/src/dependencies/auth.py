from uuid import UUID

import grpc  # type: ignore[import-untyped]
from fastapi import Cookie, HTTPException, status

from src.gRPC.client import get_user_id_by_token


async def get_current_user_id(
    access_token: str = Cookie(..., alias="access_token"),
) -> UUID:
    try:
        return await get_user_id_by_token(access_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid credentials",
        ) from e
    except grpc.aio.AioRpcError as e:
        if e.code() == grpc.StatusCode.PERMISSION_DENIED:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied",
            ) from e
        if e.code() in (
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.INTERNAL,
        ):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Authentication service unavailable",
            ) from e
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Authentication failed",
        ) from e
