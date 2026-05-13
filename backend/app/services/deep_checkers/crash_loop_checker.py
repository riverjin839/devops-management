"""CrashLoopBackOff scanner with last-log snippet per offending container."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class CrashLoopChecker(DeepBaseChecker):
    check_type = "crash_loop"
    label = "Crash Loop"
    description = "CrashLoopBackOff 상태의 컨테이너와 마지막 로그 라인 수집"
    default_params = {
        "exclude_namespaces": [],
        "min_restart_count": 5,
        "log_tail_lines": 20,
    }
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
        {"name": "min_restart_count", "type": "number", "label": "재시작 임계 (이 횟수 초과만 보고)"},
        {"name": "log_tail_lines", "type": "number", "label": "수집할 로그 라인 수"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()

        exclude = set(self.params.get("exclude_namespaces") or [])
        min_restarts = int(self.params.get("min_restart_count", 5))
        tail = int(self.params.get("log_tail_lines", 20))

        pods = core.list_pod_for_all_namespaces().items
        offenders: list[dict[str, Any]] = []
        for pod in pods:
            ns = pod.metadata.namespace
            if ns in exclude:
                continue
            for cs in pod.status.container_statuses or []:
                waiting = getattr(cs.state, "waiting", None) if cs.state else None
                in_crashloop = waiting and waiting.reason == "CrashLoopBackOff"
                restarts = cs.restart_count or 0
                if not in_crashloop and restarts < min_restarts:
                    continue
                last_log = self._tail_log(core, ns, pod.metadata.name, cs.name, tail)
                offenders.append(
                    {
                        "namespace": ns,
                        "pod": pod.metadata.name,
                        "container": cs.name,
                        "restarts": restarts,
                        "reason": waiting.reason if waiting else None,
                        "last_log_tail": last_log,
                    }
                )

        elapsed = self._elapsed_ms(start)

        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {"offender_count": len(offenders), "offenders": offenders[:30]}

        if len(offenders) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"CrashLoop/잦은 재시작 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(offenders) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"CrashLoop/잦은 재시작 {len(offenders)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message="CrashLoop 없음",
            response_time_ms=elapsed,
            details=details,
        )

    @staticmethod
    def _tail_log(core, namespace: str, pod: str, container: str, tail: int) -> str:
        try:
            return core.read_namespaced_pod_log(
                name=pod,
                namespace=namespace,
                container=container,
                tail_lines=tail,
                previous=True,
            ) or ""
        except Exception:
            try:
                return core.read_namespaced_pod_log(
                    name=pod,
                    namespace=namespace,
                    container=container,
                    tail_lines=tail,
                ) or ""
            except Exception as exc:
                return f"(log unavailable: {exc})"
