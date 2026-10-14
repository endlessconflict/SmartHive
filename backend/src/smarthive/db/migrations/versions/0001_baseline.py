"""Baseline schema from docs/05-backend/05-data-model.md"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None

TABLES = """alert_events notifications alerts alert_rules commands predictions anomalies management_events
vision_summaries detection_events images weather node_health readings node_assignments nodes hives apiaries users"""


def upgrade():
    op.execute(Path(__file__).with_suffix(".sql").read_text())


def downgrade():
    for t in TABLES.split():
        op.execute(f"DROP TABLE IF EXISTS {t} CASCADE")
