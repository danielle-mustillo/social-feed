from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_demo_flow(client):
    alice = await client.post("/users", json={"username": "alice"})
    bob = await client.post("/users", json={"username": "bob"})
    carol = await client.post("/users", json={"username": "carol"})

    assert alice.status_code == 201
    assert bob.status_code == 201
    assert carol.status_code == 201

    alice_id = alice.json()["user_id"]
    bob_id = bob.json()["user_id"]
    carol_id = carol.json()["user_id"]

    follow_bob = await client.post(
        "/follow",
        json={"follower_id": bob_id, "followed_id": alice_id},
    )
    follow_carol = await client.post(
        "/follow",
        json={"follower_id": carol_id, "followed_id": alice_id},
    )

    assert follow_bob.status_code == 201
    assert follow_carol.status_code == 201

    first_post = await client.post(
        "/posts",
        json={"user_id": alice_id, "body": "Hello world"},
    )
    second_post = await client.post(
        "/posts",
        json={"user_id": alice_id, "body": "Second post"},
    )
    assert first_post.status_code == 201
    assert second_post.status_code == 201

    alice_posts = await client.get(f"/users/{alice_id}/posts", params={"limit": 50})
    top_level_posts = await client.get("/posts", params={"user_id": alice_id, "limit": 50})
    bob_feed = await client.get(f"/users/{bob_id}/feed", params={"limit": 50})
    top_level_feed = await client.get("/feed", params={"user_id": bob_id, "limit": 50})
    carol_feed = await client.get(f"/users/{carol_id}/feed", params={"limit": 50})
    limited_feed = await client.get(f"/users/{bob_id}/feed", params={"limit": 1})
    users = await client.get("/users")
    alice_user = await client.get(f"/users/{alice_id}")
    alice_followers = await client.get("/follow", params={"followed_id": alice_id})

    assert alice_posts.status_code == 200
    assert top_level_posts.status_code == 200
    assert bob_feed.status_code == 200
    assert top_level_feed.status_code == 200
    assert carol_feed.status_code == 200
    assert limited_feed.status_code == 200
    assert users.status_code == 200
    assert alice_user.status_code == 200
    assert alice_followers.status_code == 200

    assert [item["body"] for item in alice_posts.json()] == ["Second post", "Hello world"]
    assert [item["body"] for item in top_level_posts.json()] == ["Second post", "Hello world"]
    assert [item["body"] for item in bob_feed.json()] == ["Second post", "Hello world"]
    assert [item["body"] for item in top_level_feed.json()] == ["Second post", "Hello world"]
    assert [item["body"] for item in carol_feed.json()] == ["Second post", "Hello world"]
    assert [item["body"] for item in limited_feed.json()] == ["Second post"]
    assert {item["user_id"] for item in users.json()} == {alice_id, bob_id, carol_id}
    assert alice_user.json()["username"] == "alice"
    assert {item["follower_id"] for item in alice_followers.json()["followers"]} == {
        bob_id,
        carol_id,
    }
