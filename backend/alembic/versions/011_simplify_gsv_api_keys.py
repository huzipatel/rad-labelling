"""Simplify GSV API key management - single table with usage tracking.

Replaces gsv_accounts + gsv_projects with a single gsv_api_keys table.
Migrates existing keys from gsv_projects to the new table.

Revision ID: 011
Revises: 010
Create Date: 2026-01-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create new simplified gsv_api_keys table
    op.create_table(
        'gsv_api_keys',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('api_key', sa.String(100), unique=True, nullable=False),
        sa.Column('label', sa.String(255), nullable=True),  # Optional friendly name
        sa.Column('is_active', sa.Boolean(), default=True, nullable=False),
        
        # Usage tracking
        sa.Column('requests_today', sa.Integer(), default=0, nullable=False),
        sa.Column('requests_total', sa.BigInteger(), default=0, nullable=False),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_reset_date', sa.Date(), nullable=True),
        
        # Error tracking
        sa.Column('consecutive_errors', sa.Integer(), default=0, nullable=False),
        sa.Column('last_error_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_message', sa.String(500), nullable=True),
        sa.Column('quota_exhausted', sa.Boolean(), default=False, nullable=False),
        
        # Metadata
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Create index for active key lookups
    op.create_index('ix_gsv_api_keys_active', 'gsv_api_keys', ['is_active', 'quota_exhausted'])
    
    # Migrate existing keys from gsv_projects to new table
    # This is done via raw SQL to handle the data migration
    op.execute("""
        INSERT INTO gsv_api_keys (id, api_key, label, is_active, requests_today, requests_total, created_at, updated_at)
        SELECT 
            gen_random_uuid(),
            gp.api_key,
            CONCAT('Migrated from ', ga.email),
            true,
            0,
            0,
            gp.created_at,
            NOW()
        FROM gsv_projects gp
        JOIN gsv_accounts ga ON gp.account_id = ga.id
        WHERE gp.api_key IS NOT NULL AND gp.api_key != ''
        ON CONFLICT (api_key) DO NOTHING
    """)
    
    # Drop old tables
    op.drop_index('ix_gsv_projects_account_id', table_name='gsv_projects')
    op.drop_table('gsv_projects')
    op.drop_table('gsv_accounts')


def downgrade() -> None:
    # Recreate old tables
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
    
    op.create_index('ix_gsv_projects_account_id', 'gsv_projects', ['account_id'])
    
    # Drop new table
    op.drop_index('ix_gsv_api_keys_active', table_name='gsv_api_keys')
    op.drop_table('gsv_api_keys')
