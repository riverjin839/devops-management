"""AI review of daily check results.

Phase 1: pulls a ``DailyCheckLog`` + the previous run for the same cluster,
asks Ollama for a concise summary and a structured remediation list, and
persists the result on ``DeepCheckResult``. Fail-safe — if Ollama is offline
the row is still stored with ``ai_status='offline'`` and a fallback message.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.models import Cluster, DailyCheckLog
from app.models.deep_check import AiReviewStatus, DeepCheckResult
from app.services.agent_service import agent_service

logger = logging.getLogger(__name__)


REVIEW_QUERY = (
    "Review this Kubernetes daily health-check. Reply in two parts:\n"
    "1) A 2-3 sentence summary of the cluster state (Korean OK).\n"
    "2) A JSON array named REMEDIATION with up to 5 actions, each "
    '{"title": str, "command": str (optional kubectl command), "description": str}.\n'
    "Return ONLY the summary then ```json\\n{\"remediation\": [...] }\\n```."
)


class ReviewService:
    """Build review context and persist Ollama output to DeepCheckResult."""

    async def review_and_persist(
        self,
        db: Session,
        daily_check_log_id: str,
        *,
        force: bool = False,
    ) -> DeepCheckResult:
        log: Optional[DailyCheckLog] = (
            db.query(DailyCheckLog).filter(DailyCheckLog.id == daily_check_log_id).first()
        )
        if not log:
            raise ValueError(f"DailyCheckLog not found: {daily_check_log_id}")

        existing = (
            db.query(DeepCheckResult)
            .filter(DeepCheckResult.daily_check_log_id == log.id)
            .first()
        )
        if existing and not force and existing.ai_status == AiReviewStatus.ok:
            return existing

        cluster = db.query(Cluster).filter(Cluster.id == log.cluster_id).first()
        prev_log = self._previous_log(db, log)
        trend = self._build_trend(log, prev_log)
        context = self._build_context(cluster, log, prev_log, trend)

        agent_resp = await agent_service.ask_agent(REVIEW_QUERY, context=context)
        summary, remediation = self._parse_response(agent_resp.get("answer", ""))

        row = existing or DeepCheckResult(
            cluster_id=log.cluster_id,
            daily_check_log_id=log.id,
        )

        if agent_resp.get("status") == "ok":
            row.ai_status = AiReviewStatus.ok
            row.ai_summary = summary or agent_resp.get("answer")
            row.ai_remediation = remediation
            row.ai_model = agent_resp.get("model") or None
            row.ai_error = None
        else:
            row.ai_status = AiReviewStatus.offline
            row.ai_summary = agent_resp.get("answer")
            row.ai_remediation = None
            row.ai_model = None
            row.ai_error = None

        row.trend_summary = trend
        row.updated_at = datetime.utcnow()

        if existing is None:
            db.add(row)
        db.commit()
        db.refresh(row)
        return row

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _previous_log(db: Session, log: DailyCheckLog) -> Optional[DailyCheckLog]:
        return (
            db.query(DailyCheckLog)
            .filter(
                DailyCheckLog.cluster_id == log.cluster_id,
                DailyCheckLog.id != log.id,
                DailyCheckLog.checked_at < log.checked_at,
            )
            .order_by(desc(DailyCheckLog.checked_at))
            .first()
        )

    @staticmethod
    def _build_trend(curr: DailyCheckLog, prev: Optional[DailyCheckLog]) -> dict:
        curr_errors = set(curr.error_messages or [])
        curr_warnings = set(curr.warning_messages or [])
        if prev is None:
            return {
                "prev_status": None,
                "status_changed": False,
                "new_errors": sorted(curr_errors),
                "resolved_errors": [],
                "new_warnings": sorted(curr_warnings),
                "resolved_warnings": [],
                "ready_nodes_delta": 0,
            }
        prev_errors = set(prev.error_messages or [])
        prev_warnings = set(prev.warning_messages or [])
        return {
            "prev_status": prev.overall_status.value if prev.overall_status else None,
            "status_changed": prev.overall_status != curr.overall_status,
            "new_errors": sorted(curr_errors - prev_errors),
            "resolved_errors": sorted(prev_errors - curr_errors),
            "new_warnings": sorted(curr_warnings - prev_warnings),
            "resolved_warnings": sorted(prev_warnings - curr_warnings),
            "ready_nodes_delta": (curr.ready_nodes or 0) - (prev.ready_nodes or 0),
            "prev_checked_at": prev.checked_at.isoformat() if prev.checked_at else None,
        }

    @staticmethod
    def _build_context(
        cluster: Optional[Cluster],
        log: DailyCheckLog,
        prev: Optional[DailyCheckLog],
        trend: dict,
    ) -> dict:
        node_lines = []
        for n in (log.nodes_status or [])[:10]:
            node_lines.append(
                f"- {n.get('name')}: {n.get('status')} (cpu={n.get('cpu')}, memory={n.get('memory')})"
            )
        node_block = "\n".join(node_lines) or "(no nodes reported)"

        extra = {
            "schedule_type": log.schedule_type.value if log.schedule_type else None,
            "overall_status": log.overall_status.value if log.overall_status else None,
            "api_server_status": (
                log.api_server_status.value if log.api_server_status else None
            ),
            "components": log.components_status,
            "ready_nodes": log.ready_nodes,
            "total_nodes": log.total_nodes,
            "trend_vs_previous": trend,
            "previous_checked_at": (
                prev.checked_at.isoformat() if prev and prev.checked_at else None
            ),
        }

        return {
            "cluster_name": cluster.name if cluster else str(log.cluster_id),
            "cluster_status": (
                log.overall_status.value if log.overall_status else "unknown"
            ),
            "node_status": node_block,
            "error_messages": log.error_messages or [],
            "extra": json.dumps(extra, default=str, ensure_ascii=False, indent=2),
        }

    @staticmethod
    def _parse_response(answer: str) -> tuple[Optional[str], Optional[list]]:
        """Best-effort split of the LLM answer into summary + remediation list.

        The prompt asks for free text followed by a ```json``` block; if the
        model deviates we still return whatever text we got as the summary and
        ``None`` for remediation.
        """
        if not answer:
            return None, None
        match = re.search(r"```json\s*(\{.*?\})\s*```", answer, re.DOTALL)
        if not match:
            return answer.strip(), None
        summary = answer[: match.start()].strip()
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return summary or answer.strip(), None
        remediation = payload.get("remediation")
        if isinstance(remediation, list):
            cleaned = [
                {
                    "title": str(item.get("title", "")).strip(),
                    "command": item.get("command"),
                    "description": str(item.get("description", "")).strip(),
                }
                for item in remediation
                if isinstance(item, dict) and item.get("title")
            ]
            return summary or None, cleaned or None
        return summary or None, None


review_service = ReviewService()
