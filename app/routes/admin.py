from __future__ import annotations

from fastapi import APIRouter, Depends

from app.dependencies import get_repository
from app.models import ResetResponse

router = APIRouter(tags=["admin"])


@router.post("/admin/reset", response_model=ResetResponse)
async def reset_data(
    repository=Depends(get_repository),
) -> ResetResponse:
    repository.reset()
    return ResetResponse(status="reset")
