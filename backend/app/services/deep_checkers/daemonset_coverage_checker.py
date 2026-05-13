"""DaemonSet coverage — pods missing on some nodes."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class DaemonSetCoverageChecker(DeepBaseChecker):
    check_type = "daemonset_coverage"
    label = "DaemonSet Coverage"
    description = "DaemonSet desired vs currentNumberScheduled / numberReady 불일치 검출"
    default_params = {"exclude_namespaces": []}
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        apps = self.apps_v1()
        exclude = set(self.params.get("exclude_namespaces") or [])

        daemonsets = apps.list_daemon_set_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for ds in daemonsets:
            ns = ds.metadata.namespace
            if ns in exclude:
                continue
            status = ds.status
            desired = status.desired_number_scheduled or 0
            current = status.current_number_scheduled or 0
            ready = status.number_ready or 0
            misscheduled = status.number_misscheduled or 0
            if desired == 0:
                continue
            if current < desired or ready < desired or misscheduled > 0:
                offenders.append(
                    {
                        "namespace": ns,
                        "name": ds.metadata.name,
                        "desired": desired,
                        "current": current,
                        "ready": ready,
                        "available": status.number_available or 0,
                        "misscheduled": misscheduled,
                    }
                )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {
            "total": len(daemonsets),
            "offender_count": len(offenders),
            "offenders": offenders[:50],
        }
        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"DaemonSet 커버리지 부족 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"DaemonSet 커버리지 부족 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"DaemonSet {len(daemonsets)}개 모두 정상",
            response_time_ms=elapsed,
            details=details,
        )
