"""Add upload_jobs table for large file uploads.

Revision ID: 003
Revises: 002
Create Date: 2024-01-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'upload_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('filename', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('status', sa.String(50), nullable=False, server_default='pending'),
        sa.Column('stage', sa.String(100), nullable=False, server_default='Initializing'),
        sa.Column('total_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('uploaded_bytes', sa.BigInteger(), nullable=False, server_default='0'),
        sa.Column('progress_percent', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('shapefile_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('job_metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create index on status for quick lookups
    op.create_index('ix_upload_jobs_status', 'upload_jobs', ['status'])


def downgrade() -> None:
    op.drop_index('ix_upload_jobs_status', table_name='upload_jobs')
    op.drop_table('upload_jobs')

