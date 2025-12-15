from fastapi import (
    Request,
    APIRouter,
    Depends,
    HTTPException,
    status as http_status,
    Query,
)
from sqlalchemy.orm import Session

from ..utils.logging import logger
from ..database import get_db
from .utils.cognito import verify_token
from .utils.user import get_current_user
from ..models import User, BetOutcome

from .queries import (
    fetch_non_started_fixtures_with_odds,
    create_bet,
    get_user_bets,
    ClientSideError,
)
from .schemas import CreateBetRequest

router = APIRouter(prefix="/client", tags=["client"])


@router.get("/fixture")
async def get_fixtures(
    db: Session = Depends(get_db),
    _claims=Depends(verify_token),
):
    fixtures = fetch_non_started_fixtures_with_odds(db)
    return {"fixtures": fixtures}


@router.post("/bet", status_code=http_status.HTTP_201_CREATED)
async def place_bet(
    bet_request: CreateBetRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    logger.info(f"User {user.email} is placing a bet: {bet_request}")
    try:
        bet = create_bet(
            db=db,
            user=user,
            fixture_id=bet_request.fixture_id,
            choice=bet_request.choice,
            stake=bet_request.stake,
        )
        logger.info(f"User {user.email} placed bet={bet}")
        if not bet:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail="Failed to create bet",
            )

        return {"bet": bet, "message": "Bet placed successfully"}
    except ClientSideError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error placing bet: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while placing the bet",
        )


@router.get("/bet")
async def get_my_bets(
    outcome: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get all bets for the authenticated user"""
    if outcome:
        allowed = {e.value for e in BetOutcome}
        if outcome not in allowed:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bet outcome: {outcome}",
            )

    bets = get_user_bets(db, user.id, outcome=outcome, limit=limit)
    return {"bets": bets}


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)):
    return {
        "id": str(user.id),
        "status": user.status,
        "cognito_uuid": user.cognito_uuid,
        "email": user.email,
        "balance": str(user.balance),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }
