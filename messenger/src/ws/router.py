"""WebSocket endpoint: аутентификация по cookie до accept(), подписка на события по user_id."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.gRPC.client import get_user_id_by_token
from src.ws.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.websocket("/ws")
async def websocket_connect(websocket: WebSocket) -> None:
    # Аутентификация ДО accept() — неаутентифицированные соединения отклоняются на уровне HTTP
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

    ws_manager.register(user_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        ws_manager.unregister(user_id, websocket)
