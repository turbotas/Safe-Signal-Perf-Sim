"""add run profile and run lifecycle tables

Revision ID: 0003_runs_profiles_and_events
Revises: 0002_environment_auth_sessions
Create Date: 2026-06-23 01:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0003_runs_profiles_and_events"
down_revision: Union[str, Sequence[str], None] = "0002_environment_auth_sessions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "run_profiles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("device_count_initial", sa.Integer(), nullable=False, server_default=sa.text("200")),
        sa.Column("update_min_ms", sa.Integer(), nullable=False, server_default=sa.text("1800000")),
        sa.Column("update_max_ms", sa.Integer(), nullable=False, server_default=sa.text("3600000")),
        sa.Column("activation_chance", sa.Float(), nullable=False, server_default=sa.text("0.03")),
        sa.Column("active_interval_ms", sa.Integer(), nullable=False, server_default=sa.text("30000")),
        sa.Column("active_duration_ms", sa.Integer(), nullable=False, server_default=sa.text("900000")),
        sa.Column("case_creation_delay_ms", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("teardown_mode", sa.String(length=20), nullable=False, server_default="delete"),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("profile_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="starting"),
        sa.Column("blocked_reason", sa.String(length=80), nullable=True),
        sa.Column("desired_case_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("active_case_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("stopped_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["profile_id"], ["run_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_environment_id", "runs", ["environment_id"], unique=False)
    op.create_index("ix_runs_profile_id", "runs", ["profile_id"], unique=False)

    op.create_table(
        "run_cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("safe_signal_case_id", sa.String(length=120), nullable=True),
        sa.Column("device_id", sa.String(length=64), nullable=True),
        sa.Column("device_api_key", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=40), nullable=False, server_default="provisioning"),
        sa.Column("next_update_at", sa.DateTime(), nullable=True),
        sa.Column("last_update_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("schedule_overrides", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_cases_environment_id", "run_cases", ["environment_id"], unique=False)
    op.create_index("ix_run_cases_run_id", "run_cases", ["run_id"], unique=False)

    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("run_case_id", sa.Integer(), nullable=True),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=20), nullable=False, server_default="info"),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_case_id"], ["run_cases.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_run_events_environment_id", "run_events", ["environment_id"], unique=False)
    op.create_index("ix_run_events_run_case_id", "run_events", ["run_case_id"], unique=False)
    op.create_index("ix_run_events_run_id", "run_events", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_run_events_run_id", table_name="run_events")
    op.drop_index("ix_run_events_run_case_id", table_name="run_events")
    op.drop_index("ix_run_events_environment_id", table_name="run_events")
    op.drop_table("run_events")

    op.drop_index("ix_run_cases_run_id", table_name="run_cases")
    op.drop_index("ix_run_cases_environment_id", table_name="run_cases")
    op.drop_table("run_cases")

    op.drop_index("ix_runs_profile_id", table_name="runs")
    op.drop_index("ix_runs_environment_id", table_name="runs")
    op.drop_table("runs")

    op.drop_table("run_profiles")
