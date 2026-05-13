"""Deep-check + AI review API."""
from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.config import settings
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
# Separate router for endpoints called by the in-cluster super pod; mounted
# WITHOUT the global JWT dependency. Auth is by shared bearer token in the
# Authorization header, validated below.
public_router = APIRouter(prefix="/deep-check", tags=["Deep Check (public)"])


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


class DeepCheckDefinitionCreate(BaseModel):
    cluster_id: Optional[UUID] = None
    check_type: str
    name: str
    description: Optional[str] = None
    enabled: bool = True
    schedule_cron: Optional[str] = None
    thresholds: Optional[dict] = None
    params: Optional[dict] = None
    sort_order: int = 0


class DeepCheckDefinitionUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None
    schedule_cron: Optional[str] = None
    thresholds: Optional[dict] = None
    params: Optional[dict] = None
    sort_order: Optional[int] = None


@router.post("/definitions", response_model=DeepCheckDefinitionResponse, status_code=201)
async def create_definition(
    payload: DeepCheckDefinitionCreate,
    db: Session = Depends(get_db),
):
    from app.services.deep_checkers.registry import get_checker_class

    if get_checker_class(payload.check_type) is None:
        raise HTTPException(status_code=400, detail=f"Unknown check_type: {payload.check_type}")
    row = DeepCheckDefinition(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/definitions/{definition_id}", response_model=DeepCheckDefinitionResponse)
async def update_definition(
    definition_id: UUID,
    payload: DeepCheckDefinitionUpdate,
    db: Session = Depends(get_db),
):
    row = db.query(DeepCheckDefinition).filter(DeepCheckDefinition.id == definition_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Definition not found")
    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/definitions/{definition_id}", status_code=204)
async def delete_definition(
    definition_id: UUID,
    db: Session = Depends(get_db),
):
    row = db.query(DeepCheckDefinition).filter(DeepCheckDefinition.id == definition_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Definition not found")
    db.delete(row)
    db.commit()
    return None


class DeepCheckTestResponse(BaseModel):
    check_type: str
    status: str
    message: str
    response_time_ms: int
    details: Optional[dict] = None


@router.post("/definitions/{definition_id}/test", response_model=DeepCheckTestResponse)
async def test_definition(
    definition_id: UUID,
    cluster_id: UUID,
    db: Session = Depends(get_db),
):
    """Run a single checker against the chosen cluster — no persistence."""
    from app.services.deep_checkers.registry import get_checker_class

    row = db.query(DeepCheckDefinition).filter(DeepCheckDefinition.id == definition_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Definition not found")
    cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
    if cluster is None:
        raise HTTPException(status_code=404, detail="Cluster not found")
    cls = get_checker_class(row.check_type)
    if cls is None:
        raise HTTPException(status_code=400, detail=f"Unknown check_type: {row.check_type}")

    checker = cls(cluster, params=row.params, thresholds=row.thresholds, db=db)
    res = checker.safe_check()
    return DeepCheckTestResponse(
        check_type=row.check_type,
        status=res.status.value,
        message=res.message,
        response_time_ms=res.response_time_ms,
        details=res.details,
    )


# ----------------------------- Trend ------------------------------------

class TrendPoint(BaseModel):
    checked_at: datetime
    overall_status: str
    ready_nodes: int
    total_nodes: int
    error_count: int
    warning_count: int


@router.get("/trend/{cluster_id}", response_model=list[TrendPoint])
async def get_trend(
    cluster_id: UUID,
    days: int = 7,
    db: Session = Depends(get_db),
):
    """Time-series of daily check status for charting (last ``days`` days)."""
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = (
        db.query(DailyCheckLog)
        .filter(
            DailyCheckLog.cluster_id == cluster_id,
            DailyCheckLog.checked_at >= cutoff,
        )
        .order_by(DailyCheckLog.checked_at.asc())
        .all()
    )
    return [
        TrendPoint(
            checked_at=row.checked_at,
            overall_status=row.overall_status.value if row.overall_status else "pending",
            ready_nodes=row.ready_nodes or 0,
            total_nodes=row.total_nodes or 0,
            error_count=len(row.error_messages or []),
            warning_count=len(row.warning_messages or []),
        )
        for row in rows
    ]


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


# ----------------------------- Ingest (public, token-auth) --------------

class IngestPayload(BaseModel):
    cluster_id: UUID
    source: DeepCheckSource = DeepCheckSource.in_cluster
    checked_at: Optional[datetime] = None
    results: dict[str, dict]
    errors: Optional[list[dict]] = Field(default=None)


def _require_ingest_token(authorization: Optional[str] = Header(default=None)) -> None:
    expected = settings.superpod_ingest_token
    if not expected:
        raise HTTPException(status_code=503, detail="Ingest disabled — SUPERPOD_INGEST_TOKEN not set")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    if authorization.split(" ", 1)[1] != expected:
        raise HTTPException(status_code=401, detail="Invalid ingest token")


@public_router.post("/ingest", response_model=DeepCheckResultResponse)
async def ingest_deep_check(
    payload: IngestPayload,
    db: Session = Depends(get_db),
    _: None = Depends(_require_ingest_token),
):
    """Receive a deep-check payload pushed by an in-cluster super pod.

    The payload is attached to the most recent DailyCheckLog for the
    cluster, mirroring the centralized path. The user-configured thresholds
    on each ``DeepCheckDefinition`` are still authoritative — we just
    persist the results as-is from the pod (which used registry defaults).
    """
    cluster = db.query(Cluster).filter(Cluster.id == payload.cluster_id).first()
    if not cluster:
        raise HTTPException(status_code=404, detail="Cluster not found")

    log = (
        db.query(DailyCheckLog)
        .filter(DailyCheckLog.cluster_id == cluster.id)
        .order_by(desc(DailyCheckLog.checked_at))
        .first()
    )
    if log is None:
        raise HTTPException(
            status_code=409,
            detail="DailyCheckLog 가 없습니다. 먼저 일일 점검을 실행하세요.",
        )

    row = (
        db.query(DeepCheckResult)
        .filter(DeepCheckResult.daily_check_log_id == log.id)
        .first()
    )
    if row is None:
        row = DeepCheckResult(
            cluster_id=cluster.id,
            daily_check_log_id=log.id,
            ai_status=AiReviewStatus.pending,
        )
        db.add(row)

    row.source = payload.source
    row.results = payload.results
    row.errors = payload.errors

    db.commit()
    db.refresh(row)

    deep_check_service._schedule_review(log.id)
    return row
