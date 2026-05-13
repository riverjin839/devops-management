"""Deep checker base — parallels services/checkers/base.py but without the
addon coupling. A ``DeepCheckDefinition`` carries the parameters / thresholds
instead of an ``Addon`` row.
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar, Optional

from kubernetes import client, config
from sqlalchemy.orm import Session

from app.models import Cluster, StatusEnum
from app.services.kubeconfig import ensure_kubeconfig_file


_CONNECTION_ERROR_HINTS = (
    "connection refused",
    "no route to host",
    "timed out",
    "timeout",
    "network is unreachable",
    "temporary failure in name resolution",
    "ssl:",
    "max retries exceeded",
    "connection error",
    "failed to establish",
    "certificate verify failed",
)


@dataclass
class DeepCheckResult:
    """Result of one deep-check execution. Persisted as JSONB on
    ``DeepCheckResult.results[check_type]``."""

    status: StatusEnum
    message: str
    response_time_ms: int = 0
    details: Optional[dict[str, Any]] = None


class DeepBaseChecker(ABC):
    """Common scaffolding for deep checkers.

    Subclasses declare ``check_type`` (lookup key) and optionally
    ``param_schema`` (used by the UI to render an edit form).
    """

    # ── Class-level metadata (set by subclass) ─────────────────────────
    check_type: ClassVar[str] = ""
    label: ClassVar[str] = ""
    description: ClassVar[str] = ""
    default_params: ClassVar[dict[str, Any]] = {}
    default_thresholds: ClassVar[dict[str, Any]] = {}
    # JSON-schema-lite for UI form. Each entry: {name, type, label, help?}
    param_schema: ClassVar[list[dict[str, Any]]] = []

    def __init__(
        self,
        cluster: Cluster,
        *,
        params: Optional[dict] = None,
        thresholds: Optional[dict] = None,
        db: Optional[Session] = None,
    ):
        self.cluster = cluster
        self.params: dict = {**self.default_params, **(params or {})}
        self.thresholds: dict = {**self.default_thresholds, **(thresholds or {})}
        self.db = db
        self._core: Optional[client.CoreV1Api] = None
        self._apps: Optional[client.AppsV1Api] = None

    # ── K8s client (lazy) ──────────────────────────────────────────────
    def _ensure_k8s_config(self) -> None:
        kc_path = ensure_kubeconfig_file(self.cluster)
        if kc_path and os.path.exists(kc_path):
            config.load_kube_config(config_file=kc_path)
            return
        try:
            config.load_incluster_config()
        except config.ConfigException:
            config.load_kube_config()

    def core_v1(self) -> client.CoreV1Api:
        if self._core is None:
            self._ensure_k8s_config()
            self._core = client.CoreV1Api()
        return self._core

    def apps_v1(self) -> client.AppsV1Api:
        if self._apps is None:
            self._ensure_k8s_config()
            self._apps = client.AppsV1Api()
        return self._apps

    # ── Timing ────────────────────────────────────────────────────────
    @staticmethod
    def _elapsed_ms(start: datetime) -> int:
        return int((datetime.utcnow() - start).total_seconds() * 1000)

    # ── Subclass contract ─────────────────────────────────────────────
    @abstractmethod
    def check(self) -> DeepCheckResult:
        ...

    # ── Safe runner — pending on connection issues, never raises ──────
    def safe_check(self) -> DeepCheckResult:
        try:
            return self.check()
        except FileNotFoundError as exc:
            return DeepCheckResult(
                status=StatusEnum.pending,
                message=f"{self.label}: 필수 파일 없음 — {str(exc)[:160]}",
                details={"error": str(exc)[:500]},
            )
        except Exception as exc:
            msg = str(exc).lower()
            if any(hint in msg for hint in _CONNECTION_ERROR_HINTS):
                return DeepCheckResult(
                    status=StatusEnum.pending,
                    message=f"{self.label}: 연결 실패 — {str(exc)[:160]}",
                    details={"error": str(exc)[:500]},
                )
            return DeepCheckResult(
                status=StatusEnum.critical,
                message=f"{self.label} check failed: {str(exc)[:200]}",
                details={"error": str(exc)[:500]},
            )
