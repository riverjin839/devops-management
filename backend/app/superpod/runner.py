"""Super pod entrypoint — ``python -m app.superpod.runner``.

Reads ``SUPERPOD_MODE`` from settings; dispatches to in-cluster (push to
ingest URL) or centralized (run via DB session) execution.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime
from typing import Iterable

from app.config import settings
from app.models.deep_check import DeepCheckSource

logger = logging.getLogger("superpod")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DevOps Super Pod runner")
    parser.add_argument(
        "--mode",
        choices=["in_cluster", "centralized"],
        default=settings.superpod_mode,
        help="Execution mode (overrides SUPERPOD_MODE env var).",
    )
    parser.add_argument(
        "--cluster-id",
        default=settings.superpod_cluster_id or None,
        help="Cluster UUID. Required for in_cluster mode; centralized loops over all clusters.",
    )
    return parser


def run() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    args = _build_arg_parser().parse_args()
    if args.mode == "in_cluster":
        if not args.cluster_id:
            logger.error("in_cluster mode requires --cluster-id (or SUPERPOD_CLUSTER_ID).")
            return 2
        return _run_in_cluster(args.cluster_id)
    return _run_centralized()


# ---------------------------------------------------------------------------
# Centralized — runs inside the management cluster, against every registered
# cluster, using the existing deep_check_service. Suitable for Celery Beat
# (a future commit will add a beat schedule); also runnable manually.
# ---------------------------------------------------------------------------

def _run_centralized() -> int:
    from app.database import SessionLocal
    from app.models import Cluster
    from app.services.deep_check_service import deep_check_service

    db = SessionLocal()
    successes = 0
    failures: list[dict] = []
    try:
        clusters: Iterable[Cluster] = db.query(Cluster).all()
        for cluster in clusters:
            try:
                deep_check_service.run_for_cluster(
                    db, cluster.id, source=DeepCheckSource.centralized
                )
                successes += 1
            except Exception as exc:
                logger.exception("Deep check failed for %s", cluster.name)
                failures.append({"cluster": cluster.name, "error": str(exc)[:300]})
    finally:
        db.close()
    print(json.dumps({"successes": successes, "failures": failures}, indent=2))
    return 0 if not failures else 1


# ---------------------------------------------------------------------------
# In-cluster — uses in-cluster ServiceAccount, runs every globally enabled
# definition for the target cluster, then pushes the aggregated payload to
# ``settings.superpod_ingest_url`` with the bearer token.
# ---------------------------------------------------------------------------

def _run_in_cluster(cluster_id: str) -> int:
    from kubernetes import config as kconfig

    from app.models.cluster import Cluster, StatusEnum
    from app.services.deep_checkers.registry import (
        DEFAULT_DEFINITIONS,
        get_checker_class,
    )
    from app.superpod.ingest_client import IngestClient

    try:
        kconfig.load_incluster_config()
    except kconfig.ConfigException:
        kconfig.load_kube_config()

    # Inside the target cluster we don't have access to the management DB,
    # so the definition set is hard-coded to the registry defaults. The
    # management backend re-applies the user-configured thresholds when it
    # ingests the result.
    stub_cluster = Cluster(
        id=cluster_id,
        name=f"in-cluster:{cluster_id[:8]}",
        api_endpoint="",
        kubeconfig_path=None,
        status=StatusEnum.healthy,
    )

    payload_results: dict[str, dict] = {}
    payload_errors: list[dict] = []
    for spec in DEFAULT_DEFINITIONS:
        cls = get_checker_class(spec["check_type"])
        if cls is None:
            payload_errors.append(
                {"check_type": spec["check_type"], "error": "unknown check_type"}
            )
            continue
        checker = cls(stub_cluster, params=spec.get("params"), thresholds=spec.get("thresholds"))
        result = checker.safe_check()
        payload_results[spec["check_type"]] = {
            "name": spec["name"],
            "label": cls.label,
            "status": result.status.value,
            "message": result.message,
            "response_time_ms": result.response_time_ms,
            "details": result.details,
        }

    payload = {
        "cluster_id": cluster_id,
        "source": "in_cluster",
        "checked_at": datetime.utcnow().isoformat() + "Z",
        "results": payload_results,
        "errors": payload_errors or None,
    }

    if not settings.superpod_ingest_url or not settings.superpod_ingest_token:
        logger.warning(
            "INGEST URL/TOKEN missing — printing payload instead of pushing."
        )
        print(json.dumps(payload, indent=2))
        return 0

    client = IngestClient(
        base_url=settings.superpod_ingest_url,
        token=settings.superpod_ingest_token,
        verify_ssl=settings.superpod_verify_ssl,
    )
    ok = client.post_deep_check(payload)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
