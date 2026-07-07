import json
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status as http_status,
    Query,
)
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session


from ..utils.logging import logger
from ..database import get_db
from .utils.cognito import verify_token
from .utils.user import get_current_user
from ..models import User, BetOutcome

from .queries import (
    fetch_non_started_fixtures_with_odds,
    fetch_visible_fixture_slate_by_ids,
    get_active_leagues,
    get_recent_user_bets_for_pundit,
    create_bet,
    get_user_bets,
    increment_pundit_usage,
    pundit_count_today,
    set_username,
    ClientSideError,
    UsernameTakenError,
)
from . import cup as cup_queries
from .schemas import (
    CreateBetRequest,
    CupSummary,
    FixtureResponse,
    LeagueOut,
    SetUsernameRequest,
)
from .pundit_schemas import AskPunditRequest
from .pundit import build_pundit_context, is_unlimited, stream_pundit_response
from ..settings import PUNDIT_DAILY_LIMIT
from ..utils.weeks import london_today

router = APIRouter(prefix="/client", tags=["client"])


@router.get("/fixture")
async def get_fixtures(
    search: str | None = None,
    league_id: str | None = None,
    db: Session = Depends(get_db),
    _claims: dict[str, Any] = Depends(verify_token),
) -> dict[str, Any]:
    try:
        fixtures = fetch_non_started_fixtures_with_odds(db, search, league_id)
        return {
            "fixtures": [
                FixtureResponse.model_validate(fixture).model_dump(mode="json")
                for fixture in fixtures
            ]
        }
    except Exception:
        logger.exception("Error fetching fixtures")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching fixtures",
        )


@router.get("/league")
async def get_leagues(
    db: Session = Depends(get_db),
    _claims: dict[str, Any] = Depends(verify_token),
) -> dict[str, Any]:
    try:
        leagues = get_active_leagues(db)
        return {
            "leagues": [
                LeagueOut.model_validate(league).model_dump(mode="json")
                for league in leagues
            ]
        }
    except Exception:
        logger.exception("Error fetching leagues")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching leagues",
        )


@router.post("/bet", status_code=http_status.HTTP_201_CREATED)
async def place_bet(
    bet_request: CreateBetRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
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

        return {"bet": jsonable_encoder(bet), "message": "Bet placed successfully"}
    except ClientSideError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception:
        logger.exception("Error placing bet")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while placing the bet",
        )


@router.get("/bet")
async def get_my_bets(
    search: str | None = None,
    outcome: str | None = None,
    cup_id: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get bets for the authenticated user, scoped to a cup (defaults to the
    current cup) so the client can page back through previous weeks."""
    if outcome:
        allowed = {e.value for e in BetOutcome}
        if outcome not in allowed:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bet outcome: {outcome}",
            )
    if cup_id is None:
        current = cup_queries.get_current_cup(db, datetime.now(timezone.utc))
        cup_id = current.id if current is not None else None
    bets = get_user_bets(db, user.id, outcome, search, limit, cup_id)
    return {"bets": jsonable_encoder(bets)}


@router.post("/pundit")
async def ask_pundit(
    request: AskPunditRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    if not is_unlimited(user.email):
        today = london_today(datetime.now(timezone.utc))
        if pundit_count_today(db, user, today) >= PUNDIT_DAILY_LIMIT:
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"You've used all {PUNDIT_DAILY_LIMIT} of today's pundit "
                    "questions. Try again tomorrow."
                ),
            )
        increment_pundit_usage(db, user, today)

    # Ids the client no longer sees as bettable (kicked off, week rolled over,
    # odds pulled) simply fall out of the slate here — the pundit reasons over
    # whatever is still visible rather than rejecting the whole conversation.
    fixtures = fetch_visible_fixture_slate_by_ids(db, request.fixture_ids)

    recent_bets = get_recent_user_bets_for_pundit(db, user.id)
    context = build_pundit_context(user, fixtures, recent_bets, request.conversation)

    async def event_source() -> AsyncIterator[str]:
        async for event in stream_pundit_response(context):
            yield f"event: {event.event}\ndata: {json.dumps(event.data)}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/cup/current")
async def get_current_cup_view(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        now = datetime.now(timezone.utc)
        cup = cup_queries.get_current_cup(db, now)
        balance = str(cup_queries.current_balance(db, user, now))
        if cup is None:
            return {
                "cup": None,
                "your_balance": balance,
                "your_rank": None,
                "leaderboard": [],
            }
        board = cup_queries.leaderboard(db, cup)
        your_rank = next(
            (row["rank"] for row in board if row["user_id"] == user.id), None
        )
        return {
            "cup": CupSummary.model_validate(cup).model_dump(mode="json"),
            "your_balance": balance,
            "your_rank": your_rank,
            "leaderboard": board,
        }
    except Exception:
        logger.exception("Error fetching current cup")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching the current cup",
        )


@router.get("/cup/{cup_id}")
async def get_cup_view(
    cup_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        cup = cup_queries.get_cup_by_id(db, cup_id)
        if cup is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail="Cup not found",
            )
        return {
            "cup": CupSummary.model_validate(cup).model_dump(mode="json"),
            "leaderboard": cup_queries.leaderboard(db, cup),
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception(f"Error fetching cup {cup_id}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching the cup",
        )


@router.get("/cups")
async def list_cups_view(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        cups = cup_queries.list_cups(db)
        return {
            "cups": [
                CupSummary.model_validate(cup).model_dump(mode="json") for cup in cups
            ]
        }
    except Exception:
        logger.exception("Error listing cups")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while listing cups",
        )


@router.get("/me")
async def get_me(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        now = datetime.now(timezone.utc)
        return {
            "id": str(user.id),
            "status": user.status,
            "cognito_uuid": user.cognito_uuid,
            "email": user.email,
            "username": user.username,
            "balance": str(cup_queries.current_balance(db, user, now)),
            "cups_won": cup_queries.cups_won(db, user),
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }
    except Exception:
        logger.exception("Error fetching current user")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while fetching the user",
        )


@router.put("/me/username")
async def set_my_username(
    payload: SetUsernameRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    try:
        updated = set_username(db, user, payload.username)
        return {"username": updated.username}
    except UsernameTakenError:
        raise HTTPException(
            status_code=http_status.HTTP_409_CONFLICT,
            detail="That username is already taken",
        )
    except ClientSideError as e:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception:
        logger.exception("Error setting username")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while setting the username",
        )
