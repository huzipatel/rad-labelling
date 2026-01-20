"""Add invitation and notification tables

Revision ID: 008
Revises: 007
Create Date: 2024-01-19

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create invitations table if not exists
    op.execute("""
        CREATE TABLE IF NOT EXISTS invitations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(255) NOT NULL,
            name VARCHAR(255),
            role VARCHAR(50) NOT NULL DEFAULT 'labeller',
            token VARCHAR(255) UNIQUE NOT NULL,
            invited_by_id UUID NOT NULL,
            message TEXT,
            status VARCHAR(20) NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            accepted_at TIMESTAMPTZ
        );
        
        CREATE INDEX IF NOT EXISTS ix_invitations_email ON invitations(email);
        CREATE INDEX IF NOT EXISTS ix_invitations_token ON invitations(token);
    """)
    
    # Create notification_settings table if not exists
    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_settings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            daily_summary_enabled BOOLEAN DEFAULT FALSE,
            daily_summary_time VARCHAR(5) DEFAULT '18:00',
            daily_summary_admin_id UUID REFERENCES users(id),
            task_completion_enabled BOOLEAN DEFAULT TRUE,
            daily_reminders_enabled BOOLEAN DEFAULT FALSE,
            daily_reminder_time VARCHAR(5) DEFAULT '09:00',
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    
    # Create user_notification_preferences table if not exists
    op.execute("""
        CREATE TABLE IF NOT EXISTS user_notification_preferences (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID UNIQUE REFERENCES users(id),
            opt_out_daily_reminders BOOLEAN DEFAULT FALSE,
            opt_out_task_assignments BOOLEAN DEFAULT FALSE,
            opt_out_all_whatsapp BOOLEAN DEFAULT FALSE,
            opt_out_date TIMESTAMPTZ,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ DEFAULT NOW()
        );
    """)
    
    # Create notification_logs table if not exists
    op.execute("""
        CREATE TABLE IF NOT EXISTS notification_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            notification_type VARCHAR(50) NOT NULL,
            recipient_id UUID REFERENCES users(id),
            recipient_number VARCHAR(20) NOT NULL,
            message_preview TEXT NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            error_message TEXT,
            task_id UUID REFERENCES tasks(id),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            sent_at TIMESTAMPTZ
        );
    """)
    
    # Add sample task fields to tasks table if not exists
    op.execute("""
        DO $$ 
        BEGIN 
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='is_sample') THEN
                ALTER TABLE tasks ADD COLUMN is_sample BOOLEAN NOT NULL DEFAULT FALSE;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='source_task_id') THEN
                ALTER TABLE tasks ADD COLUMN source_task_id UUID REFERENCES tasks(id) ON DELETE SET NULL;
            END IF;
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='tasks' AND column_name='sample_location_ids') THEN
                ALTER TABLE tasks ADD COLUMN sample_location_ids JSONB;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS notification_logs")
    op.execute("DROP TABLE IF EXISTS user_notification_preferences")
    op.execute("DROP TABLE IF EXISTS notification_settings")
    op.execute("DROP TABLE IF EXISTS invitations")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS is_sample")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS source_task_id")
    op.execute("ALTER TABLE tasks DROP COLUMN IF EXISTS sample_location_ids")


