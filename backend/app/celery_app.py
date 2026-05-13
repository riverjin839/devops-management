"""
Celery 앱 설정 및 스케줄 태스크
- 일일 3회 (아침/점심/저녁) 자동 헬스 체크
"""
from celery import Celery
from celery.schedules import crontab
from datetime import datetime
import asyncio

from app.config import settings

# Celery 앱 생성
celery_app = Celery(
    "k8s_daily_monitor",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

# Celery 설정
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Seoul",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5분 타임아웃
)

# Beat 스케줄 설정 (일일 3회 체크)
celery_app.conf.beat_schedule = {
    # 아침 체크 (09:00 KST)
    "daily-check-morning": {
        "task": "app.celery_app.run_scheduled_check",
        "schedule": crontab(hour=9, minute=0),
        "args": ("morning",),
    },
    # 점심 체크 (13:00 KST)
    "daily-check-noon": {
        "task": "app.celery_app.run_scheduled_check",
        "schedule": crontab(hour=13, minute=0),
        "args": ("noon",),
    },
    # 저녁 체크 (18:00 KST)
    "daily-check-evening": {
        "task": "app.celery_app.run_scheduled_check",
        "schedule": crontab(hour=18, minute=0),
        "args": ("evening",),
    },
    # 기술 트렌드 수집 (07:00 KST)
    "daily-trend-collect": {
        "task": "app.celery_app.run_trend_collect",
        "schedule": crontab(hour=7, minute=0),
    },
    # Deep check 자동 실행 — 일일 점검(09/13/18) 직후 15분에 실행해서
    # DailyCheckLog 가 이미 존재하는 상태에서 결과를 붙임. centralized 모드
    # (backend pod 가 stored kubeconfig 로 외부 점검). 내부 super pod 가
    # 배포된 클러스터에서는 자체 CronJob 이 같은 ingest API 로 push.
    "deep-check-morning": {
        "task": "app.celery_app.run_centralized_deep_check",
        "schedule": crontab(hour=9, minute=15),
    },
    "deep-check-noon": {
        "task": "app.celery_app.run_centralized_deep_check",
        "schedule": crontab(hour=13, minute=15),
    },
    "deep-check-evening": {
        "task": "app.celery_app.run_centralized_deep_check",
        "schedule": crontab(hour=18, minute=15),
    },
    # BatchJob cron entries are not in Beat — a 1-minute tick scheduler
    # queries the DB and dispatches due jobs (see tick_batch_job_scheduler).
    "batch-job-scheduler-tick": {
        "task": "app.celery_app.tick_batch_job_scheduler",
        "schedule": crontab(),
    },
}


@celery_app.task(bind=True, name="app.celery_app.run_scheduled_check")
def run_scheduled_check(self, schedule_type: str):
    """
    스케줄된 일일 체크 실행
    모든 활성 클러스터에 대해 체크 수행
    """
    from app.database import SessionLocal
    from app.models import Cluster, CheckSchedule, CheckScheduleType
    from app.services.daily_checker import DailyChecker

    db = SessionLocal()

    try:
        # 스케줄 타입 매핑
        schedule_enum = CheckScheduleType(schedule_type)

        # 해당 시간대에 체크가 활성화된 클러스터 조회
        clusters = db.query(Cluster).all()

        results = []
        for cluster in clusters:
            # 스케줄 설정 확인
            schedule = db.query(CheckSchedule).filter(
                CheckSchedule.cluster_id == cluster.id,
                CheckSchedule.is_active == True
            ).first()

            # 스케줄이 없거나 해당 시간대가 비활성화면 스킵
            if schedule:
                if schedule_type == "morning" and not schedule.morning_enabled:
                    continue
                elif schedule_type == "noon" and not schedule.noon_enabled:
                    continue
                elif schedule_type == "evening" and not schedule.evening_enabled:
                    continue

            # 체크 실행
            checker = DailyChecker(db)
            try:
                # async 함수를 sync로 실행
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(
                    checker.run_daily_check(str(cluster.id), schedule_enum)
                )
                loop.close()

                results.append({
                    "cluster": cluster.name,
                    "status": result.overall_status.value,
                    "checked_at": result.checked_at.isoformat()
                })
            except Exception as e:
                results.append({
                    "cluster": cluster.name,
                    "error": str(e)
                })

        return {
            "schedule_type": schedule_type,
            "executed_at": datetime.now().isoformat(),
            "results": results
        }

    finally:
        db.close()


@celery_app.task(bind=True, name="app.celery_app.run_trend_collect")
def run_trend_collect(self):
    """매일 07:00 KST 기술 트렌드 수집"""
    from app.database import SessionLocal
    from app.services.trends.trend_service import TrendService

    db = SessionLocal()
    try:
        svc = TrendService(db)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        digest = loop.run_until_complete(svc.run_daily_collect())
        loop.close()
        return {
            "digest_date": str(digest.digest_date),
            "status": digest.status,
            "item_count": digest.item_count,
        }
    finally:
        db.close()


@celery_app.task(bind=True, name="app.celery_app.run_batch_job")
def run_batch_job(self, job_id: str, *, password: str | None = None, private_key: str | None = None):
    """Execute a registered batch job by id.

    If no credentials are supplied by the caller, falls back to the
    encrypted-at-rest credentials on the BatchJob row (decrypted via
    services.secrets). Used for scheduled runs (tick scheduler) and
    ad-hoc background triggers.
    """
    from uuid import UUID
    from app.database import SessionLocal
    from app.services.batch_job_service import execute_job, get_job_or_404
    from app.services.secrets import decrypt_secret

    db = SessionLocal()
    try:
        job = get_job_or_404(db, UUID(job_id))
        if not job.enabled:
            return {"job_id": job_id, "skipped": True, "reason": "disabled"}

        if not password and job.default_password_enc:
            password = decrypt_secret(job.default_password_enc)
        if not private_key and job.default_private_key_enc:
            private_key = decrypt_secret(job.default_private_key_enc)
        if not password and not private_key:
            return {
                "job_id": job_id,
                "skipped": True,
                "reason": "no credentials (set default_password or default_private_key for scheduled execution)",
            }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            run, result = loop.run_until_complete(
                execute_job(
                    db,
                    job,
                    password=password,
                    private_key=private_key,
                    trigger="schedule",
                )
            )
        finally:
            loop.close()

        return {
            "job_id": job_id,
            "run_id": str(run.id),
            "status": result.status,
            "duration_ms": result.duration_ms,
        }
    finally:
        db.close()


@celery_app.task(bind=True, name="app.celery_app.tick_batch_job_scheduler")
def tick_batch_job_scheduler(self):
    """Once-per-minute Beat tick that dispatches BatchJobs whose cron matches.

    Picks up newly-added cron entries and disable toggles within a minute,
    without a Beat restart.
    """
    from app.database import SessionLocal
    from app.models import BatchJob
    from app.services.batch_job_scheduler import find_due_jobs

    db = SessionLocal()
    try:
        jobs = (
            db.query(BatchJob)
            .filter(BatchJob.enabled.is_(True), BatchJob.cron.isnot(None))
            .all()
        )
        due = find_due_jobs(jobs)
        fired: list[str] = []
        for job in due:
            run_batch_job.delay(str(job.id))
            fired.append(str(job.id))
        return {
            "checked": len(jobs),
            "fired": fired,
            "at": datetime.now().isoformat(),
        }
    finally:
        db.close()


@celery_app.task(bind=True, name="app.celery_app.run_centralized_deep_check")
def run_centralized_deep_check(self):
    """Run centralized deep checks for every registered cluster.

    Wired into Beat at 09:15/13:15/18:15 KST so each daily check (09/13/18)
    already has a DailyCheckLog by the time we attach deep results. AI
    review + notification fan-out are scheduled by deep_check_service.
    """
    from app.database import SessionLocal
    from app.models import Cluster
    from app.models.deep_check import DeepCheckSource
    from app.services.deep_check_service import deep_check_service

    db = SessionLocal()
    successes = 0
    failures: list[dict] = []
    try:
        for cluster in db.query(Cluster).all():
            try:
                deep_check_service.run_for_cluster(
                    db, cluster.id, source=DeepCheckSource.centralized
                )
                successes += 1
            except Exception as exc:
                failures.append({"cluster": cluster.name, "error": str(exc)[:300]})
    finally:
        db.close()
    return {
        "executed_at": datetime.now().isoformat(),
        "successes": successes,
        "failures": failures,
    }


@celery_app.task(bind=True, name="app.celery_app.run_review_and_notify")
def run_review_and_notify(self, daily_check_log_id: str):
    """Generate the AI review for a daily check log and persist it.

    Phase 1: only AI review (Ollama summary + remediation + diff). Phase 4
    will extend this task to fan out notifications.
    """
    from app.database import SessionLocal
    from app.services.review_service import review_service

    from app.services.notifier import notifier_service

    db = SessionLocal()
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                review_service.review_and_persist(db, daily_check_log_id)
            )
        finally:
            loop.close()
        try:
            notif_logs = notifier_service.dispatch_for_log(db, daily_check_log_id)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Notification fan-out failed for %s", daily_check_log_id
            )
            notif_logs = []
        return {
            "daily_check_log_id": daily_check_log_id,
            "ai_status": result.ai_status.value if result.ai_status else None,
            "has_remediation": bool(result.ai_remediation),
            "notifications_sent": sum(
                1 for r in notif_logs if r.status.value == "ok"
            ),
            "notifications_failed": sum(
                1 for r in notif_logs if r.status.value == "failed"
            ),
        }
    finally:
        db.close()


@celery_app.task(bind=True, name="app.celery_app.run_single_check")
def run_single_check(self, cluster_id: str):
    """단일 클러스터 체크 실행 (수동)"""
    from app.database import SessionLocal
    from app.models import CheckScheduleType
    from app.services.daily_checker import DailyChecker

    db = SessionLocal()

    try:
        checker = DailyChecker(db)

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            checker.run_daily_check(cluster_id, CheckScheduleType.manual)
        )
        loop.close()

        return {
            "cluster_id": cluster_id,
            "status": result.overall_status.value,
            "api_server_status": result.api_server_status.value,
            "total_nodes": result.total_nodes,
            "ready_nodes": result.ready_nodes,
            "checked_at": result.checked_at.isoformat()
        }

    finally:
        db.close()
