"""Менеджер активных WebSocket-соединений по user_id."""

import logging
from uuid import UUID

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Хранит активные WS по user_id, рассылает события участникам диалога."""

    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = {}

    def register(self, user_id: UUID, websocket: WebSocket) -> None:
        if user_id not in self._connections:
            self._connections[user_id] = set()
        self._connections[user_id].add(websocket)
        logger.debug(
            "WS registered for user_id=%s, total connections=%s",
            user_id,
            len(self._connections[user_id]),
        )

    def unregister(self, user_id: UUID, websocket: WebSocket) -> None:
        if user_id in self._connections:
            self._connections[user_id].discard(websocket)
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.debug("WS unregistered for user_id=%s", user_id)

    async def broadcast_to_users(
        self,
        user_ids: list[UUID],
        payload: dict,
    ) -> None:
        """Отправить payload всем подключённым сокетам указанных пользователей."""
        for user_id in user_ids:
            sockets = self._connections.get(user_id)
            if not sockets:
                continue
            dead: set[WebSocket] = set()
            for ws in sockets:
                try:
                    await ws.send_json(payload)
                except Exception as e:  # noqa: BLE001
                    logger.warning("WS send failed for user_id=%s: %s", user_id, e)
                    dead.add(ws)
            for ws in dead:
                self.unregister(user_id, ws)


# Глобальный экземпляр для использования в API и WS endpoint
ws_manager = ConnectionManager()
