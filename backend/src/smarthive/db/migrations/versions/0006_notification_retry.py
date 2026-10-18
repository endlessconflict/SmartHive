"""When a failed notification may be tried again."""

from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade() -> None:
    op.execute("ALTER TABLE notifications ADD COLUMN next_attempt_at timestamptz")
    op.execute("CREATE INDEX notifications_pending ON notifications (id) WHERE status = 'pending'")


def downgrade() -> None:
    op.execute("DROP INDEX notifications_pending")
    op.execute("ALTER TABLE notifications DROP COLUMN next_attempt_at")
