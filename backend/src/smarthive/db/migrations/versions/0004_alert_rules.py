"""The predefined alert rules and their default thresholds (docs/05-backend/07-alerts-and-rules.md)."""

from alembic import op

revision = "0004"
down_revision = "0003"

RULES = [
    ("hornet_detected", "critical", "{}"),
    ("shb_detected", "warning", "{}"),
    ("varroa_high", "warning", '{"threshold_pct": 3, "min_bees": 300, "hours": 24}'),
    ("node_offline", "warning", '{"silent_minutes": 10}'),
    ("temp_out_of_range", "warning", '{"quantity": "temp_in", "low": 32, "high": 37, "hours": 2}'),
    ("rh_out_of_range", "info", '{"quantity": "rh_in", "low": 40, "high": 85, "hours": 6}'),
]


def upgrade() -> None:
    for rule_id, severity, params in RULES:
        op.execute(
            f"INSERT INTO alert_rules (id, severity, params) VALUES ('{rule_id}', '{severity}', '{params}') "
            "ON CONFLICT (id) DO NOTHING"
        )


def downgrade() -> None:
    ids = ", ".join(f"'{r[0]}'" for r in RULES)
    op.execute(f"DELETE FROM alert_rules WHERE id IN ({ids})")
