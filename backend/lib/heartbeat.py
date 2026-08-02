from __future__ import annotations

import time
from contextlib import contextmanager

from loguru import logger

from backend.lib import db


@contextmanager
def record_run(worker: str):
    started = time.monotonic()
    run_id = None
    try:
        run_id = db.start_worker_run(worker)
    except Exception as e:
        logger.warning("heartbeat_start_failed worker={} error={}", worker, str(e))

    results: dict = {}
    try:
        yield results
    except Exception as e:
        duration_ms = int((time.monotonic() - started) * 1000)
        if run_id:
            try:
                db.finish_worker_run(run_id, "error", results, duration_ms, str(e))
            except Exception as inner:
                logger.warning("heartbeat_finish_failed worker={} error={}", worker, str(inner))
        raise
    else:
        duration_ms = int((time.monotonic() - started) * 1000)
        if run_id:
            try:
                db.finish_worker_run(run_id, "ok", results, duration_ms, None)
            except Exception as e:
                logger.warning("heartbeat_finish_failed worker={} error={}", worker, str(e))
