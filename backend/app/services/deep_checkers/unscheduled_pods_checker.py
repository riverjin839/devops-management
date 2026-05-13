"""Pods stuck in Pending due to scheduling failures.

Looks at `pod.status.conditions` for PodScheduled=False, and falls back to
PodScheduled missing while phase=Pending and no container has started.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class UnscheduledPodsChecker(DeepBaseChecker):
    check_type = "unscheduled_pods"
    label = "Unscheduled Pods"
    description = "Pending 상태에서 PodScheduled=False 로 스케줄링 실패한 파드 검출"
    default_params = {
        "exclude_namespaces": [],
        "min_age_seconds": 120,
    }
    default_thresholds = {"warning": 1, "critical": 5}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
        {"name": "min_age_seconds", "type": "number", "label": "이 시간(초) 이상 Pending 만 보고"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()

        exclude = set(self.params.get("exclude_namespaces") or [])
        min_age = int(self.params.get("min_age_seconds", 120))
        now = datetime.now(timezone.utc)

        pods = core.list_pod_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for pod in pods:
            ns = pod.metadata.namespace
            if ns in exclude:
                continue
            if pod.status.phase != "Pending":
                continue
            created = pod.metadata.creation_timestamp
            if created and (now - created).total_seconds() < min_age:
                continue
            sched_cond = next(
                (c for c in (pod.status.conditions or []) if c.type == "PodScheduled"),
                None,
            )
            if sched_cond and sched_cond.status == "True":
                continue
            reason = sched_cond.reason if sched_cond else "Unknown"
            message = (sched_cond.message if sched_cond else "no PodScheduled condition")
            offenders.append(
                {
                    "namespace": ns,
                    "pod": pod.metadata.name,
                    "reason": reason,
                    "message": (message or "")[:300],
                    "age_seconds": int((now - created).total_seconds()) if created else None,
                }
            )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 5))
        details = {"offender_count": len(offenders), "offenders": offenders[:50]}

        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"스케줄 실패 {len(offenders)}건 (>={crit_t})",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"스케줄 실패 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message="Pending 스케줄 이슈 없음",
            response_time_ms=elapsed,
            details=details,
        )
