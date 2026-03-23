from __future__ import annotations

import logging
import random
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request

from app.config import get_settings
from app.models import HealthResponse
from app.routes import admin, feed, follow, posts, users
from app.tracing import RequestTraceContext, request_trace_context


def configure_logging() -> None:
    social_feed_logger = logging.getLogger("social_feed")
    if not social_feed_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        social_feed_logger.addHandler(handler)
    social_feed_logger.setLevel(logging.INFO)
    social_feed_logger.propagate = False


configure_logging()
http_logger = logging.getLogger("social_feed.http")


def create_app(repository=None, settings=None) -> FastAPI:
    settings = settings or get_settings()

    if repository is None:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            from app.cassandra import CassandraRepository

            cassandra_repository = CassandraRepository(settings)
            app.state.repository = cassandra_repository
            try:
                yield
            finally:
                cassandra_repository.close()

        app = FastAPI(
            title="Cassandra Social Feed Demo",
            version="0.1.0",
            lifespan=lifespan,
        )
    else:
        app = FastAPI(
            title="Cassandra Social Feed Demo",
            version="0.1.0",
        )
        app.state.repository = repository

    @app.middleware("http")
    async def trace_request_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))
        trace_enabled = settings.cassandra_trace_enabled and (
            settings.cassandra_trace_sample_rate >= 1.0
            or random.random() < settings.cassandra_trace_sample_rate
        )
        started_at = time.perf_counter()

        with request_trace_context(
            RequestTraceContext(
                request_id=request_id,
                trace_enabled=trace_enabled,
                method=request.method,
                path=request.url.path,
            )
        ):
            response = await call_next(request)

        duration_ms = (time.perf_counter() - started_at) * 1000
        response.headers["X-Request-ID"] = request_id
        http_logger.info(
            "http_request request_id=%s method=%s path=%s status_code=%s duration_ms=%.2f cassandra_trace=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            trace_enabled,
        )
        return response

    app.include_router(users.router)
    app.include_router(follow.router)
    app.include_router(posts.router)
    app.include_router(feed.router)
    app.include_router(admin.router)

    @app.get("/healthz", response_model=HealthResponse, tags=["health"])
    async def healthcheck() -> HealthResponse:
        return HealthResponse(status="ok")

    return app


app = create_app()
