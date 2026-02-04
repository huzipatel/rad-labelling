"""Add password_resets table for forgot password feature

Revision ID: 010
Revises: 009
Create Date: 2024-01-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create password_resets table
    op.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token VARCHAR(255) UNIQUE NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            used_at TIMESTAMPTZ
        );
        
        CREATE INDEX IF NOT EXISTS ix_password_resets_user_id ON password_resets(user_id);
        CREATE INDEX IF NOT EXISTS ix_password_resets_token ON password_resets(token);
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS password_resets")
