"""Failed Jobs in a sliding window."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from kubernetes import client

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class JobFailureChecker(DeepBaseChecker):
    check_type = "job_failure"
    label = "Job Failure"
    description = "최근 윈도우 내 Failed Job 또는 backoffLimit 초과 Job"
    default_params = {
        "exclude_namespaces": [],
        "window_hours": 24,
    }
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
        {"name": "window_hours", "type": "number", "label": "조회 윈도우(시)"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        self._ensure_k8s_config()
        batch = client.BatchV1Api()

        exclude = set(self.params.get("exclude_namespaces") or [])
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=int(self.params.get("window_hours", 24))
        )

        jobs = batch.list_job_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for job in jobs:
            ns = job.metadata.namespace
            if ns in exclude:
                continue
            status = job.status
            if not status:
                continue
            failed = status.failed or 0
            if failed == 0:
                continue
            # Prefer completionTime/startTime/conditions[lastTransitionTime].
            ts = (
                status.completion_time
                or status.start_time
                or (status.conditions[-1].last_transition_time if status.conditions else None)
            )
            if ts and ts < cutoff:
                continue
            failed_cond = next(
                (c for c in (status.conditions or []) if c.type == "Failed" and c.status == "True"),
                None,
            )
            offenders.append(
                {
                    "namespace": ns,
                    "name": job.metadata.name,
                    "failed": failed,
                    "succeeded": status.succeeded or 0,
                    "active": status.active or 0,
                    "reason": failed_cond.reason if failed_cond else None,
                    "message": (failed_cond.message if failed_cond else None) or None,
                    "completion_time": (
                        status.completion_time.isoformat() if status.completion_time else None
                    ),
                }
            )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {
            "total_jobs_scanned": len(jobs),
            "offender_count": len(offenders),
            "offenders": offenders[:50],
        }
        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"Failed Job {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"Failed Job {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message="최근 Failed Job 없음",
            response_time_ms=elapsed,
            details=details,
        )
