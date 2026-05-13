"""Namespaces stuck in Terminating phase past a threshold age — usually means
a finalizer is wedged on some resource within the namespace."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class StuckNamespaceChecker(DeepBaseChecker):
    check_type = "stuck_namespace"
    label = "Stuck Namespace"
    description = "Terminating 상태로 오래 머무는 네임스페이스 검출 (finalizer 잠김)"
    default_params = {"min_age_seconds": 600}
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {
            "name": "min_age_seconds",
            "type": "number",
            "label": "Terminating 상태 최소 시간(초) — 이 시간 초과만 보고",
        },
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()
        min_age = int(self.params.get("min_age_seconds", 600))
        now = datetime.now(timezone.utc)

        namespaces = core.list_namespace().items
        offenders: list[dict[str, Any]] = []
        for ns in namespaces:
            if ns.status.phase != "Terminating":
                continue
            deletion_ts = ns.metadata.deletion_timestamp
            if not deletion_ts:
                continue
            age = (now - deletion_ts).total_seconds()
            if age < min_age:
                continue
            offenders.append(
                {
                    "name": ns.metadata.name,
                    "deletion_timestamp": deletion_ts.isoformat(),
                    "age_seconds": int(age),
                    "finalizers": list(ns.spec.finalizers or []) if ns.spec else [],
                }
            )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {
            "total": len(namespaces),
            "offender_count": len(offenders),
            "offenders": offenders,
        }
        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"Terminating 정체 네임스페이스 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"Terminating 정체 네임스페이스 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message="Terminating 정체 없음",
            response_time_ms=elapsed,
            details=details,
        )
