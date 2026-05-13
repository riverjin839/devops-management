"""Deep check results + AI review.

A ``DeepCheckResult`` row is created **at most once per DailyCheckLog**. Phase 1
populates only the AI fields (``ai_status`` / ``ai_summary`` / ``ai_remediation``
/ ``trend_summary``) by running ``review_service`` over the existing shallow
check result. Phase 2 adds deep-check execution which fills the ``results`` /
``errors`` / ``source`` columns.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship

from app.database import Base


class DeepCheckSource(str, enum.Enum):
    in_cluster = "in_cluster"
    centralized = "centralized"


class AiReviewStatus(str, enum.Enum):
    pending = "pending"
    ok = "ok"
    offline = "offline"
    error = "error"


class DeepCheckResult(Base):
    """Per-DailyCheckLog AI review (Phase 1) + deep-check execution (Phase 2)."""

    __tablename__ = "deep_check_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("clusters.id"), nullable=False)
    daily_check_log_id = Column(
        UUID(as_uuid=True), ForeignKey("daily_check_logs.id"), nullable=False, unique=True
    )

    source = Column(Enum(DeepCheckSource), nullable=True)

    # Per-checker JSONB results. Shape: {check_type: {status, message, details, response_time_ms}}
    results = Column(JSONB, nullable=True)
    errors = Column(JSONB, nullable=True)

    # AI review (Phase 1)
    ai_status = Column(Enum(AiReviewStatus), nullable=False, default=AiReviewStatus.pending)
    ai_summary = Column(Text, nullable=True)
    ai_remediation = Column(JSONB, nullable=True)  # list[{title, command?, description}]
    ai_model = Column(String(128), nullable=True)
    ai_error = Column(Text, nullable=True)

    # Trend / diff summary vs previous run (last_24h)
    trend_summary = Column(JSONB, nullable=True)  # {prev_status, status_changed, new_errors, resolved_errors}

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    cluster = relationship("Cluster", backref="deep_check_results")
    daily_check_log = relationship("DailyCheckLog", backref="deep_check_result", uselist=False)

    def __repr__(self):
        return (
            f"<DeepCheckResult(daily_check_log_id={self.daily_check_log_id}, "
            f"ai_status={self.ai_status})>"
        )
