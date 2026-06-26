"""drop league.last_fixture_fetch_at (per-league cooldown removed)

The per-league fetch cooldown was redundant — JobControl.min_interval_seconds
throttles job frequency and the below-target count gate stops a league once it
holds N_FIXTURES_PER_LEAGUE. Metadata-only DROP COLUMN, not lock-heavy.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-06-26 17:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("league", "last_fixture_fetch_at")


def downgrade() -> None:
    op.add_column(
        "league",
        sa.Column(
            "last_fixture_fetch_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
