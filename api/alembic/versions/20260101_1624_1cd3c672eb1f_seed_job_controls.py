"""seed job controls

Revision ID: 1cd3c672eb1f
Revises: a14fd64d977b
Create Date: 2026-01-01 16:24:09.960106

"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1cd3c672eb1f"
down_revision: Union[str, None] = "a14fd64d977b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
                "job_name": "fetch_fixtures",
                "enabled": True,
                "min_interval_seconds": 119,
                "last_run_at": None,
            },
            {
                "id": str(uuid4()),
                "job_name": "fetch_odds",
                "enabled": True,
                "min_interval_seconds": 259,
                "last_run_at": None,
            },
            {
                "id": str(uuid4()),
                "job_name": "fetch_fixture_updates",
                "enabled": True,
                "min_interval_seconds": 259,
                "last_run_at": None,
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM job_control
            WHERE job_name IN (
              'fetch_fixtures_by_league',
              'fetch_odds_by_fixture',
              'fetch_fixture_updates'
            )
            """
        )
    )
