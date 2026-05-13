"""Fan out daily-check / deep-check results to user-configured channels.

Strategy pattern — one class per channel type. All channels follow the same
fail-safe contract: ``send()`` returns a ``NotificationStatus`` and never
raises; any error is captured in the returned message and persisted to
``NotificationLog``.
"""
from __future__ import annotations

import json
import logging
import smtplib
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Optional
from uuid import UUID

import httpx
from kubernetes import client, config
from sqlalchemy.orm import Session

from app.config import settings
from app.models import Cluster, DailyCheckLog
from app.models.deep_check import DeepCheckResult
from app.models.notification import (
    NotificationChannel,
    NotificationChannelType,
    NotificationLog,
    NotificationSeverity,
    NotificationStatus,
)

logger = logging.getLogger(__name__)


_SEVERITY_RANK = {
    NotificationSeverity.healthy: 0,
    NotificationSeverity.warning: 1,
    NotificationSeverity.critical: 2,
}


@dataclass
class SendResult:
    status: NotificationStatus
    message: Optional[str] = None
    error: Optional[str] = None


@dataclass
class NotificationPayload:
    cluster_name: str
    severity: NotificationSeverity
    daily_check_log_id: Optional[UUID]
    subject: str
    summary: str
    remediation: Optional[list[dict]] = None
    deep_results: Optional[dict] = None

    def as_text(self) -> str:
        parts = [
            f"[{self.severity.value.upper()}] {self.cluster_name}",
            "",
            self.summary,
        ]
        if self.remediation:
            parts.append("")
            parts.append("권장 조치:")
            for i, step in enumerate(self.remediation, start=1):
                title = step.get("title", "")
                desc = step.get("description", "")
                cmd = step.get("command")
                parts.append(f"  {i}. {title} — {desc}")
                if cmd:
                    parts.append(f"     $ {cmd}")
        if self.deep_results:
            parts.append("")
            parts.append("Deep Check:")
            for key, val in self.deep_results.items():
                parts.append(f"  - {key}: {val.get('status')} — {val.get('message')}")
        return "\n".join(parts)


class _ChannelStrategy:
    type: NotificationChannelType

    def send(self, channel: NotificationChannel, payload: NotificationPayload) -> SendResult:
        raise NotImplementedError


class SlackChannel(_ChannelStrategy):
    type = NotificationChannelType.slack

    def send(self, channel: NotificationChannel, payload: NotificationPayload) -> SendResult:
        cfg = channel.config or {}
        webhook = cfg.get("webhook_url") or settings.slack_webhook_url
        if not webhook:
            return SendResult(NotificationStatus.failed, error="slack webhook_url 미설정")
        body = {
            "text": payload.subject,
            "attachments": [
                {
                    "color": _slack_color(payload.severity),
                    "text": payload.as_text(),
                }
            ],
        }
        try:
            with httpx.Client(timeout=10) as client_:
                resp = client_.post(webhook, json=body)
            if resp.status_code >= 300:
                return SendResult(NotificationStatus.failed, error=f"HTTP {resp.status_code}: {resp.text[:200]}")
            return SendResult(NotificationStatus.ok)
        except Exception as exc:
            return SendResult(NotificationStatus.failed, error=str(exc)[:300])


class EmailChannel(_ChannelStrategy):
    type = NotificationChannelType.email

    def send(self, channel: NotificationChannel, payload: NotificationPayload) -> SendResult:
        cfg = channel.config or {}
        host = cfg.get("host")
        port = int(cfg.get("port", 587))
        username = cfg.get("username")
        password = cfg.get("password")
        from_addr = cfg.get("from") or username
        to_addrs = cfg.get("to") or []
        if not host or not to_addrs:
            return SendResult(NotificationStatus.failed, error="email host / to 미설정")
        if isinstance(to_addrs, str):
            to_addrs = [a.strip() for a in to_addrs.split(",") if a.strip()]

        msg = MIMEText(payload.as_text(), _charset="utf-8")
        msg["Subject"] = payload.subject
        msg["From"] = from_addr or ""
        msg["To"] = ", ".join(to_addrs)
        try:
            with smtplib.SMTP(host, port, timeout=10) as srv:
                if cfg.get("starttls", True):
                    srv.starttls()
                if username and password:
                    srv.login(username, password)
                srv.sendmail(from_addr, to_addrs, msg.as_string())
            return SendResult(NotificationStatus.ok)
        except Exception as exc:
            return SendResult(NotificationStatus.failed, error=str(exc)[:300])


class WebhookChannel(_ChannelStrategy):
    type = NotificationChannelType.webhook

    def send(self, channel: NotificationChannel, payload: NotificationPayload) -> SendResult:
        cfg = channel.config or {}
        url = cfg.get("url")
        if not url:
            return SendResult(NotificationStatus.failed, error="webhook url 미설정")
        headers = cfg.get("headers") or {}
        body = {
            "cluster": payload.cluster_name,
            "severity": payload.severity.value,
            "subject": payload.subject,
            "summary": payload.summary,
            "remediation": payload.remediation,
            "deep_results": payload.deep_results,
            "daily_check_log_id": str(payload.daily_check_log_id) if payload.daily_check_log_id else None,
        }
        try:
            with httpx.Client(timeout=10) as client_:
                resp = client_.post(url, headers=headers, json=body)
            if resp.status_code >= 300:
                return SendResult(NotificationStatus.failed, error=f"HTTP {resp.status_code}: {resp.text[:200]}")
            return SendResult(NotificationStatus.ok)
        except Exception as exc:
            return SendResult(NotificationStatus.failed, error=str(exc)[:300])


class K8sEventChannel(_ChannelStrategy):
    type = NotificationChannelType.k8s_event

    def send(self, channel: NotificationChannel, payload: NotificationPayload) -> SendResult:
        cfg = channel.config or {}
        namespace = cfg.get("namespace") or settings.mgmt_namespace
        try:
            try:
                config.load_incluster_config()
            except config.ConfigException:
                config.load_kube_config()
            core = client.CoreV1Api()
            event_type = "Warning" if payload.severity != NotificationSeverity.healthy else "Normal"
            event = client.CoreV1Event(
                metadata=client.V1ObjectMeta(
                    generate_name=f"daily-check-{payload.cluster_name.lower().replace(' ', '-')}-",
                    namespace=namespace,
                ),
                involved_object=client.V1ObjectReference(
                    kind="Cluster",
                    name=payload.cluster_name,
                    namespace=namespace,
                ),
                reason="DailyCheckReview",
                message=payload.as_text()[:1000],
                type=event_type,
                source=client.V1EventSource(component="devops-management"),
            )
            core.create_namespaced_event(namespace=namespace, body=event)
            return SendResult(NotificationStatus.ok)
        except Exception as exc:
            return SendResult(NotificationStatus.failed, error=str(exc)[:300])


_STRATEGIES: dict[NotificationChannelType, _ChannelStrategy] = {
    s.type: s
    for s in (SlackChannel(), EmailChannel(), WebhookChannel(), K8sEventChannel())
}


def _slack_color(severity: NotificationSeverity) -> str:
    return {
        NotificationSeverity.healthy: "good",
        NotificationSeverity.warning: "warning",
        NotificationSeverity.critical: "danger",
    }.get(severity, "warning")


class NotifierService:
    """Fan out a single review to every eligible channel."""

    def dispatch_for_log(
        self,
        db: Session,
        daily_check_log_id: UUID | str,
    ) -> list[NotificationLog]:
        log = (
            db.query(DailyCheckLog)
            .filter(DailyCheckLog.id == daily_check_log_id)
            .first()
        )
        if log is None:
            logger.warning("Notifier: DailyCheckLog %s not found", daily_check_log_id)
            return []
        cluster = db.query(Cluster).filter(Cluster.id == log.cluster_id).first()
        if cluster is None:
            return []

        severity = self._map_severity(log.overall_status.value if log.overall_status else "healthy")
        channels = self._enabled_channels(db, log.cluster_id, severity)
        if not channels:
            return []

        review = (
            db.query(DeepCheckResult)
            .filter(DeepCheckResult.daily_check_log_id == log.id)
            .first()
        )
        payload = self._build_payload(cluster, log, review, severity)

        records: list[NotificationLog] = []
        for ch in channels:
            strategy = _STRATEGIES.get(ch.type)
            if strategy is None:
                rec = NotificationLog(
                    channel_id=ch.id,
                    daily_check_log_id=log.id,
                    severity=severity,
                    subject=payload.subject,
                    status=NotificationStatus.failed,
                    error=f"unsupported channel type: {ch.type}",
                )
                db.add(rec)
                records.append(rec)
                continue
            result = strategy.send(ch, payload)
            rec = NotificationLog(
                channel_id=ch.id,
                daily_check_log_id=log.id,
                severity=severity,
                subject=payload.subject,
                message=payload.as_text()[:5000],
                status=result.status,
                error=result.error,
            )
            db.add(rec)
            records.append(rec)
        db.commit()
        return records

    def test_channel(
        self,
        db: Session,
        channel_id: UUID | str,
    ) -> NotificationLog:
        ch = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
        if ch is None:
            raise ValueError("NotificationChannel not found")
        payload = NotificationPayload(
            cluster_name=ch.cluster.name if ch.cluster else "(test)",
            severity=NotificationSeverity.warning,
            daily_check_log_id=None,
            subject=f"[TEST] DevOps Management — {ch.name}",
            summary="이 메시지는 채널 동작 확인용 테스트 알림입니다.",
        )
        strategy = _STRATEGIES.get(ch.type)
        if strategy is None:
            result = SendResult(NotificationStatus.failed, error=f"unsupported channel type: {ch.type}")
        else:
            result = strategy.send(ch, payload)
        rec = NotificationLog(
            channel_id=ch.id,
            daily_check_log_id=None,
            severity=NotificationSeverity.warning,
            subject=payload.subject,
            message=payload.as_text()[:5000],
            status=result.status,
            error=result.error,
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec

    # ── Helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _map_severity(status_value: str) -> NotificationSeverity:
        try:
            return NotificationSeverity(status_value)
        except ValueError:
            return NotificationSeverity.warning

    @staticmethod
    def _enabled_channels(
        db: Session,
        cluster_id,
        severity: NotificationSeverity,
    ) -> list[NotificationChannel]:
        rank = _SEVERITY_RANK[severity]
        chans = (
            db.query(NotificationChannel)
            .filter(
                NotificationChannel.enabled.is_(True),
                (NotificationChannel.cluster_id == cluster_id)
                | (NotificationChannel.cluster_id.is_(None)),
            )
            .all()
        )
        return [c for c in chans if _SEVERITY_RANK[c.min_severity] <= rank]

    @staticmethod
    def _build_payload(
        cluster: Cluster,
        log: DailyCheckLog,
        review: Optional[DeepCheckResult],
        severity: NotificationSeverity,
    ) -> NotificationPayload:
        summary_parts = []
        if review and review.ai_summary:
            summary_parts.append(review.ai_summary)
        if log.error_messages:
            summary_parts.append("에러:\n  - " + "\n  - ".join(log.error_messages[:5]))
        if log.warning_messages:
            summary_parts.append("경고:\n  - " + "\n  - ".join(log.warning_messages[:5]))
        if not summary_parts:
            summary_parts.append(
                f"노드 {log.ready_nodes}/{log.total_nodes} Ready, API={log.api_server_status.value}"
            )
        return NotificationPayload(
            cluster_name=cluster.name,
            severity=severity,
            daily_check_log_id=log.id,
            subject=f"[{severity.value.upper()}] {cluster.name} 일일 점검 결과",
            summary="\n\n".join(summary_parts),
            remediation=(review.ai_remediation if review else None),
            deep_results=(review.results if review else None),
        )


notifier_service = NotifierService()
