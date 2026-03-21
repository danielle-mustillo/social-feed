from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from uuid import UUID

from app.dependencies import get_repository
from app.models import FollowCreate, FollowersResponse, FollowResponse

router = APIRouter(tags=["follow"])


@router.post("/follow", response_model=FollowResponse, status_code=201)
async def follow_user(
    payload: FollowCreate,
    repository=Depends(get_repository),
) -> FollowResponse:
    if not repository.user_exists(payload.follower_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Follower user not found",
        )
    if not repository.user_exists(payload.followed_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Followed user not found",
        )

    return repository.create_follow(
        follower_id=payload.follower_id,
        followed_id=payload.followed_id,
    )


@router.get("/follow", response_model=FollowersResponse)
async def get_followers(
    followed_id: UUID = Query(...),
    repository=Depends(get_repository),
) -> FollowersResponse:
    if not repository.user_exists(followed_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    return FollowersResponse(
        user_id=followed_id,
        followers=repository.get_follower_relationships(followed_id),
    )
