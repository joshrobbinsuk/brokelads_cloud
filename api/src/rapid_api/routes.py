from fastapi import Header, APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..utils.logging import logger
from ..settings import CRON_AUTH_KEY
from ..database import get_db
from .runner import run_jobs

router = APIRouter(prefix="/rapid-api", tags=["rapid-api"])


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

    run_jobs(db)

    return {"message": "Job accepted for processing"}
