"""add trial fields to users

Revision ID: add_trial_fields
Revises: add_soft_delete_users
Create Date: 2026-02-27

"""
from alembic import op
import sqlalchemy as sa

revision = 'add_trial_fields'
down_revision = 'add_soft_delete_users'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('users', sa.Column('trial_match_used', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('trial_ends_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('profile_role', sa.String(), nullable=True))
    op.add_column('users', sa.Column('profile_level', sa.String(), nullable=True))
    op.add_column('users', sa.Column('profile_phone', sa.String(), nullable=True))
    op.add_column('users', sa.Column('profile_city', sa.String(), nullable=True))
    op.add_column('users', sa.Column('profile_diploma', sa.String(), nullable=True))
    op.add_column('users', sa.Column('is_superadmin', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('users', sa.Column('last_login', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('users', 'trial_match_used')
    op.drop_column('users', 'trial_ends_at')
    op.drop_column('users', 'profile_role')
    op.drop_column('users', 'profile_level')
    op.drop_column('users', 'profile_phone')
    op.drop_column('users', 'profile_city')
    op.drop_column('users', 'profile_diploma')
    op.drop_column('users', 'is_superadmin')
    op.drop_column('users', 'last_login')
