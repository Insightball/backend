"""merge_trial

Revision ID: 4d3638c03f18
Revises: a032606d3f20, add_trial_fields
Create Date: 2026-02-27 13:25:00.159178

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = '4d3638c03f18'
down_revision: Union[str, None] = ('a032606d3f20', 'add_trial_fields')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
