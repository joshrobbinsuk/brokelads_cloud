"""add user.username

App-level display name, decoupled from Cognito's email auth. Nullable because a
User row is created (on first authed request) before the user reaches the
first-run gate that sets it. Adding a nullable column + unique index is
metadata-only/fast on Postgres — no table rewrite, no long lock.

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-07-01 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("username", sa.String(length=32), nullable=True))
    op.create_unique_constraint("uq_user_username", "user", ["username"])


def downgrade() -> None:
    op.drop_constraint("uq_user_username", "user", type_="unique")
    op.drop_column("user", "username")
