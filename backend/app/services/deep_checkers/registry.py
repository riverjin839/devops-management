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
from app.services.deep_checkers.image_pull_checker import ImagePullChecker
from app.services.deep_checkers.pvc_health_checker import PvcHealthChecker


_REGISTRY: dict[str, type[DeepBaseChecker]] = {
    cls.check_type: cls
    for cls in (PvcHealthChecker, ImagePullChecker, CrashLoopChecker)
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
]
