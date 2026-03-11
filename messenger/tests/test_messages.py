from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient

_CURRENT_USER_ID = uuid4()
_TARGET_USER_ID = uuid4()
_DIALOG_ENDPOINT = "/messenger/api/v1/dialogs/direct"


def _messages_endpoint(dialog_id: str) -> str:
    return f"/messenger/api/v1/dialogs/{dialog_id}/messages"


def _mock_login_by_uid(uid: object) -> str:
    return str(uid).replace("-", "")[:8]


async def _create_dialog(
    db_client: AsyncClient,
    user_a: UUID,
    user_b: UUID,
) -> dict[str, Any]:
    """Helper: create a direct dialog between two users and return response JSON."""
    mock_get_token = AsyncMock(return_value=user_a)
    mock_get_login = AsyncMock(return_value=user_b)
    mock_get_login_by_user_id = AsyncMock(side_effect=_mock_login_by_uid)

    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.services.dialogs.get_user_id_by_login", mock_get_login),
        patch("src.api.v1.dialogs.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        resp = await db_client.post(
            _DIALOG_ENDPOINT,
            json={"target_login": "target"},
            cookies={"access_token": "valid-token"},
        )
    assert resp.status_code == 200
    return resp.json()


@pytest.mark.asyncio
async def test_send_message_saved_and_returned(db_client: AsyncClient) -> None:
    dialog = await _create_dialog(db_client, _CURRENT_USER_ID, _TARGET_USER_ID)
    dialog_id = dialog["id"]

    mock_get_token = AsyncMock(return_value=_CURRENT_USER_ID)
    mock_get_login_by_user_id = AsyncMock(return_value="sender_login_mock")
    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.api.v1.messages.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        response = await db_client.post(
            _messages_endpoint(dialog_id),
            json={
                "text": "Hello!",
                "client_message_id": "unique-msg-001",
            },
            cookies={"access_token": "valid-token"},
        )

    assert response.status_code == 201
    data = response.json()
    assert data["text"] == "Hello!"
    assert data["client_message_id"] == "unique-msg-001"
    assert data["dialog_id"] == dialog_id
    assert data["sender_login"] == "sender_login_mock"
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_idempotent_by_client_message_id(db_client: AsyncClient) -> None:
    user_a = uuid4()
    user_b = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]
    client_msg_id = f"idempotent-{uuid4()}"

    mock_get_token = AsyncMock(return_value=user_a)
    mock_get_login_by_user_id = AsyncMock(side_effect=_mock_login_by_uid)
    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.api.v1.messages.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        resp1 = await db_client.post(
            _messages_endpoint(dialog_id),
            json={
                "text": "Idempotent message",
                "client_message_id": client_msg_id,
            },
            cookies={"access_token": "valid-token"},
        )
        resp2 = await db_client.post(
            _messages_endpoint(dialog_id),
            json={
                "text": "Idempotent message",
                "client_message_id": client_msg_id,
            },
            cookies={"access_token": "valid-token"},
        )

    assert resp1.status_code == 201
    assert resp2.status_code == 201
    assert resp1.json()["id"] == resp2.json()["id"]


@pytest.mark.asyncio
async def test_send_message_to_foreign_dialog_forbidden(
    db_client: AsyncClient,
) -> None:
    user_a = uuid4()
    user_b = uuid4()
    outsider = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    mock_get_token = AsyncMock(return_value=outsider)
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
        response = await db_client.post(
            _messages_endpoint(dialog_id),
            json={
                "text": "I should not be here",
                "client_message_id": f"forbidden-{uuid4()}",
            },
            cookies={"access_token": "valid-token"},
        )

    assert response.status_code == 403
    assert "participant" in response.json()["detail"].lower()


# ─── GET /dialogs/{id}/messages ───


async def _send_message(
    db_client: AsyncClient,
    dialog_id: str,
    sender_id: UUID,
    text: str,
    client_message_id: str,
) -> dict[str, Any]:
    mock_get_token = AsyncMock(return_value=sender_id)
    mock_get_login_by_user_id = AsyncMock(side_effect=_mock_login_by_uid)
    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.api.v1.messages.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        resp = await db_client.post(
            _messages_endpoint(dialog_id),
            json={"text": text, "client_message_id": client_message_id},
            cookies={"access_token": "valid-token"},
        )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_get_messages_with_limit_and_offset(db_client: AsyncClient) -> None:
    user_a = uuid4()
    user_b = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    for i in range(5):
        await _send_message(db_client, dialog_id, user_a, f"msg-{i}", f"get-lo-{uuid4()}")

    mock_get_token = AsyncMock(return_value=user_a)
    mock_get_login_by_user_id = AsyncMock(side_effect=_mock_login_by_uid)
    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.api.v1.messages.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        resp_all = await db_client.get(
            _messages_endpoint(dialog_id),
            params={"limit": 100, "offset": 0},
            cookies={"access_token": "valid-token"},
        )
        resp_page = await db_client.get(
            _messages_endpoint(dialog_id),
            params={"limit": 2, "offset": 1},
            cookies={"access_token": "valid-token"},
        )

    assert resp_all.status_code == 200
    all_msgs = resp_all.json()["messages"]
    assert len(all_msgs) == 5

    assert resp_page.status_code == 200
    page_msgs = resp_page.json()["messages"]
    assert len(page_msgs) == 2
    assert page_msgs[0]["id"] == all_msgs[1]["id"]
    assert page_msgs[1]["id"] == all_msgs[2]["id"]


@pytest.mark.asyncio
async def test_get_messages_deterministic_order(db_client: AsyncClient) -> None:
    user_a = uuid4()
    user_b = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    for i in range(3):
        await _send_message(db_client, dialog_id, user_a, f"order-{i}", f"order-{uuid4()}")

    mock_get_token = AsyncMock(return_value=user_a)
    mock_get_login_by_user_id = AsyncMock(side_effect=_mock_login_by_uid)
    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.api.v1.messages.get_login_by_user_id", mock_get_login_by_user_id),
    ):
        resp1 = await db_client.get(
            _messages_endpoint(dialog_id),
            cookies={"access_token": "valid-token"},
        )
        resp2 = await db_client.get(
            _messages_endpoint(dialog_id),
            cookies={"access_token": "valid-token"},
        )

    msgs1 = resp1.json()["messages"]
    msgs2 = resp2.json()["messages"]
    assert [m["id"] for m in msgs1] == [m["id"] for m in msgs2]

    timestamps = [m["created_at"] for m in msgs1]
    assert timestamps == sorted(timestamps)


@pytest.mark.asyncio
async def test_get_messages_only_participants_allowed(db_client: AsyncClient) -> None:
    user_a = uuid4()
    user_b = uuid4()
    outsider = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    await _send_message(db_client, dialog_id, user_a, "secret", f"secret-{uuid4()}")

    mock_get_token = AsyncMock(return_value=outsider)
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
        resp = await db_client.get(
            _messages_endpoint(dialog_id),
            cookies={"access_token": "valid-token"},
        )

    assert resp.status_code == 403
    assert "participant" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_messages_dialog_not_found(db_client: AsyncClient) -> None:
    fake_dialog_id = str(uuid4())

    mock_get_token = AsyncMock(return_value=uuid4())
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
        resp = await db_client.get(
            _messages_endpoint(fake_dialog_id),
            cookies={"access_token": "valid-token"},
        )

    assert resp.status_code == 404


# ─── POST /messages/{id}/read ───


def _read_endpoint(message_id: str) -> str:
    return f"/messenger/api/v1/messages/{message_id}/read"


@pytest.mark.asyncio
async def test_mark_message_as_read(db_client: AsyncClient) -> None:
    user_a = uuid4()
    user_b = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    msg = await _send_message(db_client, dialog_id, user_a, "Read me", f"read-{uuid4()}")

    mock_get_token = AsyncMock(return_value=user_b)
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
        resp = await db_client.post(
            _read_endpoint(msg["id"]),
            cookies={"access_token": "valid-token"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["message_id"] == msg["id"]
    assert data["status"] == "read"


@pytest.mark.asyncio
async def test_mark_message_as_read_idempotent(db_client: AsyncClient) -> None:
    user_a = uuid4()
    user_b = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    msg = await _send_message(db_client, dialog_id, user_a, "Read twice", f"read2-{uuid4()}")

    mock_get_token = AsyncMock(return_value=user_b)
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
        resp1 = await db_client.post(
            _read_endpoint(msg["id"]),
            cookies={"access_token": "valid-token"},
        )
        resp2 = await db_client.post(
            _read_endpoint(msg["id"]),
            cookies={"access_token": "valid-token"},
        )

    assert resp1.status_code == 200
    assert resp2.status_code == 200
    assert resp1.json()["status"] == "read"
    assert resp2.json()["status"] == "read"


@pytest.mark.asyncio
async def test_mark_message_as_read_not_participant(db_client: AsyncClient) -> None:
    user_a = uuid4()
    user_b = uuid4()
    outsider = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    msg = await _send_message(db_client, dialog_id, user_a, "Secret", f"outsider-{uuid4()}")

    mock_get_token = AsyncMock(return_value=outsider)
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
        resp = await db_client.post(
            _read_endpoint(msg["id"]),
            cookies={"access_token": "valid-token"},
        )

    assert resp.status_code == 403
    assert "participant" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_mark_message_as_read_not_found(db_client: AsyncClient) -> None:
    fake_msg_id = str(uuid4())

    mock_get_token = AsyncMock(return_value=uuid4())
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
        resp = await db_client.post(
            _read_endpoint(fake_msg_id),
            cookies={"access_token": "valid-token"},
        )

    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_sender_can_see_read_status(db_client: AsyncClient) -> None:
    """Отправитель также может отметить своё сообщение как прочитанное."""
    user_a = uuid4()
    user_b = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    msg = await _send_message(db_client, dialog_id, user_a, "Self read", f"self-{uuid4()}")

    mock_get_token = AsyncMock(return_value=user_a)
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
        resp = await db_client.post(
            _read_endpoint(msg["id"]),
            cookies={"access_token": "valid-token"},
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "read"
