from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ai_learning.app.core.config import Settings, get_settings

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, bool]


@router.get(
    "/live",
    response_model=LivenessResponse,
    summary="Check process liveness",
)
async def live(
    settings: Annotated[Settings, Depends(get_settings)],
) -> LivenessResponse:
    return LivenessResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "model": ReadinessResponse,
            "description": "Required server-side configuration is missing.",
        }
    },
    summary="Check application readiness",
)
async def ready(
    settings: Annotated[Settings, Depends(get_settings)],
) -> ReadinessResponse | JSONResponse:
    checks = settings.readiness_checks()
    is_ready = all(checks.values())
    response = ReadinessResponse(
        status="ready" if is_ready else "not_ready",
        checks=checks,
    )

    if is_ready:
        return response

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=response.model_dump(),
    )
