"""events, odds_struck, fixture unique index

Additive only (see CLAUDE.md migration rule): a nullable column + a small
backfill + an index on a tiny table + a new table. Nothing destructive, nothing
that can hang startup against a live writer.

Revision ID: a8f230ad7da9
Revises: 72b152bf1095
Create Date: 2026-07-11 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a8f230ad7da9"
down_revision: Union[str, None] = "72b152bf1095"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Record the price each bet was struck at.
    op.add_column("bet", sa.Column("odds_struck", sa.Numeric(5, 2), nullable=True))
    # Backfill from the fixture's write-once odds by the bet's choice. This is
    # exact; the (returns - stake)/stake derivation is lossy, so do not use it.
    op.execute(
        "UPDATE bet SET odds_struck = f.home_odds "
        "FROM fixture f WHERE bet.fixture_id = f.id AND bet.choice = 'HOME'"
    )
    op.execute(
        "UPDATE bet SET odds_struck = f.away_odds "
        "FROM fixture f WHERE bet.fixture_id = f.id AND bet.choice = 'AWAY'"
    )
    op.execute(
        "UPDATE bet SET odds_struck = f.draw_odds "
        "FROM fixture f WHERE bet.fixture_id = f.id AND bet.choice = 'DRAW'"
    )

    # 2. Make the match's natural key a DB invariant (data is already clean).
    op.create_index(
        "uq_fixture_rapid_api_id", "fixture", ["rapid_api_id"], unique=True
    )

    # 3. Append-only domain-event log. No FK on user_id: events outlive user
    #    hard-delete. `seq` is a Postgres identity for total ordering when
    #    created_at ties within a transaction.
    op.create_table(
        "event",
        sa.Column("seq", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("seq"),
    )
    op.create_index(op.f("ix_event_id"), "event", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_event_id"), table_name="event")
    op.drop_table("event")
    op.drop_index("uq_fixture_rapid_api_id", table_name="fixture")
    op.drop_column("bet", "odds_struck")
