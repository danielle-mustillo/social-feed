from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from pydantic import BaseModel, Field

UUID_EPOCH_OFFSET_100NS = 0x01B21DD213814000


def timeuuid_to_datetime(value: UUID) -> datetime:
    if value.version != 1:
        raise ValueError("Expected a version 1 UUID for timeuuid conversion")
    timestamp_100ns = value.time - UUID_EPOCH_OFFSET_100NS
    return datetime.fromtimestamp(timestamp_100ns / 10_000_000, tz=timezone.utc)


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=50)


class UserResponse(BaseModel):
    user_id: UUID
    username: str


class FollowCreate(BaseModel):
    follower_id: UUID
    followed_id: UUID


class FollowResponse(BaseModel):
    follower_id: UUID
    followed_id: UUID
    followed_at: datetime


class FollowersResponse(BaseModel):
    user_id: UUID
    followers: list[FollowResponse]


class PostCreate(BaseModel):
    user_id: UUID
    body: str = Field(min_length=1, max_length=280)


class PostResponse(BaseModel):
    post_id: UUID
    user_id: UUID
    body: str
    post_time: datetime


class FeedItemResponse(BaseModel):
    event_time: datetime
    actor_id: UUID
    post_id: UUID
    body: str


class HealthResponse(BaseModel):
    status: str


class ResetResponse(BaseModel):
    status: str
