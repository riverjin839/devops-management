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

from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, Integer, String, Text
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


class DeepCheckDefinition(Base):
    """User-editable deep check definition.

    Modeled after ``metric_cards``: built-in defaults are seeded on first
    startup, but the UI can add/edit/disable rows freely. The ``check_type``
    column is the lookup key into ``services.deep_checkers.registry`` for
    the actual checker class; ``params`` / ``thresholds`` are passed in.
    """

    __tablename__ = "deep_check_definitions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # NULL = global definition applied to every cluster.
    cluster_id = Column(UUID(as_uuid=True), ForeignKey("clusters.id"), nullable=True)

    check_type = Column(String(64), nullable=False)  # matches registry key
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    schedule_cron = Column(String(120), nullable=True)  # optional per-definition override
    thresholds = Column(JSONB, nullable=True)  # {warning: ..., critical: ...}
    params = Column(JSONB, nullable=True)      # checker-specific params
    sort_order = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    cluster = relationship("Cluster", backref="deep_check_definitions")

    def __repr__(self):
        return f"<DeepCheckDefinition(name={self.name}, type={self.check_type})>"


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
