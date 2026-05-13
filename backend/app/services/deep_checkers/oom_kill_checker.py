"""Recent OOMKilled containers — scans pod.status.container_statuses for
``last_state.terminated.reason == "OOMKilled"``. Complements CrashLoopChecker
which keys off CrashLoopBackOff (a pod can be OOM-killed without ever
entering CrashLoop)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class OomKillChecker(DeepBaseChecker):
    check_type = "oom_kill"
    label = "OOM Kill"
    description = "OOMKilled 상태로 종료된 컨테이너 검출 (last_state.terminated)"
    default_params = {
        "exclude_namespaces": [],
        "window_hours": 24,
    }
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
        {"name": "window_hours", "type": "number", "label": "이 시간(시) 이내 OOM 만 보고"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()
        exclude = set(self.params.get("exclude_namespaces") or [])
        cutoff = datetime.now(timezone.utc) - timedelta(
            hours=int(self.params.get("window_hours", 24))
        )

        pods = core.list_pod_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for pod in pods:
            ns = pod.metadata.namespace
            if ns in exclude:
                continue
            for cs in pod.status.container_statuses or []:
                last = getattr(cs.last_state, "terminated", None) if cs.last_state else None
                if not last or last.reason != "OOMKilled":
                    continue
                finished = last.finished_at
                if finished and finished < cutoff:
                    continue
                offenders.append(
                    {
                        "namespace": ns,
                        "pod": pod.metadata.name,
                        "container": cs.name,
                        "exit_code": last.exit_code,
                        "finished_at": finished.isoformat() if finished else None,
                        "restarts": cs.restart_count or 0,
                    }
                )

        elapsed = self._elapsed_ms(start)
        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {"offender_count": len(offenders), "offenders": offenders[:50]}

        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"OOMKilled {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"OOMKilled {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message="최근 OOMKilled 없음",
            response_time_ms=elapsed,
            details=details,
        )
