"""Service endpoint health — Services whose Endpoints object has no ready
addresses. A non-headless ClusterIP Service with 0 ready endpoints is a
client-side black hole.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class EndpointHealthChecker(DeepBaseChecker):
    check_type = "endpoint_health"
    label = "Service Endpoint Health"
    description = "Service 가 매칭하는 Endpoints 에 ready address 가 0 인 경우 검출"
    default_params = {
        "exclude_namespaces": ["kube-system"],
        "exclude_service_types": ["ExternalName"],
        "require_selector": True,
    }
    default_thresholds = {"warning": 1, "critical": 5}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
        {"name": "exclude_service_types", "type": "string[]", "label": "제외할 Service type"},
        {
            "name": "require_selector",
            "type": "boolean",
            "label": "Selector 없는 Service(headless 등) 제외",
        },
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()

        exclude_ns = set(self.params.get("exclude_namespaces") or [])
        exclude_types = set(self.params.get("exclude_service_types") or [])
        require_selector = bool(self.params.get("require_selector", True))

        services = core.list_service_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for svc in services:
            ns = svc.metadata.namespace
            if ns in exclude_ns:
                continue
            if svc.spec.type in exclude_types:
                continue
            if require_selector and not svc.spec.selector:
                continue
            try:
                ep = core.read_namespaced_endpoints(svc.metadata.name, ns)
            except Exception:
                ep = None
            ready_addrs = 0
            not_ready_addrs = 0
            for subset in (ep.subsets if ep else None) or []:
                ready_addrs += len(subset.addresses or [])
                not_ready_addrs += len(subset.not_ready_addresses or [])
            if ready_addrs == 0:
                offenders.append(
                    {
                        "namespace": ns,
                        "name": svc.metadata.name,
                        "type": svc.spec.type,
                        "selector": svc.spec.selector,
                        "ready_addresses": 0,
                        "not_ready_addresses": not_ready_addrs,
                    }
                )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 5))
        details = {
            "total_services_scanned": len(services),
            "offender_count": len(offenders),
            "offenders": offenders[:50],
        }
        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"Endpoint 비어있는 Service {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"Endpoint 비어있는 Service {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message="모든 Service 에 ready endpoint 존재",
            response_time_ms=elapsed,
            details=details,
        )
