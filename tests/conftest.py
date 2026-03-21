from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.repository import InMemoryRepository


@pytest.fixture
async def client() -> AsyncClient:
    app = create_app(repository=InMemoryRepository())
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as test_client:
        yield test_client
