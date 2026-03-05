"""WebSocket endpoint: подключение по токену, подписка на события по user_id."""

import logging
from urllib.parse import parse_qs

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.gRPC.client import get_user_id_by_token
from src.ws.manager import ws_manager

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_token_from_scope(scope: dict) -> str | None:
    """Достаёт access_token из query string или из cookie."""
    query_string = scope.get("query_string", b"").decode("latin-1")
    if query_string:
        parsed = parse_qs(query_string)
        tokens = parsed.get("access_token")
        if tokens:
            return tokens[0]
    headers = scope.get("headers") or []
    for name, value in headers:
        if name.lower() == b"cookie":
            for part in value.decode("latin-1").split(";"):
                part = part.strip()
                if part.startswith("access_token="):
                    return part.split("=", 1)[1].strip()
            break
    return None


@router.websocket("/ws")
async def websocket_connect(websocket: WebSocket) -> None:
    await websocket.accept()
    token = _get_token_from_scope(websocket.scope)
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
