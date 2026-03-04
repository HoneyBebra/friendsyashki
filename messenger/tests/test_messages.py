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


async def _create_dialog(
    db_client: AsyncClient,
    user_a: UUID,
    user_b: UUID,
) -> dict[str, Any]:
    """Helper: create a direct dialog between two users and return response JSON."""
    mock_get_token = AsyncMock(return_value=user_a)
    mock_get_login = AsyncMock(return_value=user_b)

    with (
        patch("src.dependencies.auth.get_user_id_by_token", mock_get_token),
        patch("src.services.dialogs.get_user_id_by_login", mock_get_login),
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
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
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
    assert data["sender_id"] == str(_CURRENT_USER_ID)
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
    with patch("src.dependencies.auth.get_user_id_by_token", mock_get_token):
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
