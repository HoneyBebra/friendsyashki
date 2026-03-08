"""Тесты WebSocket: new_message участникам диалога, reconnect, статус delivered (TASK-009)."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.main import app
from src.models.message_statuses import MessageStatus, MessageStatusEnum
from src.ws.manager import ws_manager

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
    """Создать диалог между двумя пользователями."""
    with (
        patch("src.dependencies.auth.get_user_id_by_token", AsyncMock(return_value=user_a)),
        patch("src.services.dialogs.get_user_id_by_login", AsyncMock(return_value=user_b)),
        patch("src.api.v1.dialogs.get_login_by_user_id", AsyncMock(side_effect=_mock_login_by_uid)),
    ):
        resp = await db_client.post(
            _DIALOG_ENDPOINT,
            json={"target_login": "target"},
            cookies={"access_token": "valid-token"},
        )
    assert resp.status_code == 200
    return resp.json()


async def _run_ws_connection(
    token: str,
    receive_queue: asyncio.Queue[dict[str, Any]],
    captured: list[dict[str, Any]],
) -> None:
    """Запустить один WS-коннект через ASGI в том же event loop; приходящие сообщения в captured."""
    scope: dict[str, Any] = {
        "type": "websocket",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "path": "/messenger/ws",
        "raw_path": b"/messenger/ws",
        "query_string": b"",
        "root_path": "",
        "scheme": "ws",
        "server": ("testserver", 80),
        "client": ("test", 0),
        "state": {},
        "headers": [(b"cookie", f"access_token={token}".encode())],
        "subprotocols": [],
    }

    async def receive() -> dict[str, Any]:
        return await receive_queue.get()

    async def send(message: dict[str, Any]) -> None:
        if message.get("type") == "websocket.send":
            text = message.get("text")
            if text:
                captured.append(json.loads(text))

    await app(scope, receive, send)


@pytest.mark.asyncio
async def test_two_clients_receive_new_message(db_client: AsyncClient) -> None:
    """Два клиента в одном диалоге получают событие new_message при отправке сообщения."""
    ws_manager._connections.clear()
    user_a = uuid4()
    user_b = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    def _get_user_by_token(token: str) -> UUID:
        if token == "token_a":
            return user_a
        if token == "token_b":
            return user_b
        return user_a

    mock_get_user = AsyncMock(side_effect=_get_user_by_token)
    q_a: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    q_b: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    capture_a: list[dict[str, Any]] = []
    capture_b: list[dict[str, Any]] = []

    await q_a.put({"type": "websocket.connect"})
    await q_b.put({"type": "websocket.connect"})

    with (
        patch("src.gRPC.client.get_user_id_by_token", mock_get_user),
        patch("src.ws.router.get_user_id_by_token", mock_get_user),
    ):
        task_a = asyncio.create_task(_run_ws_connection("token_a", q_a, capture_a))
        task_b = asyncio.create_task(_run_ws_connection("token_b", q_b, capture_b))
        for _ in range(50):
            await asyncio.sleep(0.05)
            if len(ws_manager._connections) >= 2:
                break
        assert len(ws_manager._connections) >= 2, "WS connections not registered in time"

        with (
            patch("src.dependencies.auth.get_user_id_by_token", mock_get_user),
            patch(
                "src.api.v1.messages.get_login_by_user_id",
                AsyncMock(side_effect=_mock_login_by_uid),
            ),
        ):
            resp = await db_client.post(
                _messages_endpoint(dialog_id),
                json={"text": "Hello WS!", "client_message_id": f"ws-{uuid4()}"},
                cookies={"access_token": "valid-token"},
            )
        assert resp.status_code == 201
        await asyncio.sleep(0.05)

    task_a.cancel()
    task_b.cancel()
    try:
        await task_a
    except asyncio.CancelledError:
        pass
    try:
        await task_b
    except asyncio.CancelledError:
        pass

    assert len(capture_a) >= 1
    assert len(capture_b) >= 1
    assert capture_a[0].get("event") == "new_message"
    assert capture_b[0].get("event") == "new_message"
    assert capture_a[0].get("payload", {}).get("text") == "Hello WS!"
    assert capture_b[0].get("payload", {}).get("dialog_id") == dialog_id


@pytest.mark.asyncio
async def test_reconnect_still_receives_events(db_client: AsyncClient) -> None:
    """После переподключения клиент снова получает события new_message."""
    ws_manager._connections.clear()
    user_a = uuid4()
    user_b = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    def _get_user_by_token(token: str) -> UUID:
        if token == "token_b":
            return user_b
        return user_a

    mock_get_user = AsyncMock(side_effect=_get_user_by_token)

    with (
        patch("src.gRPC.client.get_user_id_by_token", mock_get_user),
        patch("src.ws.router.get_user_id_by_token", mock_get_user),
    ):
        q1: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        cap1: list[dict[str, Any]] = []
        await q1.put({"type": "websocket.connect"})
        task1 = asyncio.create_task(_run_ws_connection("token_b", q1, cap1))
        await asyncio.sleep(0.03)
        task1.cancel()
        try:
            await task1
        except asyncio.CancelledError:
            pass

        q2: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        cap2: list[dict[str, Any]] = []
        await q2.put({"type": "websocket.connect"})
        task2 = asyncio.create_task(_run_ws_connection("token_b", q2, cap2))
        for _ in range(50):
            await asyncio.sleep(0.05)
            if ws_manager._connections.get(user_b):
                break

        with (
            patch("src.dependencies.auth.get_user_id_by_token", mock_get_user),
            patch(
                "src.api.v1.messages.get_login_by_user_id",
                AsyncMock(side_effect=_mock_login_by_uid),
            ),
        ):
            resp = await db_client.post(
                _messages_endpoint(dialog_id),
                json={
                    "text": "After reconnect",
                    "client_message_id": f"reconn-{uuid4()}",
                },
                cookies={"access_token": "valid-token"},
            )
        assert resp.status_code == 201
        await asyncio.sleep(0.05)

        task2.cancel()
        try:
            await task2
        except asyncio.CancelledError:
            pass

    assert len(cap2) >= 1
    assert cap2[0].get("event") == "new_message"
    assert cap2[0].get("payload", {}).get("text") == "After reconnect"


@pytest.mark.asyncio
async def test_delivered_when_recipient_ws_active(
    db_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """При активном WebSocket у получателя статус сообщения обновляется на delivered."""
    ws_manager._connections.clear()
    user_a = uuid4()
    user_b = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    def _get_user_by_token(token: str) -> UUID:
        if token == "token_b":
            return user_b
        return user_a

    mock_get_user = AsyncMock(side_effect=_get_user_by_token)
    q_b: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    capture_b: list[dict[str, Any]] = []
    await q_b.put({"type": "websocket.connect"})

    with (
        patch("src.gRPC.client.get_user_id_by_token", mock_get_user),
        patch("src.ws.router.get_user_id_by_token", mock_get_user),
    ):
        task_b = asyncio.create_task(_run_ws_connection("token_b", q_b, capture_b))
        for _ in range(50):
            await asyncio.sleep(0.05)
            if ws_manager._connections.get(user_b):
                break
        assert ws_manager._connections.get(user_b), "WS for user_b not registered"

        with (
            patch("src.dependencies.auth.get_user_id_by_token", mock_get_user),
            patch(
                "src.api.v1.messages.get_login_by_user_id",
                AsyncMock(side_effect=_mock_login_by_uid),
            ),
        ):
            resp = await db_client.post(
                _messages_endpoint(dialog_id),
                json={
                    "text": "Delivered check",
                    "client_message_id": f"deliv-{uuid4()}",
                },
                cookies={"access_token": "valid-token"},
            )
        assert resp.status_code == 201
        message_id = resp.json()["id"]
        await asyncio.sleep(0.05)

        task_b.cancel()
        try:
            await task_b
        except asyncio.CancelledError:
            pass

    result = await db_session.execute(
        select(MessageStatus).where(
            MessageStatus.message_id == message_id,
            MessageStatus.user_id == user_b,
        )
    )
    statuses = list(result.scalars().all())
    assert len(statuses) >= 1
    assert statuses[0].status == MessageStatusEnum.DELIVERED


@pytest.mark.asyncio
async def test_delivered_not_set_for_non_participant(
    db_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Статусы не проставляются неучастникам диалога (только участнику с активным WS)."""
    ws_manager._connections.clear()
    user_a = uuid4()
    user_b = uuid4()
    user_c = uuid4()
    dialog = await _create_dialog(db_client, user_a, user_b)
    dialog_id = dialog["id"]

    def _get_user_by_token(token: str) -> UUID:
        if token == "token_b":
            return user_b
        if token == "token_c":
            return user_c
        return user_a

    mock_get_user = AsyncMock(side_effect=_get_user_by_token)
    q_b: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    q_c: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    await q_b.put({"type": "websocket.connect"})
    await q_c.put({"type": "websocket.connect"})

    with (
        patch("src.gRPC.client.get_user_id_by_token", mock_get_user),
        patch("src.ws.router.get_user_id_by_token", mock_get_user),
    ):
        task_b = asyncio.create_task(_run_ws_connection("token_b", q_b, []))
        task_c = asyncio.create_task(_run_ws_connection("token_c", q_c, []))
        for _ in range(50):
            await asyncio.sleep(0.05)
            if ws_manager._connections.get(user_b) and ws_manager._connections.get(user_c):
                break

        with (
            patch("src.dependencies.auth.get_user_id_by_token", mock_get_user),
            patch(
                "src.api.v1.messages.get_login_by_user_id",
                AsyncMock(side_effect=_mock_login_by_uid),
            ),
        ):
            resp = await db_client.post(
                _messages_endpoint(dialog_id),
                json={
                    "text": "Only B is participant",
                    "client_message_id": f"nopart-{uuid4()}",
                },
                cookies={"access_token": "valid-token"},
            )
        assert resp.status_code == 201
        message_id = resp.json()["id"]
        await asyncio.sleep(0.05)

        task_b.cancel()
        task_c.cancel()
        try:
            await task_b
        except asyncio.CancelledError:
            pass
        try:
            await task_c
        except asyncio.CancelledError:
            pass

    result_c = await db_session.execute(
        select(MessageStatus).where(
            MessageStatus.message_id == message_id,
            MessageStatus.user_id == user_c,
        )
    )
    statuses_for_c = list(result_c.scalars().all())
    assert len(statuses_for_c) == 0, "Неучастник диалога (user_c) не должен получить статус"

    result_b = await db_session.execute(
        select(MessageStatus).where(
            MessageStatus.message_id == message_id,
            MessageStatus.user_id == user_b,
        )
    )
    statuses_for_b = list(result_b.scalars().all())
    assert len(statuses_for_b) >= 1
    assert statuses_for_b[0].status == MessageStatusEnum.DELIVERED
