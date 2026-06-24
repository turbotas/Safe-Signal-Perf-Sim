"""add case-worker profile and run fields

Revision ID: 0008_case_worker_runs
Revises: 0007_run_case_reference
Create Date: 2026-06-24 11:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0008_case_worker_runs"
down_revision: Union[str, Sequence[str], None] = "0007_run_case_reference"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    run_profile_cols = {col["name"] for col in inspector.get_columns("run_profiles")}
    runs_cols = {col["name"] for col in inspector.get_columns("runs")}
    runs_indexes = {idx["name"] for idx in inspector.get_indexes("runs")}

    if "profile_kind" not in run_profile_cols:
        op.add_column(
            "run_profiles",
            sa.Column("profile_kind", sa.String(length=30), nullable=False, server_default="device_telemetry"),
        )
    if "caseworker_worker_count_initial" not in run_profile_cols:
        op.add_column(
            "run_profiles",
            sa.Column("caseworker_worker_count_initial", sa.Integer(), nullable=False, server_default=sa.text("20")),
        )
    if "caseworker_actions_per_min_per_worker" not in run_profile_cols:
        op.add_column(
            "run_profiles",
            sa.Column(
                "caseworker_actions_per_min_per_worker",
                sa.Float(),
                nullable=False,
                server_default=sa.text("6.0"),
            ),
        )
    if "caseworker_think_time_min_ms" not in run_profile_cols:
        op.add_column(
            "run_profiles",
            sa.Column("caseworker_think_time_min_ms", sa.Integer(), nullable=False, server_default=sa.text("1500")),
        )
    if "caseworker_think_time_max_ms" not in run_profile_cols:
        op.add_column(
            "run_profiles",
            sa.Column("caseworker_think_time_max_ms", sa.Integer(), nullable=False, server_default=sa.text("6000")),
        )
    if "caseworker_read_ratio" not in run_profile_cols:
        op.add_column(
            "run_profiles",
            sa.Column("caseworker_read_ratio", sa.Float(), nullable=False, server_default=sa.text("0.75")),
        )

    if "parent_run_id" not in runs_cols:
        op.add_column("runs", sa.Column("parent_run_id", sa.Integer(), nullable=True))
    if "run_kind" not in runs_cols:
        op.add_column("runs", sa.Column("run_kind", sa.String(length=30), nullable=False, server_default="device_telemetry"))
    if "actions_total" not in runs_cols:
        op.add_column("runs", sa.Column("actions_total", sa.Integer(), nullable=False, server_default=sa.text("0")))
    if "actions_failed_total" not in runs_cols:
        op.add_column("runs", sa.Column("actions_failed_total", sa.Integer(), nullable=False, server_default=sa.text("0")))
    if "actions_per_second_current" not in runs_cols:
        op.add_column(
            "runs",
            sa.Column("actions_per_second_current", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        )
    if "actions_per_second_avg" not in runs_cols:
        op.add_column(
            "runs",
            sa.Column("actions_per_second_avg", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        )

    if "ix_runs_parent_run_id" not in runs_indexes:
        op.create_index("ix_runs_parent_run_id", "runs", ["parent_run_id"], unique=False)

    # SQLite cannot reliably add a new FK constraint with ALTER TABLE.
    # Skip FK creation on SQLite and rely on application-level interlock checks.
    if bind.dialect.name != "sqlite":
        fk_names = {fk.get("name") for fk in inspector.get_foreign_keys("runs") if fk.get("name")}
        if "fk_runs_parent_run_id" not in fk_names:
            op.create_foreign_key("fk_runs_parent_run_id", "runs", "runs", ["parent_run_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_runs_parent_run_id", "runs", type_="foreignkey")
    op.drop_index("ix_runs_parent_run_id", table_name="runs")
    op.drop_column("runs", "actions_per_second_avg")
    op.drop_column("runs", "actions_per_second_current")
    op.drop_column("runs", "actions_failed_total")
    op.drop_column("runs", "actions_total")
    op.drop_column("runs", "run_kind")
    op.drop_column("runs", "parent_run_id")

    op.drop_column("run_profiles", "caseworker_read_ratio")
    op.drop_column("run_profiles", "caseworker_think_time_max_ms")
    op.drop_column("run_profiles", "caseworker_think_time_min_ms")
    op.drop_column("run_profiles", "caseworker_actions_per_min_per_worker")
    op.drop_column("run_profiles", "caseworker_worker_count_initial")
    op.drop_column("run_profiles", "profile_kind")
