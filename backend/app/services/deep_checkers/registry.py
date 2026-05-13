"""Lookup table for deep checker classes — used by the runner and the UI.

Each registered checker exposes its ``check_type`` (key), display label,
description, parameter schema, and defaults. The frontend renders an edit
form from ``param_schema`` so new check definitions can be created without
custom code.
"""
from __future__ import annotations

from typing import Iterable, Optional

from app.services.deep_checkers.base import DeepBaseChecker
from app.services.deep_checkers.crash_loop_checker import CrashLoopChecker
from app.services.deep_checkers.hpa_health_checker import HpaHealthChecker
from app.services.deep_checkers.image_pull_checker import ImagePullChecker
from app.services.deep_checkers.node_pressure_checker import NodePressureChecker
from app.services.deep_checkers.oom_kill_checker import OomKillChecker
from app.services.deep_checkers.pvc_health_checker import PvcHealthChecker
from app.services.deep_checkers.tls_secret_expiry_checker import TlsSecretExpiryChecker
from app.services.deep_checkers.unscheduled_pods_checker import UnscheduledPodsChecker


_REGISTRY: dict[str, type[DeepBaseChecker]] = {
    cls.check_type: cls
    for cls in (
        PvcHealthChecker,
        ImagePullChecker,
        CrashLoopChecker,
        NodePressureChecker,
        UnscheduledPodsChecker,
        OomKillChecker,
        HpaHealthChecker,
        TlsSecretExpiryChecker,
    )
}


def all_check_types() -> Iterable[type[DeepBaseChecker]]:
    return _REGISTRY.values()


def get_checker_class(check_type: str) -> Optional[type[DeepBaseChecker]]:
    return _REGISTRY.get(check_type)


def describe_check_types() -> list[dict]:
    """UI-facing description of available checkers (form-builder source)."""
    return [
        {
            "check_type": cls.check_type,
            "label": cls.label,
            "description": cls.description,
            "default_params": cls.default_params,
            "default_thresholds": cls.default_thresholds,
            "param_schema": cls.param_schema,
        }
        for cls in _REGISTRY.values()
    ]


DEFAULT_DEFINITIONS = [
    {
        "check_type": "pvc_health",
        "name": "PVC 상태 점검",
        "description": "Pending/Lost PVC 와 Released PV 검출",
        "thresholds": PvcHealthChecker.default_thresholds,
        "params": PvcHealthChecker.default_params,
        "sort_order": 10,
    },
    {
        "check_type": "image_pull",
        "name": "이미지 풀 실패 점검",
        "description": "ImagePullBackOff / ErrImagePull 컨테이너",
        "thresholds": ImagePullChecker.default_thresholds,
        "params": ImagePullChecker.default_params,
        "sort_order": 20,
    },
    {
        "check_type": "crash_loop",
        "name": "CrashLoop 점검",
        "description": "CrashLoopBackOff 컨테이너와 마지막 로그",
        "thresholds": CrashLoopChecker.default_thresholds,
        "params": CrashLoopChecker.default_params,
        "sort_order": 30,
    },
    {
        "check_type": "node_pressure",
        "name": "노드 압박 점검",
        "description": "DiskPressure/MemoryPressure/PIDPressure/NetworkUnavailable",
        "thresholds": NodePressureChecker.default_thresholds,
        "params": NodePressureChecker.default_params,
        "sort_order": 40,
    },
    {
        "check_type": "unscheduled_pods",
        "name": "스케줄 실패 파드 점검",
        "description": "Pending 으로 PodScheduled=False 인 파드",
        "thresholds": UnscheduledPodsChecker.default_thresholds,
        "params": UnscheduledPodsChecker.default_params,
        "sort_order": 50,
    },
    {
        "check_type": "oom_kill",
        "name": "OOMKilled 점검",
        "description": "OOMKilled 로 종료된 컨테이너 (최근 N시간)",
        "thresholds": OomKillChecker.default_thresholds,
        "params": OomKillChecker.default_params,
        "sort_order": 60,
    },
    {
        "check_type": "hpa_health",
        "name": "HPA Health 점검",
        "description": "AbleToScale/ScalingActive=False (metrics-server 부재 등)",
        "thresholds": HpaHealthChecker.default_thresholds,
        "params": HpaHealthChecker.default_params,
        "sort_order": 70,
    },
    {
        "check_type": "tls_secret_expiry",
        "name": "TLS Secret 만료 점검",
        "description": "kubernetes.io/tls Secret 의 인증서 만료일",
        "thresholds": TlsSecretExpiryChecker.default_thresholds,
        "params": TlsSecretExpiryChecker.default_params,
        "sort_order": 80,
    },
]
