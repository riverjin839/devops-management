"""CronJob health — suspended jobs and stale last-success."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from kubernetes import client

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class CronJobHealthChecker(DeepBaseChecker):
    check_type = "cronjob_health"
    label = "CronJob Health"
    description = "Suspended CronJob 또는 마지막 성공 실행이 임계 이상 지난 CronJob"
    default_params = {
        "exclude_namespaces": [],
        "stale_after_hours": 48,
        "include_suspended": True,
    }
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
        {"name": "stale_after_hours", "type": "number", "label": "이 시간(시) 이상 미성공 = 이슈"},
        {"name": "include_suspended", "type": "boolean", "label": "Suspended CronJob 도 보고"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        self._ensure_k8s_config()
        batch = client.BatchV1Api()

        exclude = set(self.params.get("exclude_namespaces") or [])
        stale_after = timedelta(hours=int(self.params.get("stale_after_hours", 48)))
        include_susp = bool(self.params.get("include_suspended", True))
        now = datetime.now(timezone.utc)

        cronjobs = batch.list_cron_job_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for cj in cronjobs:
            ns = cj.metadata.namespace
            if ns in exclude:
                continue
            suspended = bool(cj.spec.suspend) if cj.spec else False
            last_succ = cj.status.last_successful_time if cj.status else None
            created = cj.metadata.creation_timestamp
            reasons: list[str] = []
            if suspended and include_susp:
                reasons.append("suspended")
            if not suspended:
                # Only count stale-success if the CronJob has been alive long enough to have run.
                age_threshold = created and (now - created) > stale_after
                if last_succ is None and age_threshold:
                    reasons.append("never_succeeded")
                elif last_succ and (now - last_succ) > stale_after:
                    reasons.append("last_success_stale")
            if not reasons:
                continue
            offenders.append(
                {
                    "namespace": ns,
                    "name": cj.metadata.name,
                    "schedule": cj.spec.schedule if cj.spec else None,
                    "suspended": suspended,
                    "last_successful_time": last_succ.isoformat() if last_succ else None,
                    "reasons": reasons,
                }
            )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {
            "total": len(cronjobs),
            "offender_count": len(offenders),
            "offenders": offenders[:50],
        }
        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"CronJob 이슈 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"CronJob 이슈 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"CronJob {len(cronjobs)}개 정상",
            response_time_ms=elapsed,
            details=details,
        )
