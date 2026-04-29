import json
from collections.abc import AsyncIterator
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
from ..pundit import build_pundit_context, stream_pundit_response
from .utils.cognito import verify_token
from .utils.user import get_current_user
from ..models import User, BetOutcome

from .queries import (
    fetch_non_started_fixtures_with_odds,
    fetch_visible_fixture_slate_by_ids,
    create_bet,
    get_recent_user_bets_for_pundit,
    get_user_bets,
    ClientSideError,
)
from .schemas import CreateBetRequest
from .pundit_schemas import AskPunditRequest

router = APIRouter(prefix="/client", tags=["client"])


def _encode_sse_event(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.get("/fixture")
async def get_fixtures(
    search: str | None = None,
    db: Session = Depends(get_db),
    _claims: dict[str, Any] = Depends(verify_token),
) -> dict[str, Any]:
    fixtures = fetch_non_started_fixtures_with_odds(db, search)
    return {"fixtures": jsonable_encoder(fixtures)}


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
    except Exception as e:
        logger.error(f"Error placing bet: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while placing the bet",
        )


@router.get("/bet")
async def get_my_bets(
    search: str | None = None,
    outcome: str | None = None,
    limit: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Get all bets for the authenticated user"""
    if outcome:
        allowed = {e.value for e in BetOutcome}
        if outcome not in allowed:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid bet outcome: {outcome}",
            )
    bets = get_user_bets(db, user.id, outcome, search, limit)
    return {"bets": jsonable_encoder(bets)}


@router.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {
        "id": str(user.id),
        "status": user.status,
        "cognito_uuid": user.cognito_uuid,
        "email": user.email,
        "balance": str(user.balance),
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


@router.post("/pundit")
async def ask_pundit(
    pundit_request: AskPunditRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    fixtures = fetch_visible_fixture_slate_by_ids(
        db=db,
        fixture_ids=pundit_request.fixture_ids,
    )
    returned_fixture_ids = {fixture.id for fixture in fixtures}
    invalid_fixture_ids = [
        fixture_id
        for fixture_id in list(dict.fromkeys(pundit_request.fixture_ids))
        if fixture_id not in returned_fixture_ids
    ]
    if invalid_fixture_ids:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=(
                "Fixtures are outside the current visible slate: "
                f"{', '.join(invalid_fixture_ids)}"
            ),
        )

    recent_bets = get_recent_user_bets_for_pundit(db=db, user_id=user.id)
    context = build_pundit_context(
        user=user,
        fixtures=fixtures,
        recent_bets=recent_bets,
        conversation=pundit_request.conversation,
    )

    async def event_stream() -> AsyncIterator[str]:
        async for event in stream_pundit_response(context):
            yield _encode_sse_event(event.event, event.data)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
