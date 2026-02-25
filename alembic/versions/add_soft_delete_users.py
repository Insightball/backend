"""add soft delete to users

Revision ID: add_soft_delete_users
Revises: 
Create Date: 2026-02-25
"""
from alembic import op
import sqlalchemy as sa

revision = 'add_soft_delete_users'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('recovery_token', sa.String(), nullable=True))
    op.add_column('users', sa.Column('recovery_token_expires', sa.DateTime(), nullable=True))
    op.create_index('ix_users_recovery_token', 'users', ['recovery_token'], unique=True)

def downgrade():
    op.drop_index('ix_users_recovery_token', table_name='users')
    op.drop_column('users', 'recovery_token_expires')
    op.drop_column('users', 'recovery_token')
    op.drop_column('users', 'deleted_at')
