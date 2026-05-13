"""PVC health: list PVCs, flag Pending/Lost; report orphan PVs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class PvcHealthChecker(DeepBaseChecker):
    check_type = "pvc_health"
    label = "PVC Health"
    description = "Pending/Lost PVC, orphan PV 검출"
    default_params = {"include_namespaces": [], "exclude_namespaces": []}
    default_thresholds = {"warning": 1, "critical": 5}
    param_schema = [
        {"name": "include_namespaces", "type": "string[]", "label": "포함할 네임스페이스 (비우면 전체)"},
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()

        include = set(self.params.get("include_namespaces") or [])
        exclude = set(self.params.get("exclude_namespaces") or [])

        pvcs = core.list_persistent_volume_claim_for_all_namespaces().items
        problematic: list[dict[str, Any]] = []
        for pvc in pvcs:
            ns = pvc.metadata.namespace
            if include and ns not in include:
                continue
            if ns in exclude:
                continue
            phase = pvc.status.phase
            if phase not in ("Bound",):
                problematic.append(
                    {
                        "namespace": ns,
                        "name": pvc.metadata.name,
                        "phase": phase,
                        "storage_class": pvc.spec.storage_class_name,
                        "requested": (
                            pvc.spec.resources.requests.get("storage")
                            if pvc.spec.resources and pvc.spec.resources.requests
                            else None
                        ),
                    }
                )

        # Orphan PVs (Released without claim or Available aged) — best-effort.
        pvs = core.list_persistent_volume().items
        orphans = [
            {"name": pv.metadata.name, "phase": pv.status.phase}
            for pv in pvs
            if pv.status.phase in ("Released", "Failed")
        ]

        elapsed = self._elapsed_ms(start)

        details = {
            "total_pvcs": len(pvcs),
            "problematic": problematic[:50],
            "orphan_pvs": orphans[:50],
        }

        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 5))
        problem_count = len(problematic) + len(orphans)

        if problem_count >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"PVC 이슈 {problem_count}건 (threshold critical>={crit_t})",
                response_time_ms=elapsed,
                details=details,
            )
        if problem_count >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"PVC 이슈 {problem_count}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"PVCs OK ({len(pvcs)}개)",
            response_time_ms=elapsed,
            details=details,
        )
