import json

from pyxle.cli.logger import ConsoleLogger, LogFormat


def test_console_logger_emits_expected_symbols():
    captured: list[str] = []

    def capture(message: str, *, fg: str | None = None, bold: bool = False) -> None:  # noqa: ARG001
        captured.append(message)

    logger = ConsoleLogger(secho=capture)

    logger.info("Info message")
    logger.success("Done")
    logger.warning("Careful")
    logger.error("Boom")
    logger.step("Navigate", "cd project")

    assert captured == [
        "ℹ️  Info message",
        "✅ Done",
        "⚠️  Careful",
        "❌ Boom",
        "▶️  Navigate — cd project",
    ]


def test_console_logger_json_emits_structured_payloads():
    captured: list[str] = []

    def capture(message: str, *, fg: str | None = None, bold: bool = False) -> None:  # noqa: ARG001
        captured.append(message)

    logger = ConsoleLogger(
        secho=capture,
        formatter=LogFormat.JSON,
        timestamp_factory=lambda: "2025-01-01T00:00:00Z",
    )

    logger.info("Info message")
    logger.step("Deploy", "Ship to prod")

    assert len(captured) == 2
    info_payload = json.loads(captured[0])
    step_payload = json.loads(captured[1])

    assert info_payload == {
        "level": "info",
        "message": "ℹ️  Info message",
        "timestamp": "2025-01-01T00:00:00Z",
    }
    assert step_payload["level"] == "step"
    assert step_payload["label"] == "Deploy"
    assert step_payload["detail"] == "Ship to prod"
    assert "ready" not in step_payload
    assert step_payload["timestamp"] == "2025-01-01T00:00:00Z"
