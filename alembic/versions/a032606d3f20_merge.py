"""merge

Revision ID: a032606d3f20
Revises: 001, add_soft_delete_users
Create Date: 2026-02-27 13:20:37.224392

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'a032606d3f20'
down_revision: Union[str, None] = ('001', 'add_soft_delete_users')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
