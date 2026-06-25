"""Pure parsing logic for the API-Football payloads — odds selection and the
DB-row transforms. No database or HTTP; these are the densest untested branches.
"""

from datetime import datetime, timezone

from src.rapid_api.schemas.fixture import (
    Fixture as FixtureSchema,
    RapidApiFixturesResponse,
    UpdateFixture as UpdateFixtureSchema,
)
from src.rapid_api.schemas.odds import (
    Odds,
    RapidApiOddsResponse,
)

# --- payload builders (shapes mirror the api-sports v3 responses) ---------------


def _match_winner_market(
    *, name: str = "Match Winner", drop: str | None = None, home: str = "2.50"
) -> dict:
    values = [
        {"value": "Home", "odd": home},
        {"value": "Draw", "odd": "3.20"},
        {"value": "Away", "odd": "2.80"},
    ]
    if drop:
        values = [v for v in values if v["value"] != drop]
    return {"id": 1, "name": name, "values": values}


def _odds(bookmakers: list[dict], fixture_id: int = 100) -> Odds:
    return Odds.model_validate(
        {"fixture": {"id": fixture_id}, "bookmakers": bookmakers}
    )


def _bookmaker(name: str, market: dict) -> dict:
    return {"id": 1, "name": name, "bets": [market]}


def _fixture_payload(
    *, fixture_id: int = 1, timestamp: int = 1893456000, status: str = "NS"
) -> dict:
    return {
        "fixture": {
            "id": fixture_id,
            "timestamp": timestamp,
            "venue": {"name": "Stadium"},
            "status": {"short": status},
        },
        "teams": {
            "home": {"name": "Home FC", "logo": "home.png"},
            "away": {"name": "Away FC", "logo": "away.png"},
        },
        "goals": {"home": None, "away": None},
    }


# --- odds selection ------------------------------------------------------------


class TestMatchWinnerSelection:
    def test_complete_match_winner_is_selected(self) -> None:
        odds = _odds([_bookmaker("Bet365", _match_winner_market())])
        assert odds.first_complete_odds() == {"Home": 2.50, "Draw": 3.20, "Away": 2.80}

    def test_incomplete_market_is_skipped(self) -> None:
        odds = _odds([_bookmaker("Bet365", _match_winner_market(drop="Draw"))])
        assert odds.first_complete_odds() is None

    def test_non_match_winner_market_is_ignored(self) -> None:
        # A complete Home/Draw/Away set under a different market name must not count.
        odds = _odds([_bookmaker("Bet365", _match_winner_market(name="Double Chance"))])
        assert odds.first_complete_odds() is None

    def test_first_bookmaker_with_complete_odds_wins(self) -> None:
        odds = _odds(
            [
                _bookmaker("Incomplete", _match_winner_market(drop="Away")),
                _bookmaker("Complete", _match_winner_market(home="1.90")),
            ]
        )
        assert odds.first_complete_odds() == {"Home": 1.90, "Draw": 3.20, "Away": 2.80}


class TestOddsToDbDict:
    def test_maps_to_row_with_bl_id(self) -> None:
        odds = _odds([_bookmaker("Bet365", _match_winner_market())], fixture_id=77)
        odds.bl_id = "internal-id"

        row = odds.to_db_dict()

        assert row == {
            "id": "internal-id",
            "rapid_api_id": 77,
            "home_odds": 2.50,
            "draw_odds": 3.20,
            "away_odds": 2.80,
        }

    def test_returns_none_when_no_complete_odds(self) -> None:
        odds = _odds([_bookmaker("Bet365", _match_winner_market(drop="Away"))])
        assert odds.to_db_dict() is None


class TestRapidApiOddsResponse:
    def test_returns_first_response_with_complete_odds(self) -> None:
        empty = {"fixture": {"id": 1}, "bookmakers": []}
        good = {
            "fixture": {"id": 2},
            "bookmakers": [_bookmaker("Bet365", _match_winner_market())],
        }
        resp = RapidApiOddsResponse.model_validate({"response": [empty, good]})

        selected = resp.first_complete_odds()
        assert selected is not None and selected.fixture.id == 2

    def test_returns_none_when_nothing_complete(self) -> None:
        resp = RapidApiOddsResponse.model_validate(
            {"response": [{"fixture": {"id": 1}, "bookmakers": []}]}
        )
        assert resp.first_complete_odds() is None


# --- fixture transforms --------------------------------------------------------


class TestFixtureToDbDict:
    def test_maps_payload_to_row(self) -> None:
        fixture = FixtureSchema.model_validate(
            _fixture_payload(fixture_id=42, status="NS")
        )

        row = fixture.to_db_dict()

        assert row["rapid_api_id"] == 42
        assert row["status"] == "NS"
        assert row["venue"] == "Stadium"
        assert row["home_team"] == "Home FC"
        assert row["away_team_logo"] == "away.png"
        assert row["kick_off"] == datetime(2030, 1, 1, tzinfo=timezone.utc)
        # New fixtures carry no odds or goals yet.
        assert row["home_odds"] is None and row["away_goals"] is None

    def test_carries_dead_keys_for_nonexistent_columns(self) -> None:
        # `voided`/`voided_message` are not columns on the Fixture model; the bulk
        # insert silently drops them. Documenting the cruft, not endorsing it.
        row = FixtureSchema.model_validate(_fixture_payload()).to_db_dict()
        assert "voided" in row and "voided_message" in row

    def test_response_alias_parses_response_key(self) -> None:
        resp = RapidApiFixturesResponse.model_validate(
            {"response": [_fixture_payload(fixture_id=7)]}
        )
        assert len(resp.data) == 1 and resp.data[0].info.id == 7


class TestUpdateFixtureToDbDict:
    def test_maps_goals_and_targets_internal_id(self) -> None:
        payload = _fixture_payload(fixture_id=42, status="FT")
        payload["goals"] = {"home": 2, "away": 1}
        update = UpdateFixtureSchema.model_validate(payload)
        update.bl_id = "internal-id"

        row = update.to_db_dict()

        assert row["id"] == "internal-id"
        assert row["rapid_api_id"] == 42
        assert row["status"] == "FT"
        assert row["home_goals"] == 2 and row["away_goals"] == 1
