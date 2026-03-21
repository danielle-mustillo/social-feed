from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.models import HealthResponse
from app.routes import admin, feed, follow, posts, users


def create_app(repository=None) -> FastAPI:
    if repository is None:
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            from app.cassandra import CassandraRepository

            cassandra_repository = CassandraRepository(get_settings())
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
