from fastapi import Header, APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..utils.logging import logger
from ..settings import CRON_AUTH_KEY
from ..database import get_db
from .runner import run_jobs

router = APIRouter(prefix="/rapid-api", tags=["rapid-api"])


@router.post("/run-jobs", status_code=status.HTTP_202_ACCEPTED)
async def run(
    x_cron_auth_key: str = Header(None),
    db: Session = Depends(get_db),
):
    if x_cron_auth_key != CRON_AUTH_KEY or not CRON_AUTH_KEY:
        logger.warning("Unauthorized cron job attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    run_jobs(db)

    return {"message": "Job accepted for processing"}
