"""Dev-only local seed CLI: `python -m src.dev.seed <fixtures|bets|resolve|all>`.

Drives the REAL ingestion + settlement code with controlled mock data so the
whole loop (fixtures -> odds -> bets -> results -> settlement -> balances) can be
exercised against a local DB without RapidAPI. The only thing faked is the API
response payload; everything downstream is production code.

Isolation: this module is never imported by the running app. Its only env check
is the prod seatbelt below.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from ..client.cup import get_or_create_current_cup, get_or_create_entry
from ..client.queries import create_bet
from ..models import Bet, BetOutcome, CupEntry, Fixture, FixtureResult, League, User
from ..rapid_api.internal_queries import save_new_fixtures, update_fixtures
from ..rapid_api.jobs import run_settle_bets, run_settle_voided_bets
from ..rapid_api.schemas.fixture import Fixture as FixtureSchema, UpdateFixture
from ..rapid_api.schemas.odds import Odds as OddsSchema
from ..settings import DATABASE_URL, ENVIRONMENT
from ..utils.weeks import current_week_window

SEED_LEAGUE_RAPID_ID = 999001
SEED_FIXTURE_RAPID_ID_BASE = 900000  # fixtures are +1..+N

# Synthetic user for the self-contained loop. Reserved namespace so it never
# collides with a real Cognito account.
SEED_USER_EMAIL = "seed-user@brokelads.dev"
SEED_USER_COGNITO_UUID = "seed-user-cognito"


@dataclass(frozen=True)
class SeedFixturePlan:
    """One seeded match plus the bet placed on it and the result it resolves to.

    `home_goals`/`away_goals`/`result_status` drive the mock results payload;
    `choice` drives the bet. Together they pin the settlement outcome so every
    path (WIN / LOSE / VOID) is exercised deterministically.
    """

    offset: int  # added to SEED_FIXTURE_RAPID_ID_BASE for the rapid_api_id
    home_team: str
    away_team: str
    choice: FixtureResult
    home_goals: int
    away_goals: int
    result_status: str  # "FT" -> settled win/lose; a voided status -> refunded


SEED_PLANS: list[SeedFixturePlan] = [
    SeedFixturePlan(1, "Arsenal", "Chelsea", FixtureResult.HOME, 2, 0, "FT"),  # WON
    SeedFixturePlan(2, "Liverpool", "Everton", FixtureResult.HOME, 3, 1, "FT"),  # WON
    SeedFixturePlan(3, "Spurs", "Fulham", FixtureResult.DRAW, 1, 1, "FT"),  # WON
    SeedFixturePlan(4, "Brighton", "Wolves", FixtureResult.HOME, 0, 2, "FT"),  # LOST
    SeedFixturePlan(5, "Newcastle", "Villa", FixtureResult.AWAY, 0, 1, "FT"),  # WON
    SeedFixturePlan(6, "Leeds", "Burnley", FixtureResult.HOME, 0, 0, "PST"),  # VOIDED
]


def _check_seatbelt() -> None:
    """Refuse to run against anything that looks like prod. Dev-only guard."""
    if ENVIRONMENT not in ("dev", "local"):
        raise SystemExit(
            f"Refusing to seed: ENVIRONMENT={ENVIRONMENT!r} is not dev/local."
        )
    host = urlparse(DATABASE_URL or "").hostname or ""
    # "db" is the docker-compose Postgres service name; the rest are host-side.
    if host not in ("localhost", "127.0.0.1", "db"):
        raise SystemExit(f"Refusing to seed: DATABASE_URL host {host!r} is not local.")


def _kick_off_for(offset: int) -> datetime:
    """A deterministic kick-off inside the current civil week so create_bet's
    week-window check passes. Spread across the week by offset."""
    week_start, week_end = current_week_window(datetime.now(timezone.utc))
    # 1..6 days into the week keeps every fixture strictly inside the window.
    kick_off = week_start.replace(
        hour=12, minute=0, second=0, microsecond=0
    ) + timedelta(hours=offset * 24)
    if kick_off >= week_end:
        raise SystemExit("Seed kick-off fell outside the current week window.")
    return kick_off


def _fixture_payload(plan: SeedFixturePlan) -> FixtureSchema:
    kick_off = _kick_off_for(plan.offset)
    return FixtureSchema.model_validate(
        {
            "fixture": {
                "id": SEED_FIXTURE_RAPID_ID_BASE + plan.offset,
                "timestamp": int(kick_off.timestamp()),
                "venue": {"name": "Seed Stadium"},
                "status": {"short": "NS"},
            },
            "teams": {
                "home": {"name": plan.home_team, "logo": "home.png"},
                "away": {"name": plan.away_team, "logo": "away.png"},
            },
        }
    )


def _odds_payload(bl_id: str, rapid_api_id: int) -> OddsSchema:
    odds = OddsSchema.model_validate(
        {
            "fixture": {"id": rapid_api_id},
            "bookmakers": [
                {
                    "id": 1,
                    "name": "SeedBook",
                    "bets": [
                        {
                            "id": 1,
                            "name": "Match Winner",
                            "values": [
                                {"value": "Home", "odd": "2.00"},
                                {"value": "Draw", "odd": "3.00"},
                                {"value": "Away", "odd": "4.00"},
                            ],
                        }
                    ],
                }
            ],
        }
    )
    odds.bl_id = bl_id
    return odds


def _result_payload(plan: SeedFixturePlan, bl_id: str) -> UpdateFixture:
    kick_off = _kick_off_for(plan.offset)
    update = UpdateFixture.model_validate(
        {
            "fixture": {
                "id": SEED_FIXTURE_RAPID_ID_BASE + plan.offset,
                "timestamp": int(kick_off.timestamp()),
                "venue": {"name": "Seed Stadium"},
                "status": {"short": plan.result_status},
            },
            "goals": {"home": plan.home_goals, "away": plan.away_goals},
        }
    )
    update.bl_id = bl_id
    return update


def _ensure_seed_league(db: Session) -> League:
    """The client board hides inactive leagues, so the seed league must be active."""
    league = (
        db.query(League).filter(League.rapid_api_id == SEED_LEAGUE_RAPID_ID).first()
    )
    if league is None:
        league = League(
            rapid_api_id=SEED_LEAGUE_RAPID_ID,
            name="BrokeLads Seed League",
            display_name="BrokeLads Seed League",
            active=True,
            logo="seed.png",
            country="Devland",
            type="League",
        )
        db.add(league)
        db.commit()
        db.refresh(league)
    elif not league.active:
        league.active = True
        db.commit()
        db.refresh(league)
    return league


def _seed_fixtures(db: Session) -> list[Fixture]:
    """Ensure the seed league + 6 mock fixtures (with odds) exist. Idempotent via
    the reserved rapid_api_id range (save_new_fixtures dedupes on rapid_api_id)."""
    league = _ensure_seed_league(db)

    save_new_fixtures(
        db, [_fixture_payload(plan) for plan in SEED_PLANS], league_id=league.id
    )

    fixtures = _seeded_fixtures(db)
    missing_odds = [f for f in fixtures if not f.has_odds]
    if missing_odds:
        update_fixtures(
            db,
            [
                _odds_payload(bl_id=f.id, rapid_api_id=f.rapid_api_id)
                for f in missing_odds
            ],
        )
        db.expire_all()
        fixtures = _seeded_fixtures(db)
    return fixtures


def _seeded_fixtures(db: Session) -> list[Fixture]:
    rapid_ids = [SEED_FIXTURE_RAPID_ID_BASE + p.offset for p in SEED_PLANS]
    by_rapid = {
        f.rapid_api_id: f
        for f in db.query(Fixture).filter(Fixture.rapid_api_id.in_(rapid_ids)).all()
    }
    return [by_rapid[rid] for rid in rapid_ids if rid in by_rapid]


def _get_or_create_seed_user(db: Session) -> User:
    user = db.query(User).filter(User.email == SEED_USER_EMAIL).first()
    if user is None:
        user = User(
            email=SEED_USER_EMAIL,
            cognito_uuid=SEED_USER_COGNITO_UUID,
            username="seed_bot",
            avatar="fox-red",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.avatar is None:
        user.avatar = "fox-red"
        db.commit()
        db.refresh(user)
    return user


def _place_bets(db: Session, user: User) -> list[Bet]:
    """Place the planned spread of bets via the REAL create_bet (real stake debit
    + LedgerEntry). Skips fixtures the user has already bet on so re-runs
    don't double-stake."""
    fixtures = _seeded_fixtures(db)
    by_rapid = {f.rapid_api_id: f for f in fixtures}

    existing_fixture_ids = {
        b.fixture_id for b in db.query(Bet).filter(Bet.user_id == user.id).all()
    }

    placed: list[Bet] = []
    for plan in SEED_PLANS:
        fixture = by_rapid.get(SEED_FIXTURE_RAPID_ID_BASE + plan.offset)
        if fixture is None or fixture.id in existing_fixture_ids:
            continue
        result = create_bet(
            db,
            user=user,
            fixture_id=fixture.id,
            choice=plan.choice,
            stake=Decimal("10.00"),
        )
        bet = db.query(Bet).filter(Bet.id == result["id"]).one()
        placed.append(bet)
    return placed


def _resolve(db: Session) -> None:
    """Build a mock results payload for the seeded fixtures -> real results
    parse/write -> real settlement (win/lose + voided-refund)."""
    fixtures = _seeded_fixtures(db)
    by_rapid = {f.rapid_api_id: f for f in fixtures}

    updates: list[UpdateFixture] = []
    for plan in SEED_PLANS:
        fixture = by_rapid.get(SEED_FIXTURE_RAPID_ID_BASE + plan.offset)
        if fixture is None:
            continue
        updates.append(_result_payload(plan, bl_id=fixture.id))

    update_fixtures(db, updates)
    run_settle_bets(db)
    run_settle_voided_bets(db)


def _entry_for(db: Session, user: User) -> CupEntry | None:
    cup = get_or_create_current_cup(db, datetime.now(timezone.utc))
    return (
        db.query(CupEntry)
        .filter(CupEntry.cup_id == cup.id, CupEntry.user_id == user.id)
        .first()
    )


def cmd_fixtures(db: Session) -> None:
    fixtures = _seed_fixtures(db)
    with_odds = sum(1 for f in fixtures if f.has_odds)
    print(f"fixtures: {len(fixtures)} seeded, {with_odds} with odds.")


def cmd_bets(db: Session, email: str | None) -> None:
    if email is not None:
        user = db.query(User).filter(User.email == email).first()
        if user is None:
            raise SystemExit(f"No user with email {email!r}.")
    else:
        user = _get_or_create_seed_user(db)
        cup = get_or_create_current_cup(db, datetime.now(timezone.utc))
        get_or_create_entry(db, cup, user)

    placed = _place_bets(db, user)
    print(f"bets: placed {len(placed)} for {user.email}.")


def cmd_resolve(db: Session) -> None:
    _resolve(db)
    print("resolve: results written and settlement run.")


def cmd_all(db: Session) -> None:
    _seed_fixtures(db)

    user = _get_or_create_seed_user(db)
    cup = get_or_create_current_cup(db, datetime.now(timezone.utc))
    entry = get_or_create_entry(db, cup, user)
    balance_before = entry.balance

    _place_bets(db, user)
    _resolve(db)

    _print_summary(db, user, balance_before)


def _print_summary(db: Session, user: User, balance_before: Decimal) -> None:
    fixtures = _seeded_fixtures(db)
    by_id = {f.id: f for f in fixtures}
    bets = (
        db.query(Bet)
        .filter(Bet.user_id == user.id)
        .order_by(Bet.created_at.asc())
        .all()
    )
    entry = _entry_for(db, user)
    balance_after = entry.balance if entry is not None else Decimal("0")

    print("\n=== seed all summary ===")
    print(f"user: {user.email}")
    print(f"entry balance before: {balance_before}")
    for bet in bets:
        fixture = by_id.get(bet.fixture_id)
        label = str(fixture) if fixture is not None else bet.fixture_id
        print(
            f"  {label}: choice={bet.choice} stake={bet.stake} "
            f"returns={bet.returns} -> {bet.outcome}"
        )
    print(f"entry balance after: {balance_after}")
    won = sum(1 for b in bets if b.outcome == BetOutcome.WON.value)
    lost = sum(1 for b in bets if b.outcome == BetOutcome.LOST.value)
    voided = sum(1 for b in bets if b.outcome == BetOutcome.VOIDED.value)
    print(f"outcomes: WON={won} LOST={lost} VOIDED={voided}")


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m src.dev.seed")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("fixtures", help="Seed league + 6 mock fixtures with odds.")
    bets_parser = sub.add_parser("bets", help="Place a spread of bets.")
    bets_parser.add_argument(
        "--email", default=None, help="Target an existing user by email."
    )
    sub.add_parser("resolve", help="Write results and run settlement.")
    sub.add_parser("all", help="fixtures -> bets -> resolve, with a summary.")

    args = parser.parse_args()

    _check_seatbelt()

    from ..database import SessionLocal

    db = SessionLocal()
    try:
        if args.command == "fixtures":
            cmd_fixtures(db)
        elif args.command == "bets":
            cmd_bets(db, args.email)
        elif args.command == "resolve":
            cmd_resolve(db)
        elif args.command == "all":
            cmd_all(db)
    finally:
        db.close()


if __name__ == "__main__":
    main()
