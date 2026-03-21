from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from uuid import UUID, uuid1, uuid4

from app.models import (
    FeedItemResponse,
    FollowersResponse,
    FollowResponse,
    PostResponse,
    UserResponse,
    timeuuid_to_datetime,
)


class SocialFeedRepository(Protocol):
    def create_user(self, username: str) -> UserResponse: ...

    def get_user(self, user_id: UUID) -> UserResponse | None: ...

    def list_users(self) -> list[UserResponse]: ...

    def user_exists(self, user_id: UUID) -> bool: ...

    def create_follow(self, follower_id: UUID, followed_id: UUID) -> FollowResponse: ...

    def get_followers(self, user_id: UUID) -> list[UUID]: ...

    def get_follower_relationships(self, user_id: UUID) -> list[FollowResponse]: ...

    def create_post(
        self, user_id: UUID, post_id: UUID, post_time: UUID, body: str
    ) -> PostResponse: ...

    def add_feed_item(
        self,
        user_id: UUID,
        event_time: UUID,
        actor_id: UUID,
        post_id: UUID,
        body: str,
    ) -> None: ...

    def get_user_posts(self, user_id: UUID, limit: int) -> list[PostResponse]: ...

    def get_user_feed(self, user_id: UUID, limit: int) -> list[FeedItemResponse]: ...

    def reset(self) -> None: ...

    def close(self) -> None: ...


class InMemoryRepository:
    def __init__(self) -> None:
        self._lock = RLock()
        self._users: dict[UUID, UserResponse] = {}
        self._followers: dict[UUID, dict[UUID, datetime]] = defaultdict(dict)
        self._posts: dict[UUID, list[PostResponse]] = defaultdict(list)
        self._feed: dict[UUID, list[FeedItemResponse]] = defaultdict(list)

    def create_user(self, username: str) -> UserResponse:
        with self._lock:
            user = UserResponse(user_id=uuid4(), username=username)
            self._users[user.user_id] = user
            return user

    def get_user(self, user_id: UUID) -> UserResponse | None:
        with self._lock:
            return self._users.get(user_id)

    def list_users(self) -> list[UserResponse]:
        with self._lock:
            return list(self._users.values())

    def user_exists(self, user_id: UUID) -> bool:
        with self._lock:
            return user_id in self._users

    def create_follow(self, follower_id: UUID, followed_id: UUID) -> FollowResponse:
        followed_at = datetime.now(timezone.utc)
        with self._lock:
            self._followers[followed_id][follower_id] = followed_at
            return FollowResponse(
                follower_id=follower_id,
                followed_id=followed_id,
                followed_at=followed_at,
            )

    def get_followers(self, user_id: UUID) -> list[UUID]:
        with self._lock:
            return list(self._followers[user_id].keys())

    def get_follower_relationships(self, user_id: UUID) -> list[FollowResponse]:
        with self._lock:
            return [
                FollowResponse(
                    follower_id=follower_id,
                    followed_id=user_id,
                    followed_at=followed_at,
                )
                for follower_id, followed_at in self._followers[user_id].items()
            ]

    def create_post(
        self, user_id: UUID, post_id: UUID, post_time: UUID, body: str
    ) -> PostResponse:
        post = PostResponse(
            post_id=post_id,
            user_id=user_id,
            body=body,
            post_time=timeuuid_to_datetime(post_time),
        )
        with self._lock:
            self._posts[user_id].insert(0, post)
        return post

    def add_feed_item(
        self,
        user_id: UUID,
        event_time: UUID,
        actor_id: UUID,
        post_id: UUID,
        body: str,
    ) -> None:
        item = FeedItemResponse(
            event_time=timeuuid_to_datetime(event_time),
            actor_id=actor_id,
            post_id=post_id,
            body=body,
        )
        with self._lock:
            self._feed[user_id].insert(0, item)

    def get_user_posts(self, user_id: UUID, limit: int) -> list[PostResponse]:
        with self._lock:
            return list(self._posts[user_id][:limit])

    def get_user_feed(self, user_id: UUID, limit: int) -> list[FeedItemResponse]:
        with self._lock:
            return list(self._feed[user_id][:limit])

    def reset(self) -> None:
        with self._lock:
            self._users.clear()
            self._followers.clear()
            self._posts.clear()
            self._feed.clear()

    def close(self) -> None:
        return None


def new_post_identity() -> tuple[UUID, UUID]:
    return uuid4(), uuid1()
