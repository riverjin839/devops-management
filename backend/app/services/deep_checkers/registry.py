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
from app.services.deep_checkers.daemonset_coverage_checker import DaemonSetCoverageChecker
from app.services.deep_checkers.deployment_progress_checker import DeploymentProgressChecker
from app.services.deep_checkers.endpoint_health_checker import EndpointHealthChecker
from app.services.deep_checkers.event_burst_checker import EventBurstChecker
from app.services.deep_checkers.hpa_health_checker import HpaHealthChecker
from app.services.deep_checkers.image_pull_checker import ImagePullChecker
from app.services.deep_checkers.node_pressure_checker import NodePressureChecker
from app.services.deep_checkers.oom_kill_checker import OomKillChecker
from app.services.deep_checkers.pvc_health_checker import PvcHealthChecker
from app.services.deep_checkers.stuck_namespace_checker import StuckNamespaceChecker
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
        DaemonSetCoverageChecker,
        DeploymentProgressChecker,
        StuckNamespaceChecker,
        EventBurstChecker,
        EndpointHealthChecker,
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
    {
        "check_type": "daemonset_coverage",
        "name": "DaemonSet 커버리지 점검",
        "description": "desired vs current / ready 불일치 + misscheduled",
        "thresholds": DaemonSetCoverageChecker.default_thresholds,
        "params": DaemonSetCoverageChecker.default_params,
        "sort_order": 90,
    },
    {
        "check_type": "deployment_progress",
        "name": "Deployment 진행 상태 점검",
        "description": "Available=False / Progressing=False (ProgressDeadlineExceeded 등)",
        "thresholds": DeploymentProgressChecker.default_thresholds,
        "params": DeploymentProgressChecker.default_params,
        "sort_order": 100,
    },
    {
        "check_type": "stuck_namespace",
        "name": "Terminating 정체 네임스페이스",
        "description": "Terminating 으로 오래 머무는 네임스페이스 (finalizer 잠김)",
        "thresholds": StuckNamespaceChecker.default_thresholds,
        "params": StuckNamespaceChecker.default_params,
        "sort_order": 110,
    },
    {
        "check_type": "event_burst",
        "name": "Warning Event 폭증",
        "description": "최근 윈도우 내 Warning Event count / 단일 사유 폭증",
        "thresholds": EventBurstChecker.default_thresholds,
        "params": EventBurstChecker.default_params,
        "sort_order": 120,
    },
    {
        "check_type": "endpoint_health",
        "name": "Service Endpoint Health",
        "description": "Service 가 매칭하는 Endpoints 에 ready address 가 0 인 경우",
        "thresholds": EndpointHealthChecker.default_thresholds,
        "params": EndpointHealthChecker.default_params,
        "sort_order": 130,
    },
]
