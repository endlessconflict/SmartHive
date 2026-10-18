"""Refresh tokens for the API. The database holds a hash of each token, never the token."""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE refresh_tokens (
          id          uuid PRIMARY KEY,
          user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
          token_hash  text NOT NULL UNIQUE,
          created_at  timestamptz NOT NULL DEFAULT now(),
          expires_at  timestamptz NOT NULL,
          revoked_at  timestamptz,
          replaced_by uuid
        )
    """)
    op.execute("CREATE INDEX refresh_tokens_user_idx ON refresh_tokens (user_id) WHERE revoked_at IS NULL")


def downgrade() -> None:
    op.execute("DROP TABLE refresh_tokens")
