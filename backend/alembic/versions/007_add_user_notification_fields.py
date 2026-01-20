"""Add user notification and phone fields

Revision ID: 007
Revises: 006
Create Date: 2024-01-19

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add phone_number column if not exists
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='phone_number') THEN
                ALTER TABLE users ADD COLUMN phone_number VARCHAR(20);
            END IF;
        END $$;
    """)
    
    # Add whatsapp_number column if not exists
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='whatsapp_number') THEN
                ALTER TABLE users ADD COLUMN whatsapp_number VARCHAR(20);
            END IF;
        END $$;
    """)
    
    # Add notify_daily_reminder column if not exists
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='notify_daily_reminder') THEN
                ALTER TABLE users ADD COLUMN notify_daily_reminder BOOLEAN NOT NULL DEFAULT TRUE;
            END IF;
        END $$;
    """)
    
    # Add notify_task_assigned column if not exists
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='users' AND column_name='notify_task_assigned') THEN
                ALTER TABLE users ADD COLUMN notify_task_assigned BOOLEAN NOT NULL DEFAULT TRUE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.drop_column('users', 'notify_task_assigned')
    op.drop_column('users', 'notify_daily_reminder')
    op.drop_column('users', 'whatsapp_number')
    op.drop_column('users', 'phone_number')


