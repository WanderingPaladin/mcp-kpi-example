from __future__ import annotations

import json
import logging
from typing import Any
from uuid import uuid4

from contextvars import ContextVar

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="-")

SECRET_FIELD_NAMES = {
    "api_key",
    "openai_api_key",
    "authorization",
    "password",
    "secret",
    "token",
    "access_token",
}


def new_correlation_id() -> str:
    return uuid4().hex[:12]


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in SECRET_FIELD_NAMES or key_l.endswith("_api_key"):
                redacted[key] = "***"
            else:
                redacted[key] = redact(item)
        return redacted
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": getattr(record, "correlation_id", None)
            or correlation_id_var.get(),
        }
        for field in ("tool", "arguments", "outcome", "duration_ms", "error"):
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        return json.dumps(payload, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


def log_tool_call(
    logger: logging.Logger,
    *,
    tool: str,
    arguments: dict[str, Any],
    outcome: str,
    duration_ms: float,
    error: str | None = None,
) -> None:
    extra: dict[str, Any] = {
        "tool": tool,
        "arguments": redact(arguments),
        "outcome": outcome,
        "duration_ms": round(duration_ms, 2),
        "correlation_id": correlation_id_var.get(),
    }
    if error:
        extra["error"] = error
    logger.info("mcp_tool_call", extra=extra)
