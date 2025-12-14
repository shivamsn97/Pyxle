"""Developer error overlay websocket coordination."""

from __future__ import annotations

import asyncio
import json
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set

from starlette.websockets import WebSocket, WebSocketDisconnect

from pyxle.cli.logger import ConsoleLogger


@dataclass(frozen=True)
class OverlayEvent:
    """Structured payload sent to connected developer overlay clients."""

    type: str
    payload: Dict[str, Any]


class OverlayManager:
    """Tracks websocket connections and broadcasts overlay events."""

    def __init__(self, *, logger: Optional[ConsoleLogger] = None) -> None:
        self._connections: Set[WebSocket] = set()
        self._lock = asyncio.Lock()
        self._logger = logger or ConsoleLogger()

    async def register(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections.add(websocket)

    async def unregister(self, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections.discard(websocket)

    async def broadcast(self, event: OverlayEvent) -> None:
        message = json.dumps({"type": event.type, "payload": event.payload})
        async with self._lock:
            connections = list(self._connections)
        stale: List[WebSocket] = []
        for connection in connections:
            try:
                await connection.send_text(message)
            except Exception:  # pragma: no cover - defensive cleanup
                stale.append(connection)
        for connection in stale:
            await self.unregister(connection)
        if stale:
            self._logger.warning(
                f"[Pyxle] Removed {len(stale)} overlay connection(s) due to send failure"
            )

    async def notify_error(
        self,
        *,
        route_path: str,
        error: BaseException,
        stack: Optional[str] = None,
        breadcrumbs: Optional[List[Dict[str, str]]] = None,
    ) -> None:
        payload = {
            "routePath": route_path,
            "message": str(error),
            "stack": stack or _format_stacktrace(error),
            "breadcrumbs": breadcrumbs or [],
        }
        await self.broadcast(OverlayEvent(type="error", payload=payload))

    async def notify_clear(self, *, route_path: str) -> None:
        await self.broadcast(
            OverlayEvent(
                type="clear",
                payload={"routePath": route_path},
            )
        )

    async def notify_reload(self, *, changed_paths: Sequence[str] | None = None) -> None:
        await self.broadcast(
            OverlayEvent(
                type="reload",
                payload={"changedPaths": list(changed_paths or [])},
            )
        )

    async def websocket_endpoint(self, websocket: WebSocket) -> None:
        await self.register(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:  # pragma: no cover - normal shutdown path
            pass
        finally:
            await self.unregister(websocket)


def _format_stacktrace(error: BaseException) -> str:
    return "".join(traceback.format_exception(type(error), error, error.__traceback__))


__all__ = ["OverlayManager", "OverlayEvent"]
