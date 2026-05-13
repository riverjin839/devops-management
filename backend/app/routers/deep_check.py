"""Deep-check + AI review API.

Phase 1 exposes only the review endpoints. Phase 2 will extend this with
``/deep-check/run``, ``/deep-check/results``, ``/deep-check/ingest`` etc.
"""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import DailyCheckLog
from app.models.deep_check import AiReviewStatus, DeepCheckResult, DeepCheckSource
from app.services.review_service import review_service


router = APIRouter(prefix="/deep-check", tags=["Deep Check"])


# ----------------------------- Schemas ----------------------------------

class RemediationStep(BaseModel):
    title: str
    command: Optional[str] = None
    description: Optional[str] = None


class DeepCheckReviewResponse(BaseModel):
    id: UUID
    cluster_id: UUID
    daily_check_log_id: UUID
    source: Optional[DeepCheckSource] = None
    results: Optional[dict] = None
    errors: Optional[Any] = None
    ai_status: AiReviewStatus
    ai_summary: Optional[str]
    ai_remediation: Optional[list[RemediationStep]] = None
    ai_model: Optional[str]
    ai_error: Optional[str]
    trend_summary: Optional[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ----------------------------- Endpoints --------------------------------

@router.get("/review/{daily_check_log_id}", response_model=DeepCheckReviewResponse)
async def get_or_compute_review(
    daily_check_log_id: UUID,
    db: Session = Depends(get_db),
):
    """Return cached AI review for a daily check, computing it on the fly if missing."""
    log = (
        db.query(DailyCheckLog)
        .filter(DailyCheckLog.id == daily_check_log_id)
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="DailyCheckLog not found")

    existing = (
        db.query(DeepCheckResult)
        .filter(DeepCheckResult.daily_check_log_id == daily_check_log_id)
        .first()
    )
    if existing and existing.ai_status == AiReviewStatus.ok:
        return existing

    return await review_service.review_and_persist(db, str(daily_check_log_id))


@router.post("/review/{daily_check_log_id}/recompute", response_model=DeepCheckReviewResponse)
async def recompute_review(
    daily_check_log_id: UUID,
    db: Session = Depends(get_db),
):
    """Force a fresh AI review (ignores cached row)."""
    log = (
        db.query(DailyCheckLog)
        .filter(DailyCheckLog.id == daily_check_log_id)
        .first()
    )
    if not log:
        raise HTTPException(status_code=404, detail="DailyCheckLog not found")

    return await review_service.review_and_persist(
        db, str(daily_check_log_id), force=True
    )
