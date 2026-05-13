"""TLS Secret 만료 검사.

kubernetes.io/tls 타입 Secret 의 ``tls.crt`` 를 파싱해서 NotAfter 까지 남은
일수를 임계값(warning_days/critical_days)과 비교. ``cryptography`` 패키지는
kubernetes / ansible-core 의 transitive dependency 라 이미 백엔드 이미지에
설치돼 있음.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any

from app.models import StatusEnum
from app.services.deep_checkers.base import DeepBaseChecker, DeepCheckResult


class TlsSecretExpiryChecker(DeepBaseChecker):
    check_type = "tls_secret_expiry"
    label = "TLS Secret Expiry"
    description = "kubernetes.io/tls Secret 의 인증서 만료일 점검"
    default_params = {
        "exclude_namespaces": ["kube-system"],
    }
    default_thresholds = {"warning_days": 30, "critical_days": 7}
    param_schema = [
        {"name": "exclude_namespaces", "type": "string[]", "label": "제외할 네임스페이스"},
    ]

    def check(self) -> DeepCheckResult:
        try:
            from cryptography import x509
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            return DeepCheckResult(
                status=StatusEnum.pending,
                message="cryptography 패키지가 없어 인증서 파싱 불가",
                details={"error": "ImportError: cryptography"},
            )

        start = datetime.utcnow()
        core = self.core_v1()
        exclude = set(self.params.get("exclude_namespaces") or [])
        warn_days = int(self.thresholds.get("warning_days", 30))
        crit_days = int(self.thresholds.get("critical_days", 7))
        now = datetime.now(timezone.utc)

        secrets = core.list_secret_for_all_namespaces(
            field_selector="type=kubernetes.io/tls"
        ).items

        warnings: list[dict[str, Any]] = []
        criticals: list[dict[str, Any]] = []
        parse_errors: list[dict[str, Any]] = []

        for sec in secrets:
            ns = sec.metadata.namespace
            if ns in exclude:
                continue
            raw_b64 = (sec.data or {}).get("tls.crt")
            if not raw_b64:
                continue
            try:
                pem = base64.b64decode(raw_b64)
                cert = x509.load_pem_x509_certificate(pem, default_backend())
                not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
                days_left = (not_after - now).days
                entry = {
                    "namespace": ns,
                    "name": sec.metadata.name,
                    "not_after": not_after.isoformat(),
                    "days_left": days_left,
                    "subject": cert.subject.rfc4514_string(),
                }
                if days_left <= crit_days:
                    criticals.append(entry)
                elif days_left <= warn_days:
                    warnings.append(entry)
            except Exception as exc:
                parse_errors.append(
                    {"namespace": ns, "name": sec.metadata.name, "error": str(exc)[:200]}
                )

        elapsed = self._elapsed_ms(start)
        details = {
            "total_tls_secrets": len(secrets),
            "criticals": criticals,
            "warnings": warnings,
            "parse_errors": parse_errors[:20],
        }

        if criticals:
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"인증서 {len(criticals)}건 {crit_days}일 이내 만료",
                response_time_ms=elapsed,
                details=details,
            )
        if warnings:
            return DeepCheckResult(
                status=StatusEnum.warning,
                message=f"인증서 {len(warnings)}건 {warn_days}일 이내 만료",
                response_time_ms=elapsed,
                details=details,
            )
        return DeepCheckResult(
            status=StatusEnum.healthy,
            message=f"TLS Secret {len(secrets)}개 모두 {warn_days}일 이상 여유",
            response_time_ms=elapsed,
            details=details,
        )
