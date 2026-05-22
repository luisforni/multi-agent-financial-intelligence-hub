from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as aioredis

from shared.events import BaseEvent, EventType, STREAM_NAMES

logger = logging.getLogger(__name__)

_MAX_STREAM_LENGTH = 10_000
_BLOCK_MS = 2_000  # block for 2s waiting for new messages


class MessageBus:
    """Redis Streams-based message bus for inter-agent communication."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._client: aioredis.Redis | None = None  # type: ignore[type-arg]

    async def connect(self) -> None:
        self._client = aioredis.from_url(
            self._redis_url, encoding="utf-8", decode_responses=True
        )
        await self._client.ping()
        logger.info("MessageBus connected", extra={"redis_url": self._redis_url})

    async def disconnect(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def _redis(self) -> aioredis.Redis:  # type: ignore[type-arg]
        if self._client is None:
            raise RuntimeError("MessageBus not connected. Call connect() first.")
        return self._client

    async def publish(self, event: BaseEvent) -> str:
        stream = STREAM_NAMES[event.event_type]
        payload = event.model_dump_json()
        message_id: str = await self._redis.xadd(
            stream,
            {"data": payload},
            maxlen=_MAX_STREAM_LENGTH,
            approximate=True,
        )
        logger.debug(
            "Published event",
            extra={
                "stream": stream,
                "event_type": event.event_type,
                "correlation_id": event.correlation_id,
                "message_id": message_id,
            },
        )
        return message_id

    async def read_one(
        self,
        event_type: EventType,
        correlation_id: str,
        timeout_ms: int = 60_000,
    ) -> dict[str, Any] | None:
        """Block until a message with the given correlation_id arrives."""
        stream = STREAM_NAMES[event_type]
        last_id = "0-0"
        elapsed = 0

        while elapsed < timeout_ms:
            block = min(_BLOCK_MS, timeout_ms - elapsed)
            results: list[Any] = await self._redis.xread(
                {stream: last_id}, block=block, count=50
            )
            elapsed += block

            if not results:
                continue

            for _stream, messages in results:
                for msg_id, fields in messages:
                    last_id = msg_id
                    raw = json.loads(fields["data"])
                    if raw.get("correlation_id") == correlation_id:
                        return raw

        return None

    async def create_consumer_group(
        self, event_type: EventType, group: str
    ) -> None:
        stream = STREAM_NAMES[event_type]
        try:
            await self._redis.xgroup_create(stream, group, id="0", mkstream=True)
        except aioredis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def consume(
        self,
        event_type: EventType,
        group: str,
        consumer: str,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Yield (message_id, raw_event) from a consumer group."""
        stream = STREAM_NAMES[event_type]
        await self.create_consumer_group(event_type, group)

        while True:
            results: list[Any] = await self._redis.xreadgroup(
                group,
                consumer,
                {stream: ">"},
                block=_BLOCK_MS,
                count=1,
            )
            if not results:
                continue
            for _stream, messages in results:
                for msg_id, fields in messages:
                    yield msg_id, json.loads(fields["data"])

    async def ack(self, event_type: EventType, group: str, message_id: str) -> None:
        stream = STREAM_NAMES[event_type]
        await self._redis.xack(stream, group, message_id)


@asynccontextmanager
async def lifespan_message_bus(redis_url: str) -> AsyncIterator[MessageBus]:
    bus = MessageBus(redis_url)
    await bus.connect()
    try:
        yield bus
    finally:
        await bus.disconnect()
