from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from uuid import UUID

from app.dependencies import get_repository
from app.models import FeedItemResponse

router = APIRouter(tags=["feed"])


@router.get("/feed", response_model=list[FeedItemResponse])
async def list_feed(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    repository=Depends(get_repository),
) -> list[FeedItemResponse]:
    if not repository.user_exists(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return repository.get_user_feed(user_id=user_id, limit=limit)


@router.get("/users/{user_id}/feed", response_model=list[FeedItemResponse])
async def get_user_feed(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    repository=Depends(get_repository),
) -> list[FeedItemResponse]:
    if not repository.user_exists(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return repository.get_user_feed(user_id=user_id, limit=limit)
