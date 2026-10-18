"""Node power alert, and the escalation time for node_offline."""

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade() -> None:
    op.execute(
        "INSERT INTO alert_rules (id, severity, params) VALUES "
        "('node_power_low', 'warning', '{\"battery_v_min\": 10.2, \"minutes\": 10, \"uv_snapshots\": 3}') "
        "ON CONFLICT (id) DO NOTHING"
    )
    op.execute(
        "UPDATE alert_rules SET params = params || '{\"escalate_after_hours\": 24}' WHERE id = 'node_offline'"
    )


def downgrade() -> None:
    op.execute("DELETE FROM alert_rules WHERE id = 'node_power_low'")
    op.execute("UPDATE alert_rules SET params = params - 'escalate_after_hours' WHERE id = 'node_offline'")
