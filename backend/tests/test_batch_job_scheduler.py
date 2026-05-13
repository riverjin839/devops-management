"""Tests for the batch-job cron matcher and ``is_due`` helper.

Pure-function tests — no DB / Celery required.
"""
import os
from datetime import datetime, timedelta

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/k8s_monitor_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def test_cron_matches_wildcard():
    from app.services.batch_job_scheduler import cron_matches
    when = datetime(2026, 5, 13, 10, 30)
    assert cron_matches("* * * * *", when)


def test_cron_matches_exact_hour_minute():
    from app.services.batch_job_scheduler import cron_matches
    when = datetime(2026, 5, 13, 3, 0)
    assert cron_matches("0 3 * * *", when)
    assert not cron_matches("0 3 * * *", when.replace(minute=1))
    assert not cron_matches("0 3 * * *", when.replace(hour=4))


def test_cron_step_field():
    """*/5 should fire every 5 minutes."""
    from app.services.batch_job_scheduler import cron_matches
    base = datetime(2026, 5, 13, 12, 0)
    assert cron_matches("*/5 * * * *", base)
    assert cron_matches("*/5 * * * *", base.replace(minute=5))
    assert cron_matches("*/5 * * * *", base.replace(minute=10))
    assert not cron_matches("*/5 * * * *", base.replace(minute=3))
    assert not cron_matches("*/5 * * * *", base.replace(minute=7))


def test_cron_list_and_range():
    from app.services.batch_job_scheduler import cron_matches
    when = datetime(2026, 5, 13, 9, 15)
    assert cron_matches("15 9,13,18 * * *", when)
    assert cron_matches("15 9,13,18 * * *", when.replace(hour=13))
    assert cron_matches("15 9,13,18 * * *", when.replace(hour=18))
    assert not cron_matches("15 9,13,18 * * *", when.replace(hour=10))
    # range form
    assert cron_matches("0 9-17 * * *", when.replace(minute=0, hour=12))
    assert not cron_matches("0 9-17 * * *", when.replace(minute=0, hour=8))


def test_cron_day_of_week_sunday_alias():
    """0 and 7 both mean Sunday."""
    from app.services.batch_job_scheduler import cron_matches
    sunday = datetime(2026, 5, 17, 3, 0)  # 2026-05-17 is a Sunday
    assert sunday.weekday() == 6
    assert cron_matches("0 3 * * 0", sunday)
    assert cron_matches("0 3 * * 7", sunday)
    monday = sunday + timedelta(days=1)
    assert not cron_matches("0 3 * * 0", monday)


def test_cron_invalid_returns_false():
    from app.services.batch_job_scheduler import cron_matches
    assert not cron_matches("not a cron", datetime(2026, 5, 13))
    assert not cron_matches("0 3 * *", datetime(2026, 5, 13))  # 4 fields
    assert not cron_matches("0 3 * * * extra", datetime(2026, 5, 13))


def test_is_due_first_run():
    """No last_run_at → fire when cron matches the current minute."""
    from app.services.batch_job_scheduler import is_due
    now = datetime(2026, 5, 13, 3, 0, 15)
    assert is_due("0 3 * * *", last_run_at=None, now=now)
    assert not is_due("0 3 * * *", last_run_at=None, now=now.replace(minute=1))


def test_is_due_skips_when_already_ran_this_minute():
    from app.services.batch_job_scheduler import is_due
    now = datetime(2026, 5, 13, 3, 0, 45)
    last = datetime(2026, 5, 13, 3, 0, 5)
    assert not is_due("0 3 * * *", last_run_at=last, now=now), (
        "should not double-fire within the same minute"
    )


def test_is_due_fires_on_next_window():
    from app.services.batch_job_scheduler import is_due
    last = datetime(2026, 5, 13, 3, 0, 5)
    next_fire = datetime(2026, 5, 14, 3, 0, 5)
    assert is_due("0 3 * * *", last_run_at=last, now=next_fire)


def test_find_due_jobs_filters_disabled_and_no_cron():
    """find_due_jobs should ignore enabled=False and cron=None rows."""
    from types import SimpleNamespace
    from app.services.batch_job_scheduler import find_due_jobs

    now = datetime(2026, 5, 13, 3, 0, 30)
    enabled_due = SimpleNamespace(enabled=True, cron="0 3 * * *", last_run_at=None, id="a")
    enabled_not_due = SimpleNamespace(enabled=True, cron="0 4 * * *", last_run_at=None, id="b")
    disabled = SimpleNamespace(enabled=False, cron="0 3 * * *", last_run_at=None, id="c")
    no_cron = SimpleNamespace(enabled=True, cron=None, last_run_at=None, id="d")
    due = find_due_jobs([enabled_due, enabled_not_due, disabled, no_cron], now=now)
    assert [j.id for j in due] == ["a"]
