"""Add number_of_faces and screen_type fields to labels table.

Revision ID: 012
Revises: 011
Create Date: 2026-01-27
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add number_of_faces column with default value of 2
    op.execute("""
        ALTER TABLE labels 
        ADD COLUMN IF NOT EXISTS number_of_faces INTEGER DEFAULT 2;
    """)
    
    # Add screen_type column (Paper or Expected Digital)
    op.execute("""
        ALTER TABLE labels 
        ADD COLUMN IF NOT EXISTS screen_type VARCHAR(50);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE labels DROP COLUMN IF EXISTS number_of_faces;
    """)
    op.execute("""
        ALTER TABLE labels DROP COLUMN IF EXISTS screen_type;
    """)
