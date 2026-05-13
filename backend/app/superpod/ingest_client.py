"""HTTP client used by the in-cluster super pod to push results back to the
management backend's ``/deep-check/ingest`` endpoint.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger("superpod.ingest")


class IngestClient:
    def __init__(self, *, base_url: str, token: str, verify_ssl: bool = True):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.verify_ssl = verify_ssl

    def post_deep_check(self, payload: dict[str, Any]) -> bool:
        url = f"{self.base_url}/deep-check/ingest"
        headers = {"Authorization": f"Bearer {self.token}"}
        # Up to 4 retries with exponential backoff — matches the user's git
        # push retry policy and is appropriate for transient network blips.
        for attempt in range(4):
            try:
                with httpx.Client(timeout=60, verify=self.verify_ssl) as client:
                    resp = client.post(url, headers=headers, json=payload)
                if resp.status_code < 300:
                    logger.info("Pushed deep check (attempt=%s, status=%s)", attempt + 1, resp.status_code)
                    return True
                logger.warning(
                    "Ingest rejected with HTTP %s: %s", resp.status_code, resp.text[:300]
                )
                if resp.status_code in (401, 403):
                    return False  # auth issue — retrying won't help
            except Exception as exc:
                logger.warning("Ingest attempt %s failed: %s", attempt + 1, exc)
            time.sleep(2 ** attempt)
        return False
