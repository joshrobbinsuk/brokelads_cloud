"""pundit_usage

Per-user, per-London-day counter backing the Ask-the-Pundit daily cap. The
unique constraint on (user_id, day) keeps it to one bucket row per user per
day (the count ceiling itself is enforced in the route, not the schema).

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
Create Date: 2026-07-01 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8c9d0e1f2a3"
down_revision: Union[str, None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pundit_usage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "day", name="uq_pundit_usage_user_day"),
    )
    op.create_index(
        op.f("ix_pundit_usage_id"), "pundit_usage", ["id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_pundit_usage_id"), table_name="pundit_usage")
    op.drop_table("pundit_usage")
