"""Tick-based scheduler for BatchJob cron entries.

Celery Beat fires ``tick_batch_job_scheduler`` once per minute. The tick task
queries every enabled BatchJob whose ``cron`` matches the current minute and
``last_run_at`` was before this minute, then dispatches ``run_batch_job`` for
each. Credentials are decrypted from the job's stored ciphertext and passed
in as task kwargs.

Why this instead of celery-redbeat or registering dynamic Beat entries?
- Beat schedules are loaded once at process start; mutating
  ``celery_app.conf.beat_schedule`` in a worker doesn't affect the running
  Beat process.
- A 1-minute tick has trivial overhead and gets new/changed jobs picked up
  on the next tick without restart.
- A minimal 5-field cron matcher (this module) covers the entire syntax our
  UI accepts — no new dependency needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional


def _match_token(token: str, value: int) -> bool:
    """Match a single cron token (after splitting on ',') against a value."""
    if token == "*":
        return True
    if "/" in token:
        base, step_s = token.split("/", 1)
        try:
            step = int(step_s)
        except ValueError:
            return False
        if step <= 0:
            return False
        if base == "*":
            return value % step == 0
        if "-" in base:
            lo_s, hi_s = base.split("-", 1)
            try:
                lo, hi = int(lo_s), int(hi_s)
            except ValueError:
                return False
            return lo <= value <= hi and (value - lo) % step == 0
        try:
            base_val = int(base)
        except ValueError:
            return False
        return value >= base_val and (value - base_val) % step == 0
    if "-" in token:
        lo_s, hi_s = token.split("-", 1)
        try:
            return int(lo_s) <= value <= int(hi_s)
        except ValueError:
            return False
    try:
        return int(token) == value
    except ValueError:
        return False


def _cron_field_matches(field: str, value: int) -> bool:
    return any(_match_token(t, value) for t in field.split(","))


def cron_matches(cron_expr: str, when: datetime) -> bool:
    """5-field cron match against a datetime. Returns False on invalid input.

    Day-of-week convention: cron 0=Sunday (also 7 in some flavors → both work).
    """
    parts = cron_expr.split()
    if len(parts) != 5:
        return False
    minute, hour, dom, month, dow = parts
    # Python: Monday=0..Sunday=6. Cron: Sunday=0..Saturday=6.
    cron_dow = (when.weekday() + 1) % 7
    return (
        _cron_field_matches(minute, when.minute)
        and _cron_field_matches(hour, when.hour)
        and _cron_field_matches(dom, when.day)
        and _cron_field_matches(month, when.month)
        and (
            _cron_field_matches(dow, cron_dow)
            # Accept "7" as an alias for Sunday (0) so users don't get bitten.
            or (cron_dow == 0 and _cron_field_matches(dow, 7))
        )
    )


def is_due(
    cron_expr: str,
    last_run_at: Optional[datetime],
    now: datetime,
) -> bool:
    """True iff the cron should fire **this minute** and hasn't already.

    Clock-skew safe: a ``last_run_at`` that ends up >= ``now`` is treated as
    "already fired" (the worker that just persisted it must be ahead of the
    Beat clock).
    """
    now_min = now.replace(second=0, microsecond=0)
    if not cron_matches(cron_expr, now_min):
        return False
    if last_run_at is None:
        return True
    return last_run_at.replace(second=0, microsecond=0) < now_min


def find_due_jobs(jobs, now: Optional[datetime] = None) -> list:
    """Filter an iterable of BatchJob rows down to ones due to fire now.

    Skips disabled jobs and jobs without a cron expression — callers can pass
    the whole table.
    """
    if now is None:
        now = datetime.utcnow() + timedelta(hours=9)  # KST — Beat schedule is KST too
    return [
        j for j in jobs
        if getattr(j, "enabled", False)
        and getattr(j, "cron", None)
        and is_due(j.cron, getattr(j, "last_run_at", None), now)
    ]
