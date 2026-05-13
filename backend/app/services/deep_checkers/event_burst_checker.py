"""Event burst — K8s Events with high count or many recent Warning events."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class EventBurstChecker(DeepBaseChecker):
    check_type = "event_burst"
    label = "Event Burst"
    description = "최근 K8s Warning Event 의 count/빈도 폭증 검출"
    default_params = {
        "window_minutes": 30,
        "exclude_namespaces": [],
    }
    default_thresholds = {
        "warning": 20,
        "critical": 100,
        "single_event_count_warning": 10,
        "single_event_count_critical": 50,
    }
    param_schema = [
        {"name": "window_minutes", "type": "number", "label": "조회 윈도우(분)"},
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()
        window_min = int(self.params.get("window_minutes", 30))
        exclude = set(self.params.get("exclude_namespaces") or [])
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=window_min)

        events = core.list_event_for_all_namespaces(
            field_selector="type=Warning"
        ).items

        recent: list[Any] = []
        for ev in events:
            ns = ev.metadata.namespace or ""
            if ns in exclude:
                continue
            last_seen = ev.last_timestamp or ev.event_time or ev.metadata.creation_timestamp
            if last_seen and last_seen < cutoff:
                continue
            recent.append(ev)

        # Group by (namespace, reason) to spot bursts on a single failure mode.
        by_reason: Counter[tuple[str, str]] = Counter()
        for ev in recent:
            by_reason[(ev.metadata.namespace or "", ev.reason or "Unknown")] += ev.count or 1

        warn_t = int(self.thresholds.get("warning", 20))
        crit_t = int(self.thresholds.get("critical", 100))
        single_warn = int(self.thresholds.get("single_event_count_warning", 10))
        single_crit = int(self.thresholds.get("single_event_count_critical", 50))

        total = sum(by_reason.values())
        top = sorted(by_reason.items(), key=lambda kv: kv[1], reverse=True)[:20]
        top_list = [
            {"namespace": ns, "reason": reason, "count": count}
            for (ns, reason), count in top
        ]
        worst_single = top[0][1] if top else 0

        elapsed = self._elapsed_ms(start)
        details = {
            "window_minutes": window_min,
            "total_warning_count": total,
            "worst_single_event_count": worst_single,
            "top": top_list,
        }

        if total >= crit_t or worst_single >= single_crit:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"최근 {window_min}분 Warning {total}건 (최다 단일 {worst_single})",
                response_time_ms=elapsed,
                details=details,
            )
        if total >= warn_t or worst_single >= single_warn:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"최근 {window_min}분 Warning {total}건",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"최근 {window_min}분 Warning {total}건 (정상 범위)",
            response_time_ms=elapsed,
            details=details,
        )
