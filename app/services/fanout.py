from __future__ import annotations

from fastapi import HTTPException, status
from uuid import UUID

from app.models import PostResponse
from app.repository import SocialFeedRepository, new_post_identity


class FanoutService:
    def __init__(self, repository: SocialFeedRepository) -> None:
        self._repository = repository

    def create_post(self, user_id: UUID, body: str) -> PostResponse:
        if not self._repository.user_exists(user_id):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        post_id, post_time = new_post_identity()
        post = self._repository.create_post(
            user_id=user_id,
            post_id=post_id,
            post_time=post_time,
            body=body,
        )

        for follower_id in self._repository.get_followers(
            user_id,
            operation="create_post.fetch_followers",
        ):
            self._repository.add_feed_item(
                user_id=follower_id,
                event_time=post_time,
                actor_id=user_id,
                post_id=post_id,
                body=body,
            )

        return post
