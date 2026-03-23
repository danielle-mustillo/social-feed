from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from uuid import UUID

from app.dependencies import get_repository
from app.models import UserCreate, UserResponse

router = APIRouter(tags=["users"])


@router.post("/users", response_model=UserResponse, status_code=201)
async def create_user(
    payload: UserCreate,
    repository=Depends(get_repository),
) -> UserResponse:
    return repository.create_user(payload.username)


@router.get("/users", response_model=list[UserResponse])
async def list_users(
    repository=Depends(get_repository),
) -> list[UserResponse]:
    return repository.list_users()


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: UUID,
    repository=Depends(get_repository),
) -> UserResponse:
    user = repository.get_user(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return user


@router.delete("/users/{user_id}", status_code=204)
async def delete_user(
    user_id: UUID,
    repository=Depends(get_repository),
) -> Response:
    if not repository.soft_delete_user(user_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
