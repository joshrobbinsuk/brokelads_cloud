"""The dev-only seeder drives the real ingestion + settlement path with mock
data. These tests prove the mock `fixtures` build inserts 6 fixtures with odds,
and that `resolve` settles the planned WIN / LOSE / VOID spread to the expected
cup-entry balance. This also exercises the ingestion parse path end-to-end.
"""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from src.client.cup import get_or_create_current_cup, get_or_create_entry
from src.dev import seed
from src.models import Bet, BetOutcome, Fixture
from src.settings import CUP_STARTING_STAKE


def test_fixtures_inserts_six_with_odds(db: Session) -> None:
    fixtures = seed._seed_fixtures(db)

    assert db.query(Fixture).count() == 6
    assert len(fixtures) == 6
    assert all(f.has_odds for f in fixtures)
    assert all(f.league is not None and f.league.active for f in fixtures)


def test_fixtures_is_idempotent(db: Session) -> None:
    seed._seed_fixtures(db)
    seed._seed_fixtures(db)

    assert db.query(Fixture).count() == 6


def _seed_user_with_entry(db: Session) -> None:
    user = seed._get_or_create_seed_user(db)
    cup = get_or_create_current_cup(db, datetime.now(timezone.utc))
    get_or_create_entry(db, cup, user)


def test_resolve_settles_win_lose_void_to_expected_balance(db: Session) -> None:
    seed._seed_fixtures(db)
    _seed_user_with_entry(db)
    user = seed._get_or_create_seed_user(db)

    placed = seed._place_bets(db, user)
    assert len(placed) == 6

    entry = seed._entry_for(db, user)
    assert entry is not None
    # 6 bets x 10 stake debited from the 1000 starting stake.
    assert entry.balance == CUP_STARTING_STAKE - Decimal("60.00")

    seed._resolve(db)

    db.expire_all()
    bets_by_choice_fixture = {(b.choice, b.fixture_id): b for b in db.query(Bet).all()}
    outcomes = sorted(b.outcome for b in bets_by_choice_fixture.values())
    assert outcomes == sorted(
        [
            BetOutcome.WON.value,  # offset 1 HOME
            BetOutcome.WON.value,  # offset 2 HOME
            BetOutcome.WON.value,  # offset 3 DRAW
            BetOutcome.LOST.value,  # offset 4 HOME (away won)
            BetOutcome.WON.value,  # offset 5 AWAY
            BetOutcome.VOIDED.value,  # offset 6 PST
        ]
    )

    entry = seed._entry_for(db, user)
    assert entry is not None
    # Decimal odds already include the stake, so returns = stake * odds.
    # Debits: 6 x 10 = 60 -> 940.
    # Wins:  20 (home@2) + 20 (home@2) + 30 (draw@3) + 40 (away@4) = 110.
    # Void refund: 10. Final = 940 + 110 + 10 = 1060.
    assert entry.balance == CUP_STARTING_STAKE + Decimal("60.00")


def test_resolve_refunds_the_voided_stake(db: Session) -> None:
    seed._seed_fixtures(db)
    _seed_user_with_entry(db)
    user = seed._get_or_create_seed_user(db)
    seed._place_bets(db, user)
    seed._resolve(db)

    db.expire_all()
    voided = db.query(Bet).filter(Bet.outcome == BetOutcome.VOIDED.value).one()
    assert voided.stake == Decimal("10.00")
