from __future__ import annotations

import os
from uuid import uuid4

import httpx
import pytest


pytestmark = pytest.mark.live


@pytest.mark.skipif(
    not os.getenv("SOCIAL_FEED_BASE_URL"),
    reason="Set SOCIAL_FEED_BASE_URL to run live cluster tests",
)
def test_live_demo_flow():
    base_url = os.environ["SOCIAL_FEED_BASE_URL"].rstrip("/")
    run_id = uuid4().hex[:8]
    host_header = os.getenv("SOCIAL_FEED_HOST_HEADER")
    headers = {"Host": host_header} if host_header else None

    with httpx.Client(base_url=base_url, timeout=30.0, headers=headers) as client:
        alice = client.post("/users", json={"username": f"alice-{run_id}"})
        bob = client.post("/users", json={"username": f"bob-{run_id}"})
        carol = client.post("/users", json={"username": f"carol-{run_id}"})

        assert alice.status_code == 201
        assert bob.status_code == 201
        assert carol.status_code == 201

        alice_id = alice.json()["user_id"]
        bob_id = bob.json()["user_id"]
        carol_id = carol.json()["user_id"]

        assert (
            client.post(
                "/follow",
                json={"follower_id": bob_id, "followed_id": alice_id},
            ).status_code
            == 201
        )
        assert (
            client.post(
                "/follow",
                json={"follower_id": carol_id, "followed_id": alice_id},
            ).status_code
            == 201
        )

        first_post = client.post("/posts", json={"user_id": alice_id, "body": "Hello world"})
        second_post = client.post("/posts", json={"user_id": alice_id, "body": "Second post"})
        assert first_post.status_code == 201
        assert second_post.status_code == 201

        alice_posts = client.get(f"/users/{alice_id}/posts", params={"limit": 50})
        bob_feed = client.get(f"/users/{bob_id}/feed", params={"limit": 50})
        carol_feed = client.get(f"/users/{carol_id}/feed", params={"limit": 50})
        limited_feed = client.get(f"/users/{bob_id}/feed", params={"limit": 1})

        assert alice_posts.status_code == 200
        assert bob_feed.status_code == 200
        assert carol_feed.status_code == 200
        assert limited_feed.status_code == 200

        assert [item["body"] for item in alice_posts.json()] == ["Second post", "Hello world"]
        assert [item["body"] for item in bob_feed.json()] == ["Second post", "Hello world"]
        assert [item["body"] for item in carol_feed.json()] == ["Second post", "Hello world"]
        assert [item["body"] for item in limited_feed.json()] == ["Second post"]
