"""HorizontalPodAutoscaler health — autoscaling/v2 status.conditions."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from kubernetes import client

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class HpaHealthChecker(DeepBaseChecker):
    check_type = "hpa_health"
    label = "HPA Health"
    description = "HPA 의 AbleToScale / ScalingActive / ScalingLimited 조건 검출 (metrics-server 부재 등)"
    default_params = {"exclude_namespaces": []}
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        self._ensure_k8s_config()
        autoscaling = client.AutoscalingV2Api()
        exclude = set(self.params.get("exclude_namespaces") or [])

        hpas = autoscaling.list_horizontal_pod_autoscaler_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for hpa in hpas:
            ns = hpa.metadata.namespace
            if ns in exclude:
                continue
            problems: list[dict[str, Any]] = []
            for cond in hpa.status.conditions or []:
                if cond.type in ("AbleToScale", "ScalingActive") and cond.status != "True":
                    problems.append(
                        {
                            "type": cond.type,
                            "reason": cond.reason,
                            "message": (cond.message or "")[:200],
                        }
                    )
            if problems:
                offenders.append(
                    {
                        "namespace": ns,
                        "name": hpa.metadata.name,
                        "target": (
                            f"{hpa.spec.scale_target_ref.kind}/{hpa.spec.scale_target_ref.name}"
                            if hpa.spec and hpa.spec.scale_target_ref
                            else None
                        ),
                        "current_replicas": hpa.status.current_replicas,
                        "desired_replicas": hpa.status.desired_replicas,
                        "problems": problems,
                    }
                )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {
            "total_hpas": len(hpas),
            "offender_count": len(offenders),
            "offenders": offenders[:50],
        }

        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"HPA 이슈 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"HPA 이슈 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"HPA {len(hpas)}개 정상",
            response_time_ms=elapsed,
            details=details,
        )
