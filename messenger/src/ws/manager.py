"""Менеджер активных WebSocket-соединений по user_id."""

import asyncio
import logging
from uuid import UUID

from fastapi import WebSocket

from src.core.config import settings

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Хранит активные WS по user_id, рассылает события участникам диалога."""

    def __init__(self) -> None:
        self._connections: dict[UUID, list[WebSocket]] = {}
        self._locks: dict[WebSocket, asyncio.Lock] = {}

    def register(self, user_id: UUID, websocket: WebSocket) -> list[WebSocket]:
        """Регистрирует соединение.

        Возвращает список старых соединений для закрытия при превышении лимита.
        """
        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(websocket)
        self._locks[websocket] = asyncio.Lock()

        excess: list[WebSocket] = []
        limit = settings.max_ws_connections_per_user
        while len(self._connections[user_id]) > limit:
            oldest = self._connections[user_id].pop(0)
            self._locks.pop(oldest, None)
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
        self._locks.pop(websocket, None)
        logger.debug("WS unregistered for user_id=%s", user_id)

    def get_connected_user_ids(self, user_ids: list[UUID]) -> list[UUID]:
        """Вернуть подмножество user_ids, у которых есть хотя бы одно активное WS-соединение."""
        return [uid for uid in user_ids if self._connections.get(uid)]

    async def _send_to_user(
        self,
        user_id: UUID,
        payload: dict,
    ) -> None:
        """Отправить payload всем сокетам одного пользователя с защитой от конкурентной записи."""
        sockets = self._connections.get(user_id)
        if not sockets:
            return
        dead: set[WebSocket] = set()
        for ws in list(sockets):
            lock = self._locks.get(ws)
            if lock is None:
                continue
            try:
                async with lock:
                    await ws.send_json(payload)
            except Exception as e:  # noqa: BLE001
                logger.warning("WS send failed for user_id=%s: %s", user_id, e)
                dead.add(ws)
        for ws in dead:
            self.unregister(user_id, ws)

    async def broadcast_to_users(
        self,
        user_ids: list[UUID],
        payload: dict,
    ) -> None:
        """Отправить payload всем подключённым сокетам указанных пользователей."""
        await asyncio.gather(
            *(self._send_to_user(uid, payload) for uid in user_ids),
        )


# Глобальный экземпляр для использования в API и WS endpoint
ws_manager = ConnectionManager()
