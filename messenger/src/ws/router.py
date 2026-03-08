"""WebSocket endpoint: подключение по токену, подписка на события по user_id."""

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.gRPC.client import get_user_id_by_token
from src.ws.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()

_AUTH_TIMEOUT_SECONDS = 5


@router.websocket("/ws")
async def websocket_connect(websocket: WebSocket) -> None:
    await websocket.accept()

    # Ожидаем первое сообщение с токеном (JSON: {"token": "..."})
    try:
        raw = await asyncio.wait_for(
            websocket.receive_text(),
            timeout=_AUTH_TIMEOUT_SECONDS,
        )
    except (asyncio.TimeoutError, WebSocketDisconnect):
        await websocket.close(code=4001, reason="Auth timeout")
        return

    try:
        data = json.loads(raw)
        token = data.get("token") if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        token = None

    if not token:
        await websocket.close(code=4001, reason="Missing access_token")
        return

    try:
        user_id = await get_user_id_by_token(token)
    except Exception as e:  # noqa: BLE001
        logger.warning("WS auth failed: %s", e)
        await websocket.close(code=4003, reason="Invalid credentials")
        return

    ws_manager.register(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.unregister(user_id, websocket)
