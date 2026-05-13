"""Notification channels for daily-check review fan-out."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class NotificationChannelType(str, enum.Enum):
    slack = "slack"
    email = "email"
    webhook = "webhook"
    k8s_event = "k8s_event"


class NotificationSeverity(str, enum.Enum):
    healthy = "healthy"
    warning = "warning"
    critical = "critical"


class NotificationStatus(str, enum.Enum):
    ok = "ok"
    failed = "failed"
    skipped = "skipped"


class NotificationChannel(Base):
    """User-configured destination for daily-check / deep-check notifications."""

    __tablename__ = "notification_channels"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("clusters.id"), nullable=True)

    name = Column(String(200), nullable=False)
    type = Column(Enum(NotificationChannelType), nullable=False)
    enabled = Column(Boolean, nullable=False, default=True)

    # Severity threshold — only notify when the daily-check overall_status is
    # at or above this level (rank: healthy < warning < critical).
    min_severity = Column(
        Enum(NotificationSeverity), nullable=False, default=NotificationSeverity.warning
    )

    # Channel-specific config (Slack webhook url, SMTP recipients, etc.)
    config = Column(JSONB, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    cluster = relationship("Cluster", backref="notification_channels")

    def __repr__(self):
        return f"<NotificationChannel(name={self.name}, type={self.type})>"


class NotificationLog(Base):
    """Audit log of notification attempts."""

    __tablename__ = "notification_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("notification_channels.id"), nullable=False)
    daily_check_log_id = Column(
        UUID(as_uuid=True), ForeignKey("daily_check_logs.id"), nullable=True
    )

    status = Column(Enum(NotificationStatus), nullable=False)
    severity = Column(Enum(NotificationSeverity), nullable=True)
    subject = Column(String(500), nullable=True)
    message = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    channel = relationship("NotificationChannel", backref="logs")
