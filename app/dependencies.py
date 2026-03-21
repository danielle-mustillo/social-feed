from __future__ import annotations

from fastapi import Depends, Request

from app.services.fanout import FanoutService


async def get_repository(request: Request):
    return request.app.state.repository


async def get_fanout_service(
    repository=Depends(get_repository),
) -> FanoutService:
    return FanoutService(repository)
