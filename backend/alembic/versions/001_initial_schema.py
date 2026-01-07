"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import geoalchemy2

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enable PostGIS extension
    op.execute('CREATE EXTENSION IF NOT EXISTS postgis')
    
    # Users table
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('hashed_password', sa.String(255), nullable=True),
        sa.Column('role', sa.String(50), nullable=False, default='labeller'),
        sa.Column('google_id', sa.String(255), nullable=True, unique=True),
        sa.Column('hourly_rate', sa.Numeric(10, 2), nullable=True),
        sa.Column('whatsapp_number', sa.String(20), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_users_email', 'users', ['email'])
    
    # Location types table
    op.create_table(
        'location_types',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('label_fields', postgresql.JSONB, nullable=False, default={}),
        sa.Column('identifier_field', sa.String(100), nullable=False, default='atco_code'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    
    # Locations table
    op.create_table(
        'locations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('location_type_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('location_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('identifier', sa.String(100), nullable=False),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('coordinates', geoalchemy2.Geography(geometry_type='POINT', srid=4326), nullable=True),
        sa.Column('council', sa.String(255), nullable=True),
        sa.Column('combined_authority', sa.String(255), nullable=True),
        sa.Column('road_classification', sa.String(10), nullable=True),
        sa.Column('original_data', postgresql.JSONB, nullable=False, default={}),
        sa.Column('is_enhanced', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index('ix_locations_identifier', 'locations', ['identifier'])
    op.create_index('ix_locations_council', 'locations', ['council'])
    op.create_index('ix_locations_type_council', 'locations', ['location_type_id', 'council'])
    
    # Tasks table
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('location_type_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('location_types.id', ondelete='CASCADE'), nullable=False),
        sa.Column('council', sa.String(255), nullable=False),
        sa.Column('assigned_to', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.String(50), nullable=False, default='pending'),
        sa.Column('total_locations', sa.Integer(), default=0),
        sa.Column('completed_locations', sa.Integer(), default=0),
        sa.Column('failed_locations', sa.Integer(), default=0),
        sa.Column('images_downloaded', sa.Integer(), default=0),
        sa.Column('total_images', sa.Integer(), default=0),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('assigned_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index('ix_tasks_council', 'tasks', ['council'])
    op.create_index('ix_tasks_status', 'tasks', ['status'])
    op.create_index('ix_tasks_type_council', 'tasks', ['location_type_id', 'council'])
    op.create_index('ix_tasks_assignee_status', 'tasks', ['assigned_to', 'status'])
    
    # Labels table
    op.create_table(
        'labels',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('location_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('locations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tasks.id', ondelete='CASCADE'), nullable=False),
        sa.Column('labeller_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('advertising_present', sa.Boolean(), nullable=True),
        sa.Column('bus_shelter_present', sa.Boolean(), nullable=True),
        sa.Column('number_of_panels', sa.Integer(), nullable=True),
        sa.Column('pole_stop', sa.Boolean(), nullable=True),
        sa.Column('unmarked_stop', sa.Boolean(), nullable=True),
        sa.Column('selected_image', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB, nullable=False, default={}),
        sa.Column('status', sa.String(50), nullable=False, default='pending'),
        sa.Column('unable_to_label', sa.Boolean(), default=False),
        sa.Column('unable_reason', sa.String(500), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.Column('labelling_started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('labelling_completed_at', sa.DateTime(timezone=True), nullable=True),
    )
    
    # GSV Images table
    op.create_table(
        'gsv_images',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('location_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('locations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('heading', sa.Integer(), nullable=False),
        sa.Column('pitch', sa.Float(), default=0),
        sa.Column('zoom', sa.Float(), default=1),
        sa.Column('gcs_path', sa.String(500), nullable=False),
        sa.Column('gcs_url', sa.String(1000), nullable=True),
        sa.Column('capture_date', sa.Date(), nullable=True),
        sa.Column('pano_id', sa.String(100), nullable=True),
        sa.Column('is_user_snapshot', sa.Boolean(), default=False),
        sa.Column('snapshot_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    
    # Council boundaries (spatial)
    op.create_table(
        'council_boundaries',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('council_name', sa.String(255), nullable=False),
        sa.Column('council_code', sa.String(50), nullable=True),
        sa.Column('boundary', geoalchemy2.Geography(geometry_type='MULTIPOLYGON', srid=4326), nullable=False),
    )
    op.create_index('ix_council_boundaries_name', 'council_boundaries', ['council_name'])
    
    # Combined authorities (spatial)
    op.create_table(
        'combined_authorities',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('authority_name', sa.String(255), nullable=False),
        sa.Column('authority_code', sa.String(50), nullable=True),
        sa.Column('boundary', geoalchemy2.Geography(geometry_type='MULTIPOLYGON', srid=4326), nullable=False),
    )
    op.create_index('ix_combined_authorities_name', 'combined_authorities', ['authority_name'])
    
    # Road classifications (spatial)
    op.create_table(
        'road_classifications',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('road_name', sa.String(255), nullable=True),
        sa.Column('road_class', sa.String(10), nullable=False),
        sa.Column('road_number', sa.String(20), nullable=True),
        sa.Column('geometry', geoalchemy2.Geography(geometry_type='MULTILINESTRING', srid=4326), nullable=False),
    )
    op.create_index('ix_road_classifications_class', 'road_classifications', ['road_class'])
    
    # Create spatial indexes
    op.execute('CREATE INDEX ix_council_boundaries_boundary ON council_boundaries USING GIST (boundary)')
    op.execute('CREATE INDEX ix_combined_authorities_boundary ON combined_authorities USING GIST (boundary)')
    op.execute('CREATE INDEX ix_road_classifications_geometry ON road_classifications USING GIST (geometry)')
    op.execute('CREATE INDEX ix_locations_coordinates ON locations USING GIST (coordinates)')


def downgrade() -> None:
    op.drop_table('road_classifications')
    op.drop_table('combined_authorities')
    op.drop_table('council_boundaries')
    op.drop_table('gsv_images')
    op.drop_table('labels')
    op.drop_table('tasks')
    op.drop_table('locations')
    op.drop_table('location_types')
    op.drop_table('users')

