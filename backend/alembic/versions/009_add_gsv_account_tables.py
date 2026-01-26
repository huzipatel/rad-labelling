"""Add GSV account and project tables for persistent API key storage.

Revision ID: 009
Revises: 008
Create Date: 2026-01-26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create gsv_accounts table
    op.create_table(
        'gsv_accounts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), unique=True, nullable=False),
        sa.Column('billing_id', sa.String(100), nullable=True),
        sa.Column('target_projects', sa.Integer(), default=30),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('connected', sa.Boolean(), default=False),
        sa.Column('connected_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create gsv_projects table
    op.create_table(
        'gsv_projects',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('account_id', UUID(as_uuid=True), sa.ForeignKey('gsv_accounts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_id', sa.String(100), nullable=False),
        sa.Column('project_name', sa.String(255), nullable=True),
        sa.Column('api_key', sa.Text(), nullable=True),
        sa.Column('auto_created', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(), default=sa.func.now()),
    )
    
    # Create index on account_id for faster lookups
    op.create_index('ix_gsv_projects_account_id', 'gsv_projects', ['account_id'])


def downgrade() -> None:
    op.drop_index('ix_gsv_projects_account_id', table_name='gsv_projects')
    op.drop_table('gsv_projects')
    op.drop_table('gsv_accounts')

