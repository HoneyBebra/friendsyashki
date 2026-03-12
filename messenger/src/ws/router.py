"""WebSocket endpoint: аутентификация по cookie до accept(), подписка на события по user_id."""

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.core.config import settings
from src.gRPC.client import get_user_id_by_token
from src.ws.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()

HEARTBEAT_INTERVAL = settings.ws_heartbeat_interval
PONG_TIMEOUT = 10


async def _heartbeat(websocket: WebSocket) -> None:
    """Периодически отправляет ping; завершается при потере связи."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if websocket.client_state != WebSocketState.CONNECTED:
                return
            await asyncio.wait_for(
                websocket.send_json({"event": "ping"}),
                timeout=PONG_TIMEOUT,
            )
    except (
        asyncio.CancelledError,
        WebSocketDisconnect,
        asyncio.TimeoutError,
        RuntimeError,
        OSError,
    ):
        return


@router.websocket("/ws")
async def websocket_connect(websocket: WebSocket) -> None:
    token = websocket.cookies.get("access_token")
    if not token:
        await websocket.close(code=4001, reason="Missing access_token")
        return

    try:
        user_id = await get_user_id_by_token(token)
    except Exception as e:  # noqa: BLE001
        logger.warning("WS auth failed: %s", e)
        await websocket.close(code=4003, reason="Invalid credentials")
        return

    await websocket.accept()

    excess = ws_manager.register(user_id, websocket)
    for old_ws in excess:
        try:
            await old_ws.close(code=4008, reason="Too many connections")
        except Exception as e:  # noqa: BLE001
            logger.debug("Failed to close excess WS for user_id=%s: %s", user_id, e)

    heartbeat_task = asyncio.create_task(_heartbeat(websocket))
    try:
        while True:
            data = await websocket.receive_text()
            if data == "pong":
                continue
    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        try:
            await heartbeat_task
        except asyncio.CancelledError:
            pass
        ws_manager.unregister(user_id, websocket)
