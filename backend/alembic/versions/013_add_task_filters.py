"""Add filters column to tasks table.

Revision ID: 013
Revises: 012
Create Date: 2026-01-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers
revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add filters JSONB column to tasks table
    # Format: [{"field": "BusStopType", "operator": "equals", "value": "MKD"}, ...]
    op.execute("""
        ALTER TABLE tasks 
        ADD COLUMN IF NOT EXISTS filters JSONB DEFAULT '[]'::jsonb;
    """)
    
    # Add index for GIN queries on filters
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_tasks_filters 
        ON tasks USING GIN (filters);
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_tasks_filters;")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS filters;")
