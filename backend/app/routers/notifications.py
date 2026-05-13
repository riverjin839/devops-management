"""Notification channel CRUD + manual test endpoint."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    NotificationChannel,
    NotificationChannelType,
    NotificationLog,
    NotificationSeverity,
    NotificationStatus,
)
from app.services.notifier import notifier_service


router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationChannelResponse(BaseModel):
    id: UUID
    cluster_id: Optional[UUID]
    name: str
    type: NotificationChannelType
    enabled: bool
    min_severity: NotificationSeverity
    config: Optional[dict]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class NotificationChannelCreate(BaseModel):
    cluster_id: Optional[UUID] = None
    name: str
    type: NotificationChannelType
    enabled: bool = True
    min_severity: NotificationSeverity = NotificationSeverity.warning
    config: Optional[dict] = None


class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    min_severity: Optional[NotificationSeverity] = None
    config: Optional[dict] = None


class NotificationLogResponse(BaseModel):
    id: UUID
    channel_id: UUID
    daily_check_log_id: Optional[UUID]
    status: NotificationStatus
    severity: Optional[NotificationSeverity]
    subject: Optional[str]
    error: Optional[str]
    sent_at: datetime

    class Config:
        from_attributes = True


@router.get("/channels", response_model=list[NotificationChannelResponse])
async def list_channels(
    cluster_id: Optional[UUID] = None,
    enabled_only: bool = False,
    db: Session = Depends(get_db),
):
    q = db.query(NotificationChannel)
    if cluster_id is not None:
        q = q.filter(
            (NotificationChannel.cluster_id == cluster_id)
            | (NotificationChannel.cluster_id.is_(None))
        )
    if enabled_only:
        q = q.filter(NotificationChannel.enabled.is_(True))
    return q.order_by(NotificationChannel.created_at.desc()).all()


@router.post("/channels", response_model=NotificationChannelResponse, status_code=201)
async def create_channel(
    payload: NotificationChannelCreate,
    db: Session = Depends(get_db),
):
    row = NotificationChannel(**payload.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.put("/channels/{channel_id}", response_model=NotificationChannelResponse)
async def update_channel(
    channel_id: UUID,
    payload: NotificationChannelUpdate,
    db: Session = Depends(get_db),
):
    row = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


@router.delete("/channels/{channel_id}", status_code=204)
async def delete_channel(
    channel_id: UUID,
    db: Session = Depends(get_db),
):
    row = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    db.delete(row)
    db.commit()
    return None


@router.post("/test/{channel_id}", response_model=NotificationLogResponse)
async def test_channel(
    channel_id: UUID,
    db: Session = Depends(get_db),
):
    try:
        return notifier_service.test_channel(db, channel_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/log", response_model=list[NotificationLogResponse])
async def list_logs(
    channel_id: Optional[UUID] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(NotificationLog)
    if channel_id is not None:
        q = q.filter(NotificationLog.channel_id == channel_id)
    return q.order_by(desc(NotificationLog.sent_at)).limit(limit).all()
