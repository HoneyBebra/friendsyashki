from collections.abc import Generator
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import grpc  # type: ignore[import-untyped]
import pytest
from httpx import AsyncClient

from src.dependencies.auth import get_current_user_id
from src.main import app, router

_TEST_USER_ID = uuid4()


@pytest.fixture(autouse=True)
def _register_protected_route() -> Generator[None, None, None]:
    from fastapi import APIRouter, Depends

    protected = APIRouter()

    @protected.get("/protected")
    async def protected_endpoint(
        user_id: UUID = Depends(get_current_user_id),
    ) -> dict[str, str]:
        return {"user_id": str(user_id)}

    router.include_router(protected)
    app.router.routes = []
    app.include_router(router)
    yield  # type: ignore[misc]
    router.routes = [r for r in router.routes if getattr(r, "path", "") != "/protected"]
    app.router.routes = []
    app.include_router(router)


def _make_aio_rpc_error(code: grpc.StatusCode, details: str = "") -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(
        code=code,
        initial_metadata=grpc.aio.Metadata(),
        trailing_metadata=grpc.aio.Metadata(),
        details=details,
    )


@pytest.mark.asyncio
async def test_valid_token_grants_access(client: AsyncClient) -> None:
    mock_get_user_id = AsyncMock(return_value=_TEST_USER_ID)

    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_user_id):
        response = await client.get(
            "/messenger/api/v1/protected",
            cookies={"access_token": "valid-token-123"},
        )

    assert response.status_code == 200
    assert response.json() == {"user_id": str(_TEST_USER_ID)}
    mock_get_user_id.assert_awaited_once_with("valid-token-123")


@pytest.mark.asyncio
async def test_invalid_token_returns_403(client: AsyncClient) -> None:
    mock_get_user_id = AsyncMock(
        side_effect=_make_aio_rpc_error(grpc.StatusCode.PERMISSION_DENIED, "Token is invalid")
    )

    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_user_id):
        response = await client.get(
            "/messenger/api/v1/protected",
            cookies={"access_token": "bad-token"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"


@pytest.mark.asyncio
async def test_expired_token_returns_403(client: AsyncClient) -> None:
    mock_get_user_id = AsyncMock(
        side_effect=_make_aio_rpc_error(grpc.StatusCode.PERMISSION_DENIED, "Token expired")
    )

    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_user_id):
        response = await client.get(
            "/messenger/api/v1/protected",
            cookies={"access_token": "expired-token"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"


@pytest.mark.asyncio
async def test_blacklisted_token_returns_403(client: AsyncClient) -> None:
    mock_get_user_id = AsyncMock(
        side_effect=_make_aio_rpc_error(grpc.StatusCode.PERMISSION_DENIED, "Token is blacklisted")
    )

    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_user_id):
        response = await client.get(
            "/messenger/api/v1/protected",
            cookies={"access_token": "blacklisted-token"},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Access denied"


@pytest.mark.asyncio
async def test_missing_token_returns_422(client: AsyncClient) -> None:
    response = await client.get("/messenger/api/v1/protected")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_auth_unavailable_returns_503(client: AsyncClient) -> None:
    mock_get_user_id = AsyncMock(side_effect=_make_aio_rpc_error(grpc.StatusCode.UNAVAILABLE))

    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_user_id):
        response = await client.get(
            "/messenger/api/v1/protected",
            cookies={"access_token": "some-token"},
        )

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"].lower()
