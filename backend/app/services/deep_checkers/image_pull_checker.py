"""ImagePullBackOff / ErrImagePull scanner."""
from __future__ import annotations

from datetime import datetime

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


_BAD_WAITING_REASONS = {"ImagePullBackOff", "ErrImagePull", "InvalidImageName"}


class ImagePullChecker(DeepBaseChecker):
    check_type = "image_pull"
    label = "Image Pull"
    description = "ImagePullBackOff / ErrImagePull / InvalidImageName 컨테이너 검출"
    default_params = {"exclude_namespaces": []}
    default_thresholds = {"warning": 1, "critical": 3}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()
        exclude = set(self.params.get("exclude_namespaces") or [])

        pods = core.list_pod_for_all_namespaces().items
        failing: list[dict] = []
        for pod in pods:
            ns = pod.metadata.namespace
            if ns in exclude:
                continue
            statuses = list(pod.status.container_statuses or []) + list(
                pod.status.init_container_statuses or []
            )
            for cs in statuses:
                waiting = getattr(cs.state, "waiting", None) if cs.state else None
                if waiting and waiting.reason in _BAD_WAITING_REASONS:
                    failing.append(
                        {
                            "namespace": ns,
                            "pod": pod.metadata.name,
                            "container": cs.name,
                            "reason": waiting.reason,
                            "message": (waiting.message or "")[:300],
                            "image": cs.image,
                        }
                    )
                    break  # one entry per pod is enough

        elapsed = self._elapsed_ms(start)

        warn_t = int(self.thresholds.get("warning", 1))
        crit_t = int(self.thresholds.get("critical", 3))
        details = {"failing_count": len(failing), "failing": failing[:50]}

        if len(failing) >= crit_t:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"ImagePull 실패 {len(failing)}건",
                response_time_ms=elapsed,
                details=details,
            )
        if len(failing) >= warn_t:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"ImagePull 실패 {len(failing)}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message="ImagePull 실패 없음",
            response_time_ms=elapsed,
            details=details,
        )
