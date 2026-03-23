from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import Iterator
from contextlib import contextmanager


@dataclass(frozen=True)
class RequestTraceContext:
    request_id: str = "-"
    trace_enabled: bool = False
    method: str = "-"
    path: str = "-"


_request_trace_context: contextvars.ContextVar[RequestTraceContext] = (
    contextvars.ContextVar("request_trace_context", default=RequestTraceContext())
)


def get_request_trace_context() -> RequestTraceContext:
    return _request_trace_context.get()


@contextmanager
def request_trace_context(context: RequestTraceContext) -> Iterator[None]:
    token = _request_trace_context.set(context)
    try:
        yield
    finally:
        _request_trace_context.reset(token)
