"""add user.avatar

App-level avatar id (`<icon>-<colour>`, e.g. "fox-red") from the fixed set in
settings.AVATAR_IDS. Nullable so existing users keep the FE fallback disc until
they pick one.

The ADD COLUMN is metadata-only/fast (nullable, no default, no index, no
backfill) — additive only, per CLAUDE.md (migrations run at container start;
locks/rewrites hang deploys).

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-07-07 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c9d0e1f2a3b4"
down_revision: Union[str, None] = "b8c9d0e1f2a3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("avatar", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "avatar")
