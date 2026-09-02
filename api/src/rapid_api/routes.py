import threading

from fastapi import Header, APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..utils.logging import logger
from ..settings import CRON_AUTH_KEY
from ..database import get_db
from .runner import run_jobs

router = APIRouter(prefix="/rapid-api", tags=["rapid-api"])

# JobControl.is_due is a clock gate, not an in-progress gate: a tick landing
# mid-run would start the same jobs again alongside it. One run at a time.
_run_lock = threading.Lock()


# Plain `def`, not `async`: the jobs are sync (requests + psycopg2). Run on the
# event loop they froze every other request, /health included, for the whole
# run; on the threadpool a slow upstream only slows the cron.
@router.post("/run-jobs", status_code=status.HTTP_202_ACCEPTED)
def run(
    x_cron_auth_key: str | None = Header(None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if x_cron_auth_key != CRON_AUTH_KEY or not CRON_AUTH_KEY:
        logger.warning("Unauthorized cron job attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    if not _run_lock.acquire(blocking=False):
        logger.info("run-jobs already in progress; skipping this tick")
        return {"message": "Run already in progress; skipped"}
    try:
        run_jobs(db)
    finally:
        _run_lock.release()

    return {"message": "Job accepted for processing"}
