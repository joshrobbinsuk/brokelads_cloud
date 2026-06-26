"""leagues metadata, fixture league fk, seed fetch_leagues

Additive only — no data wipe. Old fixtures keep a NULL league_id and are
backfilled in place by ingestion (save_new_fixtures) once their league is
ticked active; the client query hides leagueless fixtures meanwhile.

Revision ID: b2c3d4e5f6a7
Revises: f7df2ed679dc
Create Date: 2026-06-26 12:00:00.000000

"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "f7df2ed679dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("league", sa.Column("logo", sa.String(length=255), nullable=True))
    op.add_column("league", sa.Column("country", sa.String(length=255), nullable=True))
    op.add_column("league", sa.Column("type", sa.String(length=32), nullable=True))
    op.add_column(
        "league",
        sa.Column("last_fixture_fetch_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.add_column(
        "fixture", sa.Column("league_id", sa.String(length=36), nullable=True)
    )
    op.create_foreign_key(
        "fk_fixture_league_id",
        "fixture",
        "league",
        ["league_id"],
        ["id"],
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
                "job_name": "fetch_leagues",
                "enabled": True,
                "min_interval_seconds": 86400,
                "last_run_at": None,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM job_control WHERE job_name = 'fetch_leagues'")
    )
    op.drop_constraint("fk_fixture_league_id", "fixture", type_="foreignkey")
    op.drop_column("fixture", "league_id")
    op.drop_column("league", "last_fixture_fetch_at")
    op.drop_column("league", "type")
    op.drop_column("league", "country")
    op.drop_column("league", "logo")
