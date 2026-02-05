"""Add label_comments table

Revision ID: 002
Revises: 001_initial_schema
Create Date: 2026-01-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create label_comments table
    op.create_table(
        'label_comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('label_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('comment_type', sa.String(50), nullable=False, server_default='feedback'),
        sa.Column('tagged_user_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('parent_comment_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('is_read', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_resolved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('resolved_by_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['label_id'], ['labels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tagged_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['parent_comment_id'], ['label_comments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['resolved_by_id'], ['users.id'], ondelete='SET NULL'),
    )
    
    # Create indexes for efficient querying
    op.create_index('ix_label_comments_label_id', 'label_comments', ['label_id'])
    op.create_index('ix_label_comments_author_id', 'label_comments', ['author_id'])
    op.create_index('ix_label_comments_is_read', 'label_comments', ['is_read'])
    op.create_index('ix_label_comments_created_at', 'label_comments', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_label_comments_created_at')
    op.drop_index('ix_label_comments_is_read')
    op.drop_index('ix_label_comments_author_id')
    op.drop_index('ix_label_comments_label_id')
    op.drop_table('label_comments')
