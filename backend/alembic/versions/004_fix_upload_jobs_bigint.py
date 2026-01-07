"""Fix upload_jobs table to use BigInteger for file sizes.

Revision ID: 004
Revises: 003
Create Date: 2024-01-15
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Change Integer columns to BigInteger to support files > 2GB
    op.alter_column('upload_jobs', 'total_bytes',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)
    op.alter_column('upload_jobs', 'uploaded_bytes',
                    existing_type=sa.Integer(),
                    type_=sa.BigInteger(),
                    existing_nullable=False)


def downgrade() -> None:
    op.alter_column('upload_jobs', 'total_bytes',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)
    op.alter_column('upload_jobs', 'uploaded_bytes',
                    existing_type=sa.BigInteger(),
                    type_=sa.Integer(),
                    existing_nullable=False)

