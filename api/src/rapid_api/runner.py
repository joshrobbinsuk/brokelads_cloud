import threading
import time
from datetime import datetime, timezone
from typing import Sequence

from sqlalchemy.orm import Session

from ..models import JobControl
from ..utils.logging import logger
from .jobs import JOB_REGISTRY

# JobControl.is_due is a clock gate, not an in-progress gate: a tick landing
# mid-run would start the same jobs again alongside it. The admin's manual
# triggers reach the same jobs from the event loop while the cron holds a
# threadpool thread, so the two genuinely run in parallel — one lock, both
# callers. Process-local: a second Cloud Run instance has its own and is not
# covered (see CLAUDE.md, Known gaps).
_run_lock = threading.Lock()

# No new job may start past this. Cloud Scheduler abandons its attempt at 180s
# and Cloud Run returns 504 at 300s, but neither kills the thread: an over-long
# run keeps the lock while every later tick answers "skipped", so ingestion and
# settlement stop with nothing failing anywhere.
#
# Worst case is this budget, plus the JOB_BUDGET_SECONDS of a job that starts
# just under it, plus one in-flight request: 100 + 45 + 15 = 160s, inside the
# 180s. That bounds the two jobs whose risk is upstream latency. The settlement
# and close jobs have no internal deadline — they are bounded by row caps
# (fetch_bets_to_settle takes 200) and, for the cup backstop loops, by nothing
# at all. At five users that work is seconds; it is not a general bound, and a
# large enough backlog would still run long.
RUN_BUDGET_SECONDS = 100


def fetch_job_controls(db: Session) -> Sequence[JobControl]:
    try:
        return (
            db.query(JobControl)
            .filter(JobControl.job_name.in_(JOB_REGISTRY.keys()))
            .all()
        )
    except Exception:
        logger.exception("Error fetching job controls")
        raise


def run_jobs(db: Session) -> bool:
    """Run every due job. False if a run was already in progress, in which case
    nothing was started."""
    if not _run_lock.acquire(blocking=False):
        return False
    try:
        deadline = time.monotonic() + RUN_BUDGET_SECONDS
        for job in fetch_job_controls(db):
            if not job.is_due():
                logger.debug(
                    f"Job {job.job_name} is not due to run. Enabled={job.enabled} Last run={job.last_run_at}. Interval={job.min_interval_seconds}s"
                )
                continue

            if time.monotonic() >= deadline:
                logger.warning(
                    f"Run budget spent; {job.job_name} deferred to the next tick."
                )
                break

            logger.info(f"Running job: {job.job_name}")
            job.last_run_at = datetime.now(timezone.utc)
            db.commit()
            JOB_REGISTRY[job.job_name](db)
    finally:
        _run_lock.release()
    return True


def run_job(db: Session, job_name: str) -> bool:
    """Run one named job now, ignoring its clock gate — the admin's manual
    trigger. False if a run was already in progress. Deliberately leaves
    last_run_at alone: this is an override, not a tick."""
    if not _run_lock.acquire(blocking=False):
        return False
    try:
        logger.info(f"Running job on request: {job_name}")
        JOB_REGISTRY[job_name](db)
    finally:
        _run_lock.release()
    return True
