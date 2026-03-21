from __future__ import annotations

import os

import httpx
import pytest


pytestmark = pytest.mark.live


@pytest.mark.skipif(
    not os.getenv("SOCIAL_FEED_BASE_URL"),
    reason="Set SOCIAL_FEED_BASE_URL to run live cluster tests",
)
def test_live_cleanup():
    base_url = os.environ["SOCIAL_FEED_BASE_URL"].rstrip("/")
    host_header = os.getenv("SOCIAL_FEED_HOST_HEADER")
    headers = {"Host": host_header} if host_header else None

    with httpx.Client(base_url=base_url, timeout=30.0, headers=headers) as client:
        reset = client.post("/admin/reset")
        assert reset.status_code == 200
        assert reset.json() == {"status": "reset"}

        users = client.get("/users")
        assert users.status_code == 200
        assert users.json() == []
