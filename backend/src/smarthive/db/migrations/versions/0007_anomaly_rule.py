"""Anomaly warnings (US17): a level on each anomaly window, and the rule that finds and shows them.

An anomaly is a warning to review, never critical and never notified. The level says how unusual it is.
"""

import json

from alembic import op

revision = "0007"
down_revision = "0006"

# smarthive.alerts.anomaly.DEFAULTS as of this migration; changing the defaults needs its own migration
PARAMS = {
    "baseline_days": 7,
    "recent_hours": 24,
    "min_baseline_hours": 48,
    "min_run_hours": 2,
    "info_z": 3.5,
    "warning_z": 6.0,
    "min_scale_temp_in": 0.3,
    "min_scale_rh_in": 1.5,
    "min_scale_weight": 0.1,
}


def upgrade() -> None:
    op.execute(
        "ALTER TABLE anomalies ADD COLUMN level text NOT NULL DEFAULT 'warning' "
        "CHECK (level IN ('info', 'warning'))"
    )
    # the stored severity is the highest an anomaly reaches; each one is info or warning by its own score
    op.execute(
        "INSERT INTO alert_rules (id, severity, params) VALUES "
        f"('anomaly_detected', 'warning', '{json.dumps(PARAMS)}') ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DELETE FROM alert_rules WHERE id = 'anomaly_detected'")
    op.execute("ALTER TABLE anomalies DROP COLUMN level")
