"""Admission webhook health — Validating / Mutating WebhookConfigurations
that point to a non-existent Service or unresponsive endpoint.

This is a common silent failure mode: a webhook configuration outlives the
controller it points to, and the API server starts rejecting every matching
request with ``failed calling webhook``. We check that each webhook's
``clientConfig.service`` resolves to an actual Service with ready endpoints.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from kubernetes import client

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class WebhookHealthChecker(DeepBaseChecker):
    check_type = "webhook_health"
    label = "Admission Webhook Health"
    description = "Validating/MutatingWebhookConfiguration 이 가리키는 Service 의 존재 + endpoint 검증"
    default_params = {}
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = []

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()
        self._ensure_k8s_config()
        adm = client.AdmissionregistrationV1Api()

        configs = []
        for cfg in adm.list_validating_webhook_configuration().items:
            for wh in cfg.webhooks or []:
                configs.append(("validating", cfg.metadata.name, wh))
        for cfg in adm.list_mutating_webhook_configuration().items:
            for wh in cfg.webhooks or []:
                configs.append(("mutating", cfg.metadata.name, wh))

        offenders: list[dict[str, Any]] = []
        for kind, cfg_name, wh in configs:
            svc_ref = wh.client_config.service if wh.client_config else None
            if svc_ref is None:
                continue
            ns, name = svc_ref.namespace, svc_ref.name
            problem = None
            ready_addrs = 0
            try:
                core.read_namespaced_service(name, ns)
                ep = core.read_namespaced_endpoints(name, ns)
                for subset in ep.subsets or []:
                    ready_addrs += len(subset.addresses or [])
                if ready_addrs == 0:
                    problem = "service exists but no ready endpoints"
            except client.ApiException as exc:
                if exc.status == 404:
                    problem = "service not found"
                else:
                    problem = f"API error {exc.status}: {(exc.reason or '')[:120]}"
            except Exception as exc:
                problem = f"unexpected error: {str(exc)[:200]}"
            if problem:
                offenders.append(
                    {
                        "kind": kind,
                        "configuration": cfg_name,
                        "webhook": wh.name,
                        "service": f"{ns}/{name}",
                        "failure_policy": wh.failure_policy,
                        "ready_endpoint_count": ready_addrs,
                        "problem": problem,
                    }
                )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {
            "total_webhooks": len(configs),
            "offender_count": len(offenders),
            "offenders": offenders[:50],
        }
        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"끊긴 admission webhook {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"끊긴 admission webhook {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"Admission webhook {len(configs)}개 모두 정상",
            response_time_ms=elapsed,
            details=details,
        )
