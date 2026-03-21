from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_reset_clears_data(client):
    alice = await client.post("/users", json={"username": "alice"})
    assert alice.status_code == 201

    before_reset = await client.get("/users")
    assert before_reset.status_code == 200
    assert len(before_reset.json()) == 1

    reset = await client.post("/admin/reset")
    assert reset.status_code == 200
    assert reset.json() == {"status": "reset"}

    after_reset = await client.get("/users")
    assert after_reset.status_code == 200
    assert after_reset.json() == []
