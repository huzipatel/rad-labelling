"""Add download_logs table for tracking GSV image downloads.

Revision ID: 006
Revises: 005
Create Date: 2024-12-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'download_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('task_id', UUID(as_uuid=True), sa.ForeignKey('tasks.id'), nullable=False, index=True),
        sa.Column('status', sa.String(50), default='pending'),
        sa.Column('total_locations', sa.Integer(), default=0),
        sa.Column('processed_locations', sa.Integer(), default=0),
        sa.Column('successful_downloads', sa.Integer(), default=0),
        sa.Column('failed_downloads', sa.Integer(), default=0),
        sa.Column('skipped_existing', sa.Integer(), default=0),
        sa.Column('current_location_id', UUID(as_uuid=True), nullable=True),
        sa.Column('current_location_identifier', sa.String(255), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('error_count', sa.Integer(), default=0),
        sa.Column('log_messages', sa.Text(), default='[]'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('download_logs')

