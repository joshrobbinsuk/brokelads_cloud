"""shirt identity

Replace the emoji-disc avatar with a customisable shirt: drop the `avatar`
string column and add a nullable JSON `shirt` column on `user`. Existing avatar
values are dropped by design (users re-pick; invites not yet sent). Tiny-table
column change — instant, no lock concern.

Revision ID: c58fc7d4594c
Revises: 72b152bf1095
Create Date: 2026-07-14 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c58fc7d4594c'
down_revision: Union[str, None] = '72b152bf1095'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('user', 'avatar')
    op.add_column('user', sa.Column('shirt', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('user', 'shirt')
    op.add_column('user', sa.Column('avatar', sa.String(length=20), nullable=True))
