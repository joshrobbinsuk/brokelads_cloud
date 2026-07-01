"""add user.username

App-level display name, decoupled from Cognito's email auth. Nullable because a
User row is created (on first authed request) before the user reaches the
first-run gate that sets it.

The ADD COLUMN is metadata-only/fast (nullable, no default). The unique index is
functional on lower(username) so case-insensitive uniqueness is a real DB
invariant; lower(NULL) is NULL so multiple null usernames remain allowed.
NOTE: building the index takes a brief ACCESS EXCLUSIVE lock and scans the
table — negligible here (the user table is tiny), but if it ever grows large,
switch to CONCURRENTLY inside an autocommit block.

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
    op.add_column("user", sa.Column("username", sa.String(length=20), nullable=True))
    op.create_index(
        "uq_user_username_lower",
        "user",
        [sa.text("lower(username)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_user_username_lower", table_name="user")
    op.drop_column("user", "username")
