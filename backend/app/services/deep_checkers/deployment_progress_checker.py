"""Deployment progress — Available=False or Progressing=False (RollbackFailed,
ProgressDeadlineExceeded)."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class DeploymentProgressChecker(DeepBaseChecker):
    check_type = "deployment_progress"
    label = "Deployment Progress"
    description = "Deployment Available=False 또는 Progressing=False (ProgressDeadlineExceeded 등)"
    default_params = {"exclude_namespaces": []}
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        apps = self.apps_v1()
        exclude = set(self.params.get("exclude_namespaces") or [])

        deployments = apps.list_deployment_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for dep in deployments:
            ns = dep.metadata.namespace
            if ns in exclude:
                continue
            problems: list[dict[str, Any]] = []
            for c in dep.status.conditions or []:
                if c.type == "Available" and c.status != "True":
                    problems.append(
                        {
                            "type": "Available",
                            "reason": c.reason,
                            "message": (c.message or "")[:200],
                        }
                    )
                if c.type == "Progressing" and c.status != "True":
                    problems.append(
                        {
                            "type": "Progressing",
                            "reason": c.reason,
                            "message": (c.message or "")[:200],
                        }
                    )
            if problems:
                offenders.append(
                    {
                        "namespace": ns,
                        "name": dep.metadata.name,
                        "replicas": dep.status.replicas or 0,
                        "ready_replicas": dep.status.ready_replicas or 0,
                        "available_replicas": dep.status.available_replicas or 0,
                        "problems": problems,
                    }
                )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {
            "total": len(deployments),
            "offender_count": len(offenders),
            "offenders": offenders[:50],
        }
        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"Deployment 이슈 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"Deployment 이슈 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"Deployment {len(deployments)}개 정상",
            response_time_ms=elapsed,
            details=details,
        )
