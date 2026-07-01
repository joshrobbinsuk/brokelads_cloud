"""weekly cup: cup + cup_entry tables, bet.cup_entry_id, close_cups job

Additive only — creates two new tables, adds one nullable FK column to bet, and
seeds the close_cups JobControl row. No deletes, no data backfill, no table
rewrites, no long locks (mirrors the leagues migration's constraint that broke
a live App Runner deploy when it took locks). Legacy bets keep
cup_entry_id IS NULL and are ignored by all cup logic.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-01 12:00:00.000000

"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "cup",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("week_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("week_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("week_start"),
    )
    op.create_index(op.f("ix_cup_id"), "cup", ["id"], unique=False)

    op.create_table(
        "cup_entry",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cup_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("balance", sa.Numeric(precision=19, scale=2), nullable=False),
        sa.Column("is_winner", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["cup_id"], ["cup.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("cup_id", "user_id", name="uq_cup_entry"),
    )
    op.create_index(op.f("ix_cup_entry_id"), "cup_entry", ["id"], unique=False)

    op.add_column(
        "bet",
        sa.Column("cup_entry_id", sa.String(length=36), nullable=True),
    )
    op.create_foreign_key(
        "fk_bet_cup_entry_id",
        "bet",
        "cup_entry",
        ["cup_entry_id"],
        ["id"],
    )

    # Widen money columns from NUMERIC(5,2) (max 999.99) to NUMERIC(19,2): cup
    # balances start at 1000 and grow, so stakes/returns/audit rows overflow the
    # old precision. Increasing precision is a metadata-only change on Postgres —
    # no data rewrite, no long lock.
    op.alter_column("bet", "stake", type_=sa.Numeric(19, 2))
    op.alter_column("bet", "returns", type_=sa.Numeric(19, 2))
    op.alter_column(
        "transaction_record", "user_balance_before", type_=sa.Numeric(19, 2)
    )
    op.alter_column(
        "transaction_record", "user_balance_after", type_=sa.Numeric(19, 2)
    )

    job_control = sa.table(
        "job_control",
        sa.column("id", sa.String(36)),
        sa.column("job_name", sa.String(64)),
        sa.column("enabled", sa.Boolean()),
        sa.column("min_interval_seconds", sa.Integer()),
        sa.column("last_run_at", sa.DateTime(timezone=True)),
    )
    op.bulk_insert(
        job_control,
        [
            {
                "id": str(uuid4()),
                "job_name": "close_cups",
                "enabled": True,
                "min_interval_seconds": 300,
                "last_run_at": None,
            }
        ],
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM job_control WHERE job_name = 'close_cups'"))
    op.alter_column(
        "transaction_record", "user_balance_after", type_=sa.Numeric(5, 2)
    )
    op.alter_column(
        "transaction_record", "user_balance_before", type_=sa.Numeric(5, 2)
    )
    op.alter_column("bet", "returns", type_=sa.Numeric(5, 2))
    op.alter_column("bet", "stake", type_=sa.Numeric(5, 2))
    op.drop_constraint("fk_bet_cup_entry_id", "bet", type_="foreignkey")
    op.drop_column("bet", "cup_entry_id")
    op.drop_index(op.f("ix_cup_entry_id"), table_name="cup_entry")
    op.drop_table("cup_entry")
    op.drop_index(op.f("ix_cup_id"), table_name="cup")
    op.drop_table("cup")
