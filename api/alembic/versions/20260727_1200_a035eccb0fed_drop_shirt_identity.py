"""drop shirt identity

Username is now the only user-editable identity, so the JSON `shirt` column on
`user` goes. Destructive by design — existing shirts are discarded, not
preserved. Tiny-table column drop: instant, no lock concern. Merge order: the
bl-fe `feature/ladbrokes-reskin` PR (which stops sending/reading the field)
must merge and deploy before this branch lands on `dev`.

Revision ID: a035eccb0fed
Revises: c58fc7d4594c
Create Date: 2026-07-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a035eccb0fed'
down_revision: Union[str, None] = 'c58fc7d4594c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('user', 'shirt')


def downgrade() -> None:
    op.add_column('user', sa.Column('shirt', sa.JSON(), nullable=True))
