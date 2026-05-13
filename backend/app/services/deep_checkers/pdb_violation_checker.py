"""PodDisruptionBudget violations.

A PDB is "violated" when ``status.currentHealthy < status.desiredHealthy`` or
``disruptionsAllowed == 0`` with ``expectedPods > minAvailable``. That
combination blocks ``kubectl drain`` and voluntary disruptions, which
operators usually notice only when a node upgrade hangs.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from kubernetes import client

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class PdbViolationChecker(DeepBaseChecker):
    check_type = "pdb_violation"
    label = "PDB Violations"
    description = "PodDisruptionBudget currentHealthy < desiredHealthy 또는 disruptionsAllowed=0"
    default_params = {"exclude_namespaces": []}
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        self._ensure_k8s_config()
        policy = client.PolicyV1Api()
        exclude = set(self.params.get("exclude_namespaces") or [])

        pdbs = policy.list_pod_disruption_budget_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for pdb in pdbs:
            ns = pdb.metadata.namespace
            if ns in exclude:
                continue
            status = pdb.status
            if status is None:
                continue
            current = status.current_healthy or 0
            desired = status.desired_healthy or 0
            disruptions_allowed = status.disruptions_allowed or 0
            expected = status.expected_pods or 0
            unhealthy = current < desired
            drain_blocked = disruptions_allowed == 0 and expected > 0
            if not (unhealthy or drain_blocked):
                continue
            offenders.append(
                {
                    "namespace": ns,
                    "name": pdb.metadata.name,
                    "current_healthy": current,
                    "desired_healthy": desired,
                    "disruptions_allowed": disruptions_allowed,
                    "expected_pods": expected,
                    "reason": "unhealthy" if unhealthy else "drain_blocked",
                }
            )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {
            "total": len(pdbs),
            "offender_count": len(offenders),
            "offenders": offenders[:50],
        }
        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"PDB 위반 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"PDB 위반 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"PDB {len(pdbs)}개 모두 정상",
            response_time_ms=elapsed,
            details=details,
        )
