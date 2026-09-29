from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

try:
    from langfuse import get_client, observe, propagate_attributes

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_span(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

    def get_client():
        return _DummyClient()

    @contextmanager
    def propagate_attributes(**kwargs: Any):
        yield


def get_langfuse_client():
    return get_client()


def update_current_generation(client: Any, **kwargs: Any) -> None:
    """Update the active generation if the client supports it (test doubles may not)."""
    update = getattr(client, "update_current_generation", None)
    if callable(update):
        update(**kwargs)


def current_trace_id(client: Any) -> str:
    """Trace ID of the active observation, used to join structured logs with Langfuse."""
    getter = getattr(client, "get_current_trace_id", None)
    try:
        return (getter() if callable(getter) else None) or ""
    except Exception:  # tracing must never break the request path
        return ""


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )
