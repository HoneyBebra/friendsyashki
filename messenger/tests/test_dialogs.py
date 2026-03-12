from unittest.mock import AsyncMock, patch
from uuid import uuid4

import grpc  # type: ignore[import-untyped]
import pytest
from httpx import AsyncClient

_CURRENT_USER_ID = uuid4()
_TARGET_USER_ID = uuid4()
_TARGET_LOGIN = "target_user"
_ENDPOINT = "/messenger/api/v1/dialogs/direct"
_LIST_ENDPOINT = "/messenger/api/v1/dialogs"


def _make_aio_rpc_error(code: grpc.StatusCode, details: str = "") -> grpc.aio.AioRpcError:
    return grpc.aio.AioRpcError(
        code=code,
        initial_metadata=grpc.aio.Metadata(),
        trailing_metadata=grpc.aio.Metadata(),
        details=details,
    )


@pytest.mark.asyncio
async def test_create_direct_dialog(db_client: AsyncClient) -> None:
    mock_get_token = AsyncMock(return_value=_CURRENT_USER_ID)
    mock_get_login = AsyncMock(return_value=_TARGET_USER_ID)
    mock_get_login_by_user_id = AsyncMock(
        side_effect=lambda uid: "current_user" if uid == _CURRENT_USER_ID else "target_user",
    )

    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.services.dialogs.get_user_id_by_login", mock_get_login),
        patch("src.api.v1.dialogs.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        response = await db_client.post(
            _ENDPOINT,
            json={"target_login": _TARGET_LOGIN},
            cookies={"access_token": "valid-token"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "direct"
    assert len(data["participants"]) == 2

    participant_logins = {p["login"] for p in data["participants"]}
    assert "current_user" in participant_logins
    assert "target_user" in participant_logins

    mock_get_login.assert_awaited_once_with(_TARGET_LOGIN)


def _any_login_mock(uid: object) -> str:
    return str(uid).replace("-", "")[:8]


@pytest.mark.asyncio
async def test_get_existing_direct_dialog(
    db_client: AsyncClient,
) -> None:
    user_a = uuid4()
    user_b = uuid4()
    mock_get_token = AsyncMock(return_value=user_a)
    mock_get_login = AsyncMock(return_value=user_b)
    mock_get_login_by_user_id = AsyncMock(side_effect=_any_login_mock)

    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.services.dialogs.get_user_id_by_login", mock_get_login),
        patch("src.api.v1.dialogs.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        resp1 = await db_client.post(
            _ENDPOINT,
            json={"target_login": "other_user"},
            cookies={"access_token": "valid-token"},
        )
        resp2 = await db_client.post(
            _ENDPOINT,
            json={"target_login": "other_user"},
            cookies={"access_token": "valid-token"},
        )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_cannot_create_dialog_with_self(
    client: AsyncClient,
) -> None:
    same_user_id = uuid4()
    mock_get_token = AsyncMock(return_value=same_user_id)
    mock_get_login = AsyncMock(return_value=same_user_id)

    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.services.dialogs.get_user_id_by_login", mock_get_login),
    ):
        response = await client.post(
            _ENDPOINT,
            json={"target_login": "myself"},
            cookies={"access_token": "valid-token"},
        )

    assert response.status_code == 400
    assert "yourself" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_target_login_not_found(
    client: AsyncClient,
) -> None:
    mock_get_token = AsyncMock(return_value=_CURRENT_USER_ID)
    mock_get_login = AsyncMock(
        side_effect=_make_aio_rpc_error(grpc.StatusCode.NOT_FOUND, "User not found")
    )

    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.services.dialogs.get_user_id_by_login", mock_get_login),
    ):
        response = await client.post(
            _ENDPOINT,
            json={"target_login": "nonexistent"},
            cookies={"access_token": "valid-token"},
        )

    assert response.status_code == 404
    assert "nonexistent" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_user_sees_only_own_dialogs(db_client: AsyncClient) -> None:
    user_a = uuid4()
    user_b = uuid4()
    user_c = uuid4()

    mock_get_token_a = AsyncMock(return_value=user_a)
    mock_get_login_b = AsyncMock(return_value=user_b)
    mock_get_login_by_user_id = AsyncMock(side_effect=_any_login_mock)

    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token_a),
        patch("src.services.dialogs.get_user_id_by_login", mock_get_login_b),
        patch("src.api.v1.dialogs.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        await db_client.post(
            _ENDPOINT,
            json={"target_login": "user_b"},
            cookies={"access_token": "token-a"},
        )

    mock_get_token_b = AsyncMock(return_value=user_b)
    mock_get_login_c = AsyncMock(return_value=user_c)

    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token_b),
        patch("src.services.dialogs.get_user_id_by_login", mock_get_login_c),
        patch("src.api.v1.dialogs.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        await db_client.post(
            _ENDPOINT,
            json={"target_login": "user_c"},
            cookies={"access_token": "token-b"},
        )

    with (
        patch(
            "src.dependencies.auth.get_user_id_by_token",
            AsyncMock(return_value=user_c),
        ),
        patch("src.api.v1.dialogs.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        response = await db_client.get(
            _LIST_ENDPOINT,
            cookies={"access_token": "token-c"},
        )

    assert response.status_code == 200
    data = response.json()
    dialogs = data["dialogs"]

    user_c_login = _any_login_mock(user_c)
    for dialog in dialogs:
        participant_logins = {p["login"] for p in dialog["participants"]}
        assert user_c_login in participant_logins


@pytest.mark.asyncio
async def test_dialogs_sorted_by_last_activity(db_client: AsyncClient) -> None:
    user_a = uuid4()
    user_b = uuid4()
    user_c = uuid4()

    mock_get_token_a = AsyncMock(return_value=user_a)

    mock_get_login_by_user_id = AsyncMock(side_effect=_any_login_mock)
    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token_a),
        patch(
            "src.services.dialogs.get_user_id_by_login",
            AsyncMock(return_value=user_b),
        ),
        patch("src.api.v1.dialogs.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        resp1 = await db_client.post(
            _ENDPOINT,
            json={"target_login": "user_b"},
            cookies={"access_token": "token-a"},
        )

    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token_a),
        patch(
            "src.services.dialogs.get_user_id_by_login",
            AsyncMock(return_value=user_c),
        ),
        patch("src.api.v1.dialogs.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        resp2 = await db_client.post(
            _ENDPOINT,
            json={"target_login": "user_c"},
            cookies={"access_token": "token-a"},
        )

    dialog_1_id = resp1.json()["id"]
    dialog_2_id = resp2.json()["id"]

    with (
        patch(
            "src.dependencies.auth.get_user_id_by_token",
            AsyncMock(return_value=user_a),
        ),
        patch("src.api.v1.dialogs.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        response = await db_client.get(
            _LIST_ENDPOINT,
            cookies={"access_token": "token-a"},
        )

    assert response.status_code == 200
    dialogs = response.json()["dialogs"]
    dialog_ids = [d["id"] for d in dialogs]

    assert dialog_2_id in dialog_ids
    assert dialog_1_id in dialog_ids
    idx_2 = dialog_ids.index(dialog_2_id)
    idx_1 = dialog_ids.index(dialog_1_id)
    assert idx_2 < idx_1, "Newer dialog should appear first (sorted by updated_at DESC)"
