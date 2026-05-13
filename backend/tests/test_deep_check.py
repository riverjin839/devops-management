"""Smoke tests for the super pod / deep check feature.

These tests focus on the pieces that do NOT require a live database:
- The check-type registry shape (used by the UI to render forms).
- The notifier strategy registry covers all enum values.
- review_service helpers compute diffs as expected.
"""
import os
from datetime import datetime
from types import SimpleNamespace

# Tests live next to the existing test_api.py which already sets these,
# but importing this module first must not fail standalone.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/k8s_monitor_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def test_deep_check_registry_describes_required_fields():
    from app.services.deep_checkers.registry import describe_check_types, all_check_types

    schemas = describe_check_types()
    assert len(schemas) > 0
    required = {"check_type", "label", "description", "default_params",
                "default_thresholds", "param_schema"}
    for entry in schemas:
        assert required <= set(entry.keys()), f"missing field in {entry}"
    # Default definitions in registry must all resolve to a class.
    for cls in all_check_types():
        assert cls.check_type
        assert cls.label


def test_deep_check_default_definitions_resolve():
    from app.services.deep_checkers.registry import DEFAULT_DEFINITIONS, get_checker_class

    for spec in DEFAULT_DEFINITIONS:
        assert get_checker_class(spec["check_type"]) is not None, (
            f"DEFAULT_DEFINITIONS references unknown check_type={spec['check_type']}"
        )


def test_notifier_strategy_registry_covers_all_types():
    from app.models.notification import NotificationChannelType
    from app.services.notifier import _STRATEGIES  # noqa: PLC2701 — accessing for assertion

    assert set(_STRATEGIES.keys()) == set(NotificationChannelType)


def test_review_service_trend_diff_for_first_run():
    from app.services.review_service import ReviewService
    from app.models import StatusEnum

    log = SimpleNamespace(
        error_messages=["err-a", "err-b"],
        warning_messages=["warn-x"],
        ready_nodes=3,
        overall_status=StatusEnum.warning,
        checked_at=datetime.utcnow(),
    )
    trend = ReviewService._build_trend(log, prev=None)
    assert trend["prev_status"] is None
    assert trend["new_errors"] == ["err-a", "err-b"]
    assert trend["resolved_errors"] == []
    assert trend["new_warnings"] == ["warn-x"]
    assert trend["ready_nodes_delta"] == 0


def test_review_service_trend_diff_when_errors_resolve():
    from app.services.review_service import ReviewService
    from app.models import StatusEnum

    prev = SimpleNamespace(
        error_messages=["shared", "old-only"],
        warning_messages=[],
        ready_nodes=2,
        overall_status=StatusEnum.critical,
        checked_at=datetime.utcnow(),
    )
    curr = SimpleNamespace(
        error_messages=["shared", "new-only"],
        warning_messages=["warn"],
        ready_nodes=3,
        overall_status=StatusEnum.warning,
        checked_at=datetime.utcnow(),
    )
    trend = ReviewService._build_trend(curr, prev)
    assert trend["prev_status"] == StatusEnum.critical.value
    assert trend["status_changed"] is True
    assert trend["new_errors"] == ["new-only"]
    assert trend["resolved_errors"] == ["old-only"]
    assert trend["new_warnings"] == ["warn"]
    assert trend["ready_nodes_delta"] == 1


def test_review_service_parses_remediation_block():
    from app.services.review_service import ReviewService

    answer = (
        "전반적으로 안정적이지만 노드 1대가 NotReady.\n\n"
        "```json\n"
        '{"remediation": ['
        '{"title": "노드 재부팅", "command": "kubectl drain node-1", "description": "DiskPressure 해소"}'
        "]}\n```"
    )
    summary, remediation = ReviewService._parse_response(answer)
    assert summary and "안정적" in summary
    assert isinstance(remediation, list) and len(remediation) == 1
    assert remediation[0]["title"] == "노드 재부팅"
    assert remediation[0]["command"] == "kubectl drain node-1"
