from __future__ import annotations

import json

import pytest
from starlette.websockets import WebSocketDisconnect

from pyxle.cli.logger import ConsoleLogger
from pyxle.devserver.overlay import OverlayManager


@pytest.fixture
def anyio_backend() -> str:  # pragma: no cover - fixture wiring
    return "asyncio"


class StubLogger(ConsoleLogger):
    def __init__(self) -> None:
        super().__init__(secho=lambda *_args, **_kwargs: None)


class StubWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[str] = []
        self.receive_calls = 0
        self.disconnect_after: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, data: str) -> None:
        self.sent.append(data)
        if self.disconnect_after is not None and len(self.sent) >= self.disconnect_after:
            raise RuntimeError("fail")

    async def receive_text(self) -> str:
        self.receive_calls += 1
        raise WebSocketDisconnect(1000)


@pytest.mark.anyio
async def test_overlay_manager_broadcasts_error_and_clear() -> None:
    manager = OverlayManager(logger=StubLogger())
    socket = StubWebSocket()

    await manager.register(socket)

    await manager.notify_error(route_path="/", error=RuntimeError("boom"), stack="trace")
    await manager.notify_clear(route_path="/")

    assert socket.accepted is True
    assert len(socket.sent) == 2

    error_message = json.loads(socket.sent[0])
    assert error_message["type"] == "error"
    assert error_message["payload"]["routePath"] == "/"
    assert error_message["payload"]["message"] == "boom"
    assert error_message["payload"]["stack"] == "trace"
    assert error_message["payload"]["breadcrumbs"] == []

    clear_message = json.loads(socket.sent[1])
    assert clear_message["type"] == "clear"
    assert clear_message["payload"]["routePath"] == "/"


@pytest.mark.anyio
async def test_overlay_manager_broadcasts_reload_event() -> None:
    manager = OverlayManager(logger=StubLogger())
    socket = StubWebSocket()

    await manager.register(socket)

    await manager.notify_reload(changed_paths=["pages/index.pyx"])

    assert socket.sent, "expected reload payload"
    message = json.loads(socket.sent[0])
    assert message["type"] == "reload"
    assert message["payload"]["changedPaths"] == ["pages/index.pyx"]


@pytest.mark.anyio
async def test_overlay_manager_endpoint_unregisters_on_disconnect() -> None:
    manager = OverlayManager(logger=StubLogger())
    socket = StubWebSocket()

    await manager.websocket_endpoint(socket)

    assert socket.accepted is True
    assert socket.receive_calls == 1
    assert len(manager._connections) == 0  # type: ignore[attr-defined]


@pytest.mark.anyio
async def test_overlay_manager_removes_stale_connections() -> None:
    manager = OverlayManager(logger=StubLogger())
    socket = StubWebSocket()
    socket.disconnect_after = 1

    await manager.register(socket)
    await manager.notify_error(route_path="/", error=RuntimeError("boom"), stack="trace")

    assert len(socket.sent) == 1
    assert len(manager._connections) == 0  # type: ignore[attr-defined]
