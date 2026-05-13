"""Node pressure conditions — DiskPressure / MemoryPressure / PIDPressure /
NetworkUnavailable / Ready=False (excluded from NodeChecker which counts but
doesn't surface which condition fired)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


_PRESSURE_TYPES = ("DiskPressure", "MemoryPressure", "PIDPressure", "NetworkUnavailable")


class NodePressureChecker(DeepBaseChecker):
    check_type = "node_pressure"
    label = "Node Pressure"
    description = "Node 의 DiskPressure/MemoryPressure/PIDPressure/NetworkUnavailable 조건 검출"
    default_params = {"include_unschedulable": True}
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {
            "name": "include_unschedulable",
            "type": "boolean",
            "label": "Cordoned (Unschedulable) 노드도 리포트",
        },
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()
        include_unsched = bool(self.params.get("include_unschedulable", True))

        nodes = core.list_node().items
        offenders: list[dict[str, Any]] = []
        for node in nodes:
            name = node.metadata.name
            conds = {c.type: c for c in (node.status.conditions or [])}
            triggered: list[dict[str, Any]] = []
            for ctype in _PRESSURE_TYPES:
                c = conds.get(ctype)
                if c and c.status == "True":
                    triggered.append({"condition": ctype, "message": (c.message or "")[:200]})
            ready = conds.get("Ready")
            if ready and ready.status != "True":
                triggered.append(
                    {"condition": "Ready=False", "message": (ready.message or "")[:200]}
                )
            cordoned = bool(node.spec and node.spec.unschedulable)
            if include_unsched and cordoned:
                triggered.append({"condition": "Cordoned", "message": "spec.unschedulable=true"})
            if triggered:
                offenders.append({"node": name, "conditions": triggered})

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {
            "total_nodes": len(nodes),
            "offender_count": len(offenders),
            "offenders": offenders[:50],
        }

        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"노드 압박 {len(offenders)}대 (threshold critical>={crit_t})",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"노드 압박 {len(offenders)}대",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"노드 {len(nodes)}대 정상",
            response_time_ms=elapsed,
            details=details,
        )
