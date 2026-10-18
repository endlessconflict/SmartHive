"""Nodes register themselves on first contact; indexes for the queries that come next.

A node that only talks MQTT has no HTTP device token, so `device_token_hash` can no longer be NOT NULL.
The token is issued when an admin registers the node through the API (needed for image upload only).
"""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.execute("ALTER TABLE nodes ALTER COLUMN device_token_hash DROP NOT NULL")
    # alert dedup looks events up by episode; the Varroa index and traffic charts read summaries per hive
    op.execute("CREATE INDEX detection_events_episode_idx ON detection_events (episode_id)")
    op.execute("CREATE INDEX vision_summaries_hive_idx ON vision_summaries (hive_id, window_start DESC)")


def downgrade() -> None:
    op.execute("DROP INDEX vision_summaries_hive_idx")
    op.execute("DROP INDEX detection_events_episode_idx")
    op.execute("UPDATE nodes SET device_token_hash = '' WHERE device_token_hash IS NULL")
    op.execute("ALTER TABLE nodes ALTER COLUMN device_token_hash SET NOT NULL")
