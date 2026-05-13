"""Deep check orchestrator.

Reads ``DeepCheckDefinition`` rows (global + per-cluster), instantiates the
registered checker class for each, executes them in sequence and persists
the aggregated output on ``DeepCheckResult`` linked to the most recent
``DailyCheckLog`` for the cluster.

Phase 2a: runs from the backend pod using stored kubeconfig (centralized).
Phase 2b: same service can be invoked from inside the cluster via the super
pod runner — the source is recorded in ``DeepCheckResult.source``.
"""
from __future__ import annotations

import logging
import time
from typing import Iterable, Optional
from uuid import UUID

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import Cluster, DailyCheckLog, StatusEnum
from app.models.deep_check import (
    AiReviewStatus,
    DeepCheckDefinition,
    DeepCheckResult,
    DeepCheckSource,
)
from app.services.deep_checkers.registry import get_checker_class

logger = logging.getLogger(__name__)


_STATUS_RANK = {
    StatusEnum.healthy: 0,
    StatusEnum.pending: 1,
    StatusEnum.warning: 2,
    StatusEnum.critical: 3,
}


class DeepCheckService:
    """One-shot deep check execution + persistence."""

    def run_for_cluster(
        self,
        db: Session,
        cluster_id: str | UUID,
        *,
        source: DeepCheckSource = DeepCheckSource.centralized,
        definitions: Optional[Iterable[DeepCheckDefinition]] = None,
    ) -> DeepCheckResult:
        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            raise ValueError(f"Cluster not found: {cluster_id}")

        defs = list(definitions) if definitions is not None else self._enabled_definitions(db, cluster_id)
        results: dict[str, dict] = {}
        errors: list[dict] = []
        worst = StatusEnum.healthy

        for definition in defs:
            cls = get_checker_class(definition.check_type)
            if cls is None:
                errors.append(
                    {
                        "definition_id": str(definition.id),
                        "check_type": definition.check_type,
                        "error": "unknown check_type (no registered checker)",
                    }
                )
                continue
            start = time.time()
            checker = cls(
                cluster,
                params=definition.params,
                thresholds=definition.thresholds,
                db=db,
            )
            res = checker.safe_check()
            duration_ms = int((time.time() - start) * 1000)
            results[definition.check_type] = {
                "definition_id": str(definition.id),
                "name": definition.name,
                "label": cls.label,
                "status": res.status.value,
                "message": res.message,
                "response_time_ms": res.response_time_ms or duration_ms,
                "details": res.details,
            }
            if _STATUS_RANK[res.status] > _STATUS_RANK[worst]:
                worst = res.status

        log = (
            db.query(DailyCheckLog)
            .filter(DailyCheckLog.cluster_id == cluster.id)
            .order_by(desc(DailyCheckLog.checked_at))
            .first()
        )
        if log is None:
            raise ValueError(
                "DailyCheckLog 가 없습니다. 먼저 daily check 를 실행한 뒤 deep check 를 실행하세요."
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

        row.source = source
        row.results = results
        row.errors = errors or None

        db.commit()
        db.refresh(row)

        # Re-run AI review now that deep results are persisted — fire-and-forget
        # so the caller doesn't have to wait on Ollama.
        self._schedule_review(log.id)
        return row

    @staticmethod
    def _enabled_definitions(db: Session, cluster_id: str | UUID) -> list[DeepCheckDefinition]:
        return (
            db.query(DeepCheckDefinition)
            .filter(
                DeepCheckDefinition.enabled.is_(True),
                (DeepCheckDefinition.cluster_id == cluster_id)
                | (DeepCheckDefinition.cluster_id.is_(None)),
            )
            .order_by(DeepCheckDefinition.sort_order.asc())
            .all()
        )

    @staticmethod
    def _schedule_review(daily_check_log_id) -> None:
        try:
            from app.celery_app import run_review_and_notify

            run_review_and_notify.delay(str(daily_check_log_id))
        except Exception:
            logger.exception("Failed to schedule AI review for %s", daily_check_log_id)


deep_check_service = DeepCheckService()
