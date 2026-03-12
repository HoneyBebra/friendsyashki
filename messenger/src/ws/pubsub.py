"""Redis Pub/Sub for cross-worker WebSocket message broadcasting."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING
from uuid import UUID

import orjson
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import RedisError

if TYPE_CHECKING:
    from src.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

CHANNEL_NAME = "ws:broadcast"


class RedisPubSub:
    """Publish WS events to Redis and listen for local delivery."""

    def __init__(
        self,
        redis_url: str,
        manager: ConnectionManager,
    ) -> None:
        self._redis_url = redis_url
        self._manager = manager
        self._publisher: aioredis.Redis | None = None
        self._subscriber: aioredis.Redis | None = None
        self._listener_task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """Create Redis connections, verify with ping, and start listener."""
        self._publisher = aioredis.from_url(
            self._redis_url,
            decode_responses=False,
        )
        self._subscriber = aioredis.from_url(
            self._redis_url,
            decode_responses=False,
        )

        assert self._publisher is not None  # just assigned above
        try:
            await self._publisher.ping()
            logger.info("Redis Pub/Sub ping OK, connection verified")
        except (RedisConnectionError, RedisError, OSError, TimeoutError) as e:
            logger.error(
                "Redis Pub/Sub ping failed — publish will fall back "
                "to local delivery until Redis is available: %s",
                e,
            )

        self._listener_task = asyncio.create_task(self._listen())
        self._listener_task.add_done_callback(self._on_listener_done)
        logger.info("Redis Pub/Sub started on channel '%s'", CHANNEL_NAME)

    def _on_listener_done(self, task: asyncio.Task[None]) -> None:
        """Log unexpected listener task termination."""
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "Redis Pub/Sub listener task terminated with error: %s",
                exc,
            )

    async def stop(self) -> None:
        """Stop listener and close connections."""
        if self._listener_task is not None:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
            self._listener_task = None

        for conn in (self._publisher, self._subscriber):
            if conn is not None:
                await conn.aclose()
        self._publisher = None
        self._subscriber = None
        logger.info("Redis Pub/Sub stopped")

    async def _ensure_publisher(self) -> aioredis.Redis | None:
        """Return a healthy publisher connection, reconnecting if needed."""
        if self._publisher is not None:
            try:
                await self._publisher.ping()
                return self._publisher
            except (RedisConnectionError, RedisError, OSError, TimeoutError):
                logger.warning("Publisher ping failed, reconnecting...")
                try:
                    await self._publisher.aclose()
                except (RedisError, OSError):
                    pass

        try:
            publisher = aioredis.from_url(
                self._redis_url,
                decode_responses=False,
            )
            await publisher.ping()
            self._publisher = publisher
            logger.info("Redis publisher reconnected")
            return self._publisher
        except (RedisConnectionError, RedisError, OSError, TimeoutError) as e:
            logger.error("Redis publisher reconnect failed: %s", e)
            self._publisher = None
            return None

    async def publish(
        self,
        user_ids: list[UUID],
        payload: dict,
    ) -> None:
        """Publish message to Redis channel for all workers."""
        publisher = await self._ensure_publisher()
        if publisher is None:
            logger.warning("Redis publisher unavailable, falling back to local")
            await self._manager.local_broadcast_to_users(user_ids, payload)
            return

        message = orjson.dumps(
            {
                "user_ids": [str(uid) for uid in user_ids],
                "payload": payload,
            }
        )
        try:
            await publisher.publish(CHANNEL_NAME, message)
        except (
            RedisConnectionError,
            RedisError,
            OSError,
            TimeoutError,
        ) as e:
            logger.error(
                "Failed to publish to Redis, falling back to local: %s",
                e,
            )
            await self._manager.local_broadcast_to_users(user_ids, payload)

    async def _reconnect_subscriber(self) -> None:
        """Close and recreate the subscriber Redis connection."""
        if self._subscriber is not None:
            try:
                await self._subscriber.aclose()
            except (RedisError, OSError):
                pass
        self._subscriber = aioredis.from_url(
            self._redis_url,
            decode_responses=False,
        )

    async def _listen(self) -> None:
        """Listen to Redis channel and broadcast to local WS."""
        backoff = 0.5
        max_backoff = 5.0
        while True:
            if self._subscriber is None:
                return
            try:
                await self._subscribe_and_process()
                backoff = 0.5
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Redis subscriber error, reconnecting in %.1fs: %s",
                    backoff,
                    e,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)
                try:
                    await self._reconnect_subscriber()
                except (RedisError, OSError) as re_err:
                    logger.error("Subscriber reconnect failed: %s", re_err)

    async def _subscribe_and_process(self) -> None:
        """Subscribe to channel and process incoming messages."""
        if self._subscriber is None:
            return

        pubsub = self._subscriber.pubsub()
        try:
            await pubsub.subscribe(CHANNEL_NAME)
            logger.info("Subscribed to Redis channel '%s'", CHANNEL_NAME)
            async for raw_message in pubsub.listen():
                if raw_message["type"] != "message":
                    continue
                await self._handle_message(raw_message["data"])
        finally:
            await pubsub.unsubscribe(CHANNEL_NAME)
            await pubsub.aclose()

    async def _handle_message(self, data: bytes) -> None:
        """Deserialize and deliver via local manager."""
        try:
            parsed = orjson.loads(data)
            user_ids = [UUID(uid) for uid in parsed["user_ids"]]
            payload: dict = parsed["payload"]
        except (orjson.JSONDecodeError, KeyError, ValueError) as e:
            logger.warning("Invalid Pub/Sub message: %s", e)
            return

        await self._manager.local_broadcast_to_users(user_ids, payload)
