"""Initial database schema

Revision ID: 001
Revises: 
Create Date: 2026-02-18

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    # Create clubs table
    op.create_table(
        'clubs',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(), nullable=True),
        sa.Column('quota_matches', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_clubs_id', 'clubs', ['id'])
    op.create_index('ix_clubs_stripe_customer_id', 'clubs', ['stripe_customer_id'], unique=True)
    
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('hashed_password', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('plan', sa.Enum('coach', 'club', name='plantype'), nullable=False),
        sa.Column('stripe_customer_id', sa.String(), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(), nullable=True),
        sa.Column('club_id', sa.String(), nullable=True),
        sa.Column('role', sa.Enum('admin', 'coach', 'analyst', name='userrole'), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_users_id', 'users', ['id'])
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_stripe_customer_id', 'users', ['stripe_customer_id'], unique=True)
    
    # Create matches table
    op.create_table(
        'matches',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('club_id', sa.String(), nullable=True),
        sa.Column('opponent', sa.String(), nullable=False),
        sa.Column('date', sa.DateTime(), nullable=False),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('type', sa.Enum('championnat', 'coupe', 'amical', name='matchtype'), nullable=False),
        sa.Column('video_url', sa.String(), nullable=False),
        sa.Column('pdf_url', sa.String(), nullable=True),
        sa.Column('status', sa.Enum('pending', 'processing', 'completed', 'error', name='matchstatus'), nullable=False),
        sa.Column('progress', sa.Integer(), nullable=False),
        sa.Column('error_message', sa.String(), nullable=True),
        sa.Column('stats', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['club_id'], ['clubs.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_matches_id', 'matches', ['id'])

def downgrade():
    op.drop_table('matches')
    op.drop_table('users')
    op.drop_table('clubs')
    
    # Drop enums
    op.execute('DROP TYPE matchstatus')
    op.execute('DROP TYPE matchtype')
    op.execute('DROP TYPE userrole')
    op.execute('DROP TYPE plantype')
