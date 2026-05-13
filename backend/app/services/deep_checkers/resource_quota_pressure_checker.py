"""ResourceQuota near-exhaustion — used/hard ratio."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


_MEM_UNITS = {
    "Ki": 1024, "Mi": 1024**2, "Gi": 1024**3, "Ti": 1024**4,
    "K": 1000, "M": 1000**2, "G": 1000**3, "T": 1000**4,
}


def _parse_quantity(value: str) -> float:
    if not value:
        return 0.0
    s = str(value).strip()
    # CPU millicores
    if s.endswith("m") and s[:-1].replace(".", "").isdigit():
        return float(s[:-1]) / 1000.0
    # Memory binary/decimal suffix
    match = re.match(r"^([0-9.]+)([A-Za-z]+)?$", s)
    if not match:
        try:
            return float(s)
        except ValueError:
            return 0.0
    num, unit = match.group(1), match.group(2) or ""
    return float(num) * _MEM_UNITS.get(unit, 1)


class ResourceQuotaPressureChecker(DeepBaseChecker):
    check_type = "resource_quota_pressure"
    label = "ResourceQuota Pressure"
    description = "ResourceQuota used/hard 비율이 임계 이상인 항목 검출"
    default_params = {"exclude_namespaces": []}
    default_thresholds = {"warning_pct": 80, "critical_pct": 95}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
    ]

    def check(self) -> DeepCheckResult:
        start = datetime.utcnow()
        core = self.core_v1()
        exclude = set(self.params.get("exclude_namespaces") or [])
        warn_pct = float(self.thresholds.get("warning_pct", 80))
        crit_pct = float(self.thresholds.get("critical_pct", 95))

        quotas = core.list_resource_quota_for_all_namespaces().items
        warnings: list[dict[str, Any]] = []
        criticals: list[dict[str, Any]] = []
        for rq in quotas:
            ns = rq.metadata.namespace
            if ns in exclude:
                continue
            hard = rq.status.hard if rq.status else None
            used = rq.status.used if rq.status else None
            if not hard or not used:
                continue
            for resource, hard_raw in hard.items():
                used_raw = used.get(resource)
                if used_raw is None:
                    continue
                hard_n = _parse_quantity(hard_raw)
                used_n = _parse_quantity(used_raw)
                if hard_n <= 0:
                    continue
                pct = (used_n / hard_n) * 100.0
                if pct < warn_pct:
                    continue
                entry = {
                    "namespace": ns,
                    "quota": rq.metadata.name,
                    "resource": resource,
                    "used": used_raw,
                    "hard": hard_raw,
                    "pct": round(pct, 1),
                }
                if pct >= crit_pct:
                    criticals.append(entry)
                else:
                    warnings.append(entry)

        elapsed = self._elapsed_ms(start)
        details = {
            "total_quotas": len(quotas),
            "criticals": criticals[:50],
            "warnings": warnings[:50],
        }
        if criticals:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"ResourceQuota {len(criticals)}건 critical_pct>={crit_pct} 초과",
                response_time_ms=elapsed,
                details=details,
            )
        if warnings:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"ResourceQuota {len(warnings)}건 warning_pct>={warn_pct} 초과",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"ResourceQuota {len(quotas)}개 모두 여유",
            response_time_ms=elapsed,
            details=details,
        )
