"""drop vestigial user.balance column

The weekly-cup feature moved the betting money path onto CupEntry.balance,
leaving User.balance unused. Dropping the column is metadata-only/fast on
Postgres (no table rewrite, no long lock). No data operations — reversible via
downgrade(), which re-adds the column with its original type/default.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-07-01 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("user", "balance")


def downgrade() -> None:
    op.add_column(
        "user",
        sa.Column(
            "balance",
            sa.Numeric(precision=19, scale=2),
            nullable=False,
            server_default="100.00",
        ),
    )
    op.alter_column("user", "balance", server_default=None)
