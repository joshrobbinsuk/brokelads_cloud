"""settle bet jobs

Revision ID: f7df2ed679dc
Revises: 1cd3c672eb1f
Create Date: 2026-01-02 17:07:26.812614

"""

from typing import Sequence, Union
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "f7df2ed679dc"
down_revision: Union[str, None] = "1cd3c672eb1f"
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
                "job_name": "settle_bets",
                "enabled": True,
                "min_interval_seconds": 59,
                "last_run_at": None,
            },
            {
                "id": str(uuid4()),
                "job_name": "settle_voided_bets",
                "enabled": True,
                "min_interval_seconds": 59,
                "last_run_at": None,
            },
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            """
            DELETE FROM job_control
            WHERE job_name IN ('settle_bets', 'settle_voided_bets')
            """
        )
    )
