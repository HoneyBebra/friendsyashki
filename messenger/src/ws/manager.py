"""Менеджер активных WebSocket-соединений по user_id."""

import logging
from uuid import UUID

from fastapi import WebSocket

from src.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Хранит активные WS по user_id, рассылает события участникам диалога."""

    def __init__(self) -> None:
        self._connections: dict[UUID, list[WebSocket]] = {}

    def register(self, user_id: UUID, websocket: WebSocket) -> list[WebSocket]:
        """Регистрирует соединение.

        Возвращает список старых соединений для закрытия при превышении лимита.
        """
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)

        excess: list[WebSocket] = []
        limit = settings.max_ws_connections_per_user
        while len(self._connections[user_id]) > limit:
            oldest = self._connections[user_id].pop(0)
            excess.append(oldest)

        logger.debug(
            "WS registered for user_id=%s, total connections=%s",
            user_id,
            len(self._connections[user_id]),
        )
        return excess

    def unregister(self, user_id: UUID, websocket: WebSocket) -> None:
        if user_id in self._connections:
            try:
                self._connections[user_id].remove(websocket)
            except ValueError:
                pass
            if not self._connections[user_id]:
                del self._connections[user_id]
        logger.debug("WS unregistered for user_id=%s", user_id)

    def get_connected_user_ids(self, user_ids: list[UUID]) -> list[UUID]:
        """Вернуть подмножество user_ids, у которых есть хотя бы одно активное WS-соединение."""
        return [uid for uid in user_ids if self._connections.get(uid)]

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
