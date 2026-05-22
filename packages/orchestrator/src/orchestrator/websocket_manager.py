from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Broadcasts JSON messages to all connected WebSocket clients."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.debug("WebSocket connected", extra={"total": len(self._connections)})

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws) if hasattr(self._connections, "discard") else None
        if ws in self._connections:
            self._connections.remove(ws)
        logger.debug("WebSocket disconnected", extra={"total": len(self._connections)})

    async def broadcast(self, message: dict[str, Any]) -> None:
        if not self._connections:
            return
        data = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._connections:
                self._connections.remove(ws)

    @property
    def connected_count(self) -> int:
        return len(self._connections)


ws_manager = ConnectionManager()
