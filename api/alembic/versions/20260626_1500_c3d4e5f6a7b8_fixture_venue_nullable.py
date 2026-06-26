"""make fixture.venue nullable

API-Football returns fixture.venue.name = null for fixtures with no assigned
venue yet (future / international fixtures), which must ingest. Metadata-only
ALTER — not lock-heavy.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-26 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "fixture",
        "venue",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    # Existing NULLs would violate the restored NOT NULL, so coalesce first.
    op.execute(sa.text("UPDATE fixture SET venue = '' WHERE venue IS NULL"))
    op.alter_column(
        "fixture",
        "venue",
        existing_type=sa.String(length=255),
        nullable=False,
    )
