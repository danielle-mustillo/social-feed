from __future__ import annotations

import logging
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
from app.tracing import get_request_trace_context

cassandra_logger = logging.getLogger("social_feed.cassandra")


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
        self._ensure_soft_delete_schema()
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
            "INSERT INTO users (user_id, username, deleted_at) VALUES (?, ?, ?)"
        )
        self._select_user = self._session.prepare(
            "SELECT user_id, username, deleted_at FROM users WHERE user_id = ?"
        )
        self._select_all_users = self._session.prepare(
            "SELECT user_id, username, deleted_at FROM users"
        )
        self._soft_delete_user = self._session.prepare(
            "UPDATE users SET deleted_at = ? WHERE user_id = ?"
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

    def _ensure_soft_delete_schema(self) -> None:
        rows = self._session.execute(
            "SELECT column_name FROM system_schema.columns "
            "WHERE keyspace_name = %s AND table_name = 'users'",
            (self._settings.cassandra_keyspace,),
        )
        columns = {row["column_name"] for row in rows}
        if "deleted_at" not in columns:
            self._session.execute("ALTER TABLE users ADD deleted_at timestamp")

    def _execute(self, statement, parameters=None, operation: str = "query"):
        context = get_request_trace_context()
        if not context.trace_enabled:
            return self._session.execute(statement, parameters)

        future = self._session.execute_async(statement, parameters=parameters, trace=True)
        result = future.result()
        query_trace = future.get_query_trace(
            max_wait=self._settings.cassandra_trace_max_wait_seconds
        )
        self._log_query_trace(operation, statement, query_trace)
        return result

    def _log_query_trace(self, operation: str, statement, query_trace) -> None:
        if query_trace is None:
            cassandra_logger.warning(
                "cassandra_trace_missing operation=%s statement=%s",
                operation,
                self._statement_text(statement),
            )
            return

        context = get_request_trace_context()
        duration_ms = self._duration_ms(query_trace.duration)
        statement_text = self._statement_text(statement)
        cassandra_logger.info(
            "cassandra_trace request_id=%s method=%s path=%s operation=%s coordinator=%s trace_id=%s duration_ms=%.2f statement=%s",
            context.request_id,
            context.method,
            context.path,
            operation,
            query_trace.coordinator,
            query_trace.trace_id,
            duration_ms,
            statement_text,
        )

        if self._settings.cassandra_trace_log_events:
            for event in query_trace.events:
                elapsed_ms = self._duration_ms(event.source_elapsed)
                cassandra_logger.info(
                    "cassandra_trace_event request_id=%s operation=%s source=%s elapsed_ms=%s thread=%s description=%s",
                    context.request_id,
                    operation,
                    event.source,
                    f"{elapsed_ms:.2f}" if elapsed_ms is not None else "-",
                    event.thread_name,
                    event.description,
                )

    @staticmethod
    def _duration_ms(duration) -> float:
        if duration is None:
            return None
        if hasattr(duration, "total_seconds"):
            return duration.total_seconds() * 1000
        return float(duration) / 1000

    @staticmethod
    def _statement_text(statement) -> str:
        query_string = getattr(statement, "query_string", str(statement))
        return " ".join(query_string.split())

    def create_user(self, username: str) -> UserResponse:
        user = UserResponse(user_id=uuid4(), username=username)
        self._execute(
            self._insert_user,
            (user.user_id, user.username, None),
            operation="create_user.insert_user",
        )
        return user

    def get_user(self, user_id: UUID) -> UserResponse | None:
        row = self._execute(
            self._select_user,
            (user_id,),
            operation="get_user.select_user",
        ).one()
        if row is None or row["deleted_at"] is not None:
            return None
        return UserResponse(user_id=row["user_id"], username=row["username"])

    def list_users(self) -> list[UserResponse]:
        rows = self._execute(
            self._select_all_users,
            operation="list_users.select_all_users",
        )
        return [
            UserResponse(user_id=row["user_id"], username=row["username"])
            for row in rows
            if row["deleted_at"] is None
        ]

    def user_exists(self, user_id: UUID) -> bool:
        return self.get_user(user_id) is not None

    def soft_delete_user(self, user_id: UUID) -> bool:
        row = self._execute(
            self._select_user,
            (user_id,),
            operation="soft_delete_user.select_user",
        ).one()
        if row is None or row["deleted_at"] is not None:
            return False
        self._execute(
            self._soft_delete_user,
            (datetime.now(timezone.utc), user_id),
            operation="soft_delete_user.mark_deleted",
        )
        return True

    def create_follow(self, follower_id: UUID, followed_id: UUID) -> FollowResponse:
        followed_at = datetime.now(timezone.utc)
        self._execute(
            self._insert_follow,
            (followed_id, follower_id, followed_at),
            operation="create_follow.insert_follow",
        )
        return FollowResponse(
            follower_id=follower_id,
            followed_id=followed_id,
            followed_at=followed_at,
        )

    def get_followers(
        self,
        user_id: UUID,
        operation: str = "get_followers.select_followers",
    ) -> list[UUID]:
        rows = self._execute(
            self._select_followers,
            (user_id,),
            operation=operation,
        )
        return [
            row["follower_id"]
            for row in rows
            if self.user_exists(row["follower_id"])
        ]

    def get_follower_relationships(self, user_id: UUID) -> list[FollowResponse]:
        rows = self._execute(
            self._select_follower_relationships,
            (user_id,),
            operation="get_follower_relationships.select_relationships",
        )
        return [
            FollowResponse(
                follower_id=row["follower_id"],
                followed_id=user_id,
                followed_at=row["followed_at"],
            )
            for row in rows
            if self.user_exists(row["follower_id"])
        ]

    def create_post(
        self, user_id: UUID, post_id: UUID, post_time: UUID, body: str
    ) -> PostResponse:
        self._execute(
            self._insert_post,
            (user_id, post_time, post_id, body),
            operation="create_post.insert_post",
        )
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
        self._execute(
            self._insert_feed_item,
            (user_id, event_time, actor_id, post_id, body),
            operation="create_post.feed_fanout",
        )

    def get_user_posts(self, user_id: UUID, limit: int) -> list[PostResponse]:
        rows = self._execute(
            self._select_posts,
            (user_id, limit),
            operation="get_user_posts.select_posts",
        )
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
        rows = self._execute(
            self._select_feed,
            (user_id, limit),
            operation="get_user_feed.select_feed",
        )
        return [
            FeedItemResponse(
                event_time=timeuuid_to_datetime(row["event_time"]),
                actor_id=row["actor_id"],
                post_id=row["post_id"],
                body=row["body"],
            )
            for row in rows
            if self.user_exists(row["actor_id"])
        ]

    def reset(self) -> None:
        self._execute("TRUNCATE feed_by_user", operation="reset.truncate_feed")
        self._execute("TRUNCATE posts_by_user", operation="reset.truncate_posts")
        self._execute(
            "TRUNCATE followers_by_user", operation="reset.truncate_followers"
        )
        self._execute("TRUNCATE users", operation="reset.truncate_users")

    def close(self) -> None:
        self._session.shutdown()
        self._cluster.shutdown()
