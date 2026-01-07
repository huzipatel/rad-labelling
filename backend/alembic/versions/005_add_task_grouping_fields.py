"""Add task grouping fields.

Revision ID: 005
Revises: 004
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new flexible grouping fields to tasks table
    op.add_column('tasks', sa.Column('group_field', sa.String(100), nullable=True, server_default='council'))
    op.add_column('tasks', sa.Column('group_value', sa.Text(), nullable=True))
    op.add_column('tasks', sa.Column('name', sa.String(500), nullable=True))
    
    # Create index for grouping queries
    op.create_index('ix_tasks_group', 'tasks', ['location_type_id', 'group_field', 'group_value'])
    
    # Update existing tasks to have group_field and group_value populated from council
    op.execute("""
        UPDATE tasks 
        SET group_field = 'council', 
            group_value = council,
            name = council
        WHERE group_field IS NULL
    """)


def downgrade() -> None:
    op.drop_index('ix_tasks_group', table_name='tasks')
    op.drop_column('tasks', 'name')
    op.drop_column('tasks', 'group_value')
    op.drop_column('tasks', 'group_field')

