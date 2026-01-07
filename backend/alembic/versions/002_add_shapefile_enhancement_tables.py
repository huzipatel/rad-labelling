"""Add shapefile and enhancement job tables

Revision ID: 002
Revises: 001
Create Date: 2024-01-01

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create shapefiles table
    op.create_table(
        'shapefiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('shapefile_type', sa.String(50), nullable=False),
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('feature_count', sa.Integer(), server_default='0'),
        sa.Column('geometry_type', sa.String(50), nullable=True),
        sa.Column('attribute_columns', postgresql.JSONB(), server_default='{}'),
        sa.Column('name_column', sa.String(100), nullable=True),
        sa.Column('is_loaded', sa.Boolean(), server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('loaded_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id', name='pk_shapefiles')
    )
    
    # Create enhancement_jobs table
    op.create_table(
        'enhancement_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('location_type_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('total_locations', sa.Integer(), server_default='0'),
        sa.Column('processed_locations', sa.Integer(), server_default='0'),
        sa.Column('enhanced_locations', sa.Integer(), server_default='0'),
        sa.Column('enhance_council', sa.Boolean(), server_default='true'),
        sa.Column('enhance_road', sa.Boolean(), server_default='true'),
        sa.Column('enhance_authority', sa.Boolean(), server_default='true'),
        sa.Column('councils_found', postgresql.JSONB(), server_default='[]'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['location_type_id'], ['location_types.id'], ondelete='CASCADE', name='fk_enhancement_jobs_location_type'),
        sa.PrimaryKeyConstraint('id', name='pk_enhancement_jobs')
    )
    
    # Create index for enhancement jobs
    op.create_index('ix_enhancement_jobs_location_type_status', 'enhancement_jobs', ['location_type_id', 'status'])


def downgrade() -> None:
    op.drop_index('ix_enhancement_jobs_location_type_status', 'enhancement_jobs')
    op.drop_table('enhancement_jobs')
    op.drop_table('shapefiles')

