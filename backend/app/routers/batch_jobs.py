"""Batch job registration + execution.

Pattern (extending with new job types):
  1. Add a `BatchJobExecutor` subclass under `app/services/batch_jobs/`.
  2. Decorate it with `@register_executor`.
  3. Import it from `app/services/batch_jobs/__init__.py` so the registration
     side-effect runs.
That's it — `GET /api/v1/batch-jobs/types` will surface it and the existing
CRUD/run endpoints work unchanged.
"""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import BatchJob, BatchJobRun, Cluster
from app.schemas.batch_job import (
    BatchJobCreate,
    BatchJobListResponse,
    BatchJobResponse,
    BatchJobRunListResponse,
    BatchJobRunRequest,
    BatchJobRunResponse,
    BatchJobTypeListResponse,
    BatchJobUpdate,
)
from app.services.batch_job_service import (
    BatchJobNotFound,
    UnknownJobType,
    execute_job,
    get_job_or_404,
)
from app.services.batch_jobs import get_executor, list_executors
from app.services.secrets import encrypt_secret

router = APIRouter(prefix="/batch-jobs", tags=["batch-jobs"])


def _to_response(job: BatchJob) -> dict:
    """Materialize a BatchJob into the response shape (with masked cred flags)."""
    return {
        **{c.name: getattr(job, c.name) for c in BatchJob.__table__.columns
           if c.name not in ("default_password_enc", "default_private_key_enc")},
        "has_default_password": bool(job.default_password_enc),
        "has_default_private_key": bool(job.default_private_key_enc),
    }


# ── job type registry ────────────────────────────────────────────────────────

@router.get("/types", response_model=BatchJobTypeListResponse)
def list_job_types():
    """Registered batch job types — drives the 'New Job' UI."""
    return BatchJobTypeListResponse(data=list_executors())


# ── CRUD ─────────────────────────────────────────────────────────────────────

@router.get("", response_model=BatchJobListResponse)
def list_jobs(
    cluster_id: UUID | None = Query(default=None),
    job_type: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    q = db.query(BatchJob)
    if cluster_id:
        q = q.filter(BatchJob.cluster_id == cluster_id)
    if job_type:
        q = q.filter(BatchJob.job_type == job_type)
    jobs = q.order_by(BatchJob.created_at.desc()).all()
    return BatchJobListResponse(data=[_to_response(j) for j in jobs])


@router.post("", response_model=BatchJobResponse, status_code=status.HTTP_201_CREATED)
def create_job(payload: BatchJobCreate, db: Session = Depends(get_db)):
    if not db.query(Cluster).filter(Cluster.id == payload.cluster_id).first():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Cluster not found")
    if get_executor(payload.job_type) is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown job_type '{payload.job_type}'. See GET /batch-jobs/types.",
        )

    data = payload.model_dump()
    plain_password = data.pop("default_password", None)
    plain_key = data.pop("default_private_key", None)
    job = BatchJob(**data)
    if plain_password:
        job.default_password_enc = encrypt_secret(plain_password)
    if plain_key:
        job.default_private_key_enc = encrypt_secret(plain_key)
    db.add(job)
    db.commit()
    db.refresh(job)
    return _to_response(job)


@router.get("/{job_id}", response_model=BatchJobResponse)
def get_job(job_id: UUID, db: Session = Depends(get_db)):
    try:
        return _to_response(get_job_or_404(db, job_id))
    except BatchJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BatchJob not found")


@router.put("/{job_id}", response_model=BatchJobResponse)
def update_job(job_id: UUID, payload: BatchJobUpdate, db: Session = Depends(get_db)):
    try:
        job = get_job_or_404(db, job_id)
    except BatchJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BatchJob not found")

    update_data = payload.model_dump(exclude_unset=True)
    # Special-case credential fields: empty string clears, non-empty re-encrypts,
    # unset leaves the existing ciphertext alone.
    if "default_password" in update_data:
        plain = update_data.pop("default_password")
        job.default_password_enc = encrypt_secret(plain) if plain else None
    if "default_private_key" in update_data:
        plain = update_data.pop("default_private_key")
        job.default_private_key_enc = encrypt_secret(plain) if plain else None
    for field, value in update_data.items():
        setattr(job, field, value)
    db.commit()
    db.refresh(job)
    return _to_response(job)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: UUID, db: Session = Depends(get_db)):
    try:
        job = get_job_or_404(db, job_id)
    except BatchJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BatchJob not found")
    db.delete(job)
    db.commit()
    return None


# ── execution + run history ──────────────────────────────────────────────────

@router.post("/{job_id}/run", response_model=BatchJobRunResponse)
async def run_job(job_id: UUID, payload: BatchJobRunRequest, db: Session = Depends(get_db)):
    try:
        job = get_job_or_404(db, job_id)
    except BatchJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BatchJob not found")

    if not payload.password and not payload.private_key:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="password 또는 private_key 중 하나는 필수입니다.",
        )

    try:
        run, _ = await execute_job(
            db,
            job,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            password=payload.password,
            private_key=payload.private_key,
            param_override=payload.param_override,
            timeout=payload.timeout,
            trigger="manual",
        )
    except UnknownJobType as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown job_type '{exc}'.",
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    return run


@router.delete("/{job_id}/credentials", response_model=BatchJobResponse)
def clear_job_credentials(job_id: UUID, db: Session = Depends(get_db)):
    """Drop stored encrypted credentials for scheduled execution."""
    try:
        job = get_job_or_404(db, job_id)
    except BatchJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BatchJob not found")
    job.default_password_enc = None
    job.default_private_key_enc = None
    db.commit()
    db.refresh(job)
    return _to_response(job)


@router.get("/{job_id}/runs", response_model=BatchJobRunListResponse)
def list_runs(
    job_id: UUID,
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    try:
        get_job_or_404(db, job_id)
    except BatchJobNotFound:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BatchJob not found")

    runs = (
        db.query(BatchJobRun)
        .filter(BatchJobRun.job_id == job_id)
        .order_by(BatchJobRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return BatchJobRunListResponse(data=runs)


@router.get("/runs/{run_id}", response_model=BatchJobRunResponse)
def get_run(run_id: UUID, db: Session = Depends(get_db)):
    run = db.query(BatchJobRun).filter(BatchJobRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run
