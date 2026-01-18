from datetime import datetime, timezone
from typing import Any, Sequence, cast

from sqlalchemy.orm import Session

from ..models import JobControl
from ..utils.logging import logger
from .jobs import JOB_REGISTRY


def fetch_job_controls(db: Session) -> Sequence[JobControl]:
    try:
        return (
            db.query(JobControl)
            .filter(JobControl.job_name.in_(JOB_REGISTRY.keys()))
            .all()
        )
    except Exception as e:
        logger.error(f"Error fetching job controls: {e}")
        return []


def run_jobs(db: Session) -> None:
    jobs = fetch_job_controls(db)

    for job in jobs:
        if not job.is_due():
            logger.info(
                f"Job {job.job_name} is not due to run. Enabled={job.enabled} Last run={job.last_run_at}. Interval={job.min_interval_seconds}s"
            )

        else:
            logger.info(f"Running job: {job.job_name}")
            job_mut = cast(Any, job)
            job_mut.last_run_at = datetime.now(timezone.utc)
            db.commit()
            job_name = cast(str, job.job_name)
            JOB_REGISTRY[job_name](db)
