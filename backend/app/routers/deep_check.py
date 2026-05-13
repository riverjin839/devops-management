"""Deep-check + AI review API."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Cluster, DailyCheckLog
from app.models.deep_check import (
    AiReviewStatus,
    DeepCheckDefinition,
    DeepCheckResult,
    DeepCheckSource,
)
from app.services.deep_check_service import deep_check_service
from app.services.deep_checkers.registry import describe_check_types
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


# ----------------------------- Deep check execution ---------------------

class DeepCheckDefinitionResponse(BaseModel):
    id: UUID
    cluster_id: Optional[UUID]
    check_type: str
    name: str
    description: Optional[str]
    enabled: bool
    schedule_cron: Optional[str]
    thresholds: Optional[dict]
    params: Optional[dict]
    sort_order: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DeepCheckTypeSchema(BaseModel):
    check_type: str
    label: str
    description: str
    default_params: dict
    default_thresholds: dict
    param_schema: list[dict]


@router.get("/check-types", response_model=list[DeepCheckTypeSchema])
async def list_check_types():
    """Available deep checker types + UI form schema."""
    return describe_check_types()


@router.get("/definitions", response_model=list[DeepCheckDefinitionResponse])
async def list_definitions(
    cluster_id: Optional[UUID] = None,
    enabled_only: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(DeepCheckDefinition)
    if cluster_id is not None:
        q = q.filter(
            (DeepCheckDefinition.cluster_id == cluster_id)
            | (DeepCheckDefinition.cluster_id.is_(None))
        )
    if enabled_only:
        q = q.filter(DeepCheckDefinition.enabled.is_(True))
    return q.order_by(DeepCheckDefinition.sort_order.asc()).all()


class DeepCheckResultResponse(BaseModel):
    id: UUID
    cluster_id: UUID
    daily_check_log_id: UUID
    source: Optional[DeepCheckSource]
    results: Optional[dict]
    errors: Optional[Any]
    ai_status: AiReviewStatus
    ai_summary: Optional[str]
    ai_remediation: Optional[list[RemediationStep]] = None
    ai_model: Optional[str]
    trend_summary: Optional[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


@router.post("/run/{cluster_id}", response_model=DeepCheckResultResponse)
async def run_deep_check(
    cluster_id: UUID,
    db: Session = Depends(get_db),
):
    """Trigger an immediate centralized deep check for the cluster."""
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")
    try:
        row = deep_check_service.run_for_cluster(
            db, cluster_id, source=DeepCheckSource.centralized
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return row


@router.get("/results/{cluster_id}/latest", response_model=Optional[DeepCheckResultResponse])
async def get_latest_result(
    cluster_id: UUID,
    db: Session = Depends(get_db),
):
    row = (
        db.query(DeepCheckResult)
        .filter(DeepCheckResult.cluster_id == cluster_id)
        .order_by(desc(DeepCheckResult.updated_at))
        .first()
    )
    return row
