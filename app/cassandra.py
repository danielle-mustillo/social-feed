from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID, uuid4

from cassandra import InvalidRequest, OperationTimedOut
from cassandra.cluster import Cluster, NoHostAvailable
from cassandra.query import dict_factory

from app.config import Settings
from app.models import (
    FeedItemResponse,
    FollowResponse,
    PostResponse,
    UserResponse,
    timeuuid_to_datetime,
)


class CassandraRepository:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cluster = Cluster(
            contact_points=list(settings.cassandra_contact_points),
            port=settings.cassandra_port,
            connect_timeout=settings.cassandra_connect_timeout,
        )
        self._session = self._connect()
        self._session.row_factory = dict_factory
        self._session.default_timeout = settings.cassandra_request_timeout
        self._prepare_statements()

    def _connect(self):
        last_error: Exception | None = None
        for _ in range(self._settings.cassandra_connect_retries):
            session = None
            try:
                session = self._cluster.connect()
                session.execute("SELECT release_version FROM system.local")
                session.set_keyspace(self._settings.cassandra_keyspace)
                return session
            except (NoHostAvailable, OperationTimedOut, InvalidRequest) as exc:
                last_error = exc
                if session is not None:
                    session.shutdown()
                time.sleep(self._settings.cassandra_retry_delay_seconds)

        raise RuntimeError(
            f"Unable to connect to Cassandra keyspace {self._settings.cassandra_keyspace}"
        ) from last_error

    def _prepare_statements(self) -> None:
        self._insert_user = self._session.prepare(
            "INSERT INTO users (user_id, username) VALUES (?, ?)"
        )
        self._select_user = self._session.prepare(
            "SELECT user_id, username FROM users WHERE user_id = ?"
        )
        self._select_all_users = self._session.prepare(
            "SELECT user_id, username FROM users"
        )
        self._insert_follow = self._session.prepare(
            "INSERT INTO followers_by_user (user_id, follower_id, followed_at) "
            "VALUES (?, ?, ?)"
        )
        self._select_followers = self._session.prepare(
            "SELECT follower_id FROM followers_by_user WHERE user_id = ?"
        )
        self._select_follower_relationships = self._session.prepare(
            "SELECT follower_id, followed_at FROM followers_by_user WHERE user_id = ?"
        )
        self._insert_post = self._session.prepare(
            "INSERT INTO posts_by_user (user_id, post_time, post_id, body) "
            "VALUES (?, ?, ?, ?)"
        )
        self._select_posts = self._session.prepare(
            "SELECT user_id, post_time, post_id, body FROM posts_by_user "
            "WHERE user_id = ? LIMIT ?"
        )
        self._insert_feed_item = self._session.prepare(
            "INSERT INTO feed_by_user (user_id, event_time, actor_id, post_id, body) "
            "VALUES (?, ?, ?, ?, ?)"
        )
        self._select_feed = self._session.prepare(
            "SELECT event_time, actor_id, post_id, body FROM feed_by_user "
            "WHERE user_id = ? LIMIT ?"
        )

    def create_user(self, username: str) -> UserResponse:
        user = UserResponse(user_id=uuid4(), username=username)
        self._session.execute(self._insert_user, (user.user_id, user.username))
        return user

    def get_user(self, user_id: UUID) -> UserResponse | None:
        row = self._session.execute(self._select_user, (user_id,)).one()
        if row is None:
            return None
        return UserResponse(user_id=row["user_id"], username=row["username"])

    def list_users(self) -> list[UserResponse]:
        rows = self._session.execute(self._select_all_users)
        return [
            UserResponse(user_id=row["user_id"], username=row["username"])
            for row in rows
        ]

    def user_exists(self, user_id: UUID) -> bool:
        return self.get_user(user_id) is not None

    def create_follow(self, follower_id: UUID, followed_id: UUID) -> FollowResponse:
        followed_at = datetime.now(timezone.utc)
        self._session.execute(
            self._insert_follow,
            (followed_id, follower_id, followed_at),
        )
        return FollowResponse(
            follower_id=follower_id,
            followed_id=followed_id,
            followed_at=followed_at,
        )

    def get_followers(self, user_id: UUID) -> list[UUID]:
        rows = self._session.execute(self._select_followers, (user_id,))
        return [row["follower_id"] for row in rows]

    def get_follower_relationships(self, user_id: UUID) -> list[FollowResponse]:
        rows = self._session.execute(self._select_follower_relationships, (user_id,))
        return [
            FollowResponse(
                follower_id=row["follower_id"],
                followed_id=user_id,
                followed_at=row["followed_at"],
            )
            for row in rows
        ]

    def create_post(
        self, user_id: UUID, post_id: UUID, post_time: UUID, body: str
    ) -> PostResponse:
        self._session.execute(self._insert_post, (user_id, post_time, post_id, body))
        return PostResponse(
            post_id=post_id,
            user_id=user_id,
            body=body,
            post_time=timeuuid_to_datetime(post_time),
        )

    def add_feed_item(
        self,
        user_id: UUID,
        event_time: UUID,
        actor_id: UUID,
        post_id: UUID,
        body: str,
    ) -> None:
        self._session.execute(
            self._insert_feed_item,
            (user_id, event_time, actor_id, post_id, body),
        )

    def get_user_posts(self, user_id: UUID, limit: int) -> list[PostResponse]:
        rows = self._session.execute(self._select_posts, (user_id, limit))
        return [
            PostResponse(
                post_id=row["post_id"],
                user_id=row["user_id"],
                body=row["body"],
                post_time=timeuuid_to_datetime(row["post_time"]),
            )
            for row in rows
        ]

    def get_user_feed(self, user_id: UUID, limit: int) -> list[FeedItemResponse]:
        rows = self._session.execute(self._select_feed, (user_id, limit))
        return [
            FeedItemResponse(
                event_time=timeuuid_to_datetime(row["event_time"]),
                actor_id=row["actor_id"],
                post_id=row["post_id"],
                body=row["body"],
            )
            for row in rows
        ]

    def reset(self) -> None:
        self._session.execute("TRUNCATE feed_by_user")
        self._session.execute("TRUNCATE posts_by_user")
        self._session.execute("TRUNCATE followers_by_user")
        self._session.execute("TRUNCATE users")

    def close(self) -> None:
        self._session.shutdown()
        self._cluster.shutdown()
