from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from uuid import UUID

from app.dependencies import get_fanout_service, get_repository
from app.models import PostCreate, PostResponse
from app.services.fanout import FanoutService

router = APIRouter(tags=["posts"])


@router.post("/posts", response_model=PostResponse, status_code=201)
async def create_post(
    payload: PostCreate,
    fanout_service: FanoutService = Depends(get_fanout_service),
) -> PostResponse:
    return fanout_service.create_post(user_id=payload.user_id, body=payload.body)


@router.get("/posts", response_model=list[PostResponse])
async def list_posts(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    repository=Depends(get_repository),
) -> list[PostResponse]:
    if not repository.user_exists(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return repository.get_user_posts(user_id=user_id, limit=limit)


@router.get("/users/{user_id}/posts", response_model=list[PostResponse])
async def get_user_posts(
    user_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    repository=Depends(get_repository),
) -> list[PostResponse]:
    if not repository.user_exists(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return repository.get_user_posts(user_id=user_id, limit=limit)
