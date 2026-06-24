"""add run action stats table

Revision ID: 0009_run_action_stats
Revises: 0008_case_worker_runs
Create Date: 2026-06-24 12:25:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0009_run_action_stats"
down_revision: Union[str, Sequence[str], None] = "0008_case_worker_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "run_action_stats" not in tables:
        op.create_table(
            "run_action_stats",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=False),
            sa.Column("environment_id", sa.Integer(), nullable=False),
            sa.Column("action_type", sa.String(length=80), nullable=False),
            sa.Column("success_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("avg_response_ms", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("last_response_ms", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["run_id"], ["runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("run_id", "action_type", name="uq_run_action_stats_run_action_type"),
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("run_action_stats")}
    if "ix_run_action_stats_run_id" not in indexes:
        op.create_index("ix_run_action_stats_run_id", "run_action_stats", ["run_id"], unique=False)
    if "ix_run_action_stats_environment_id" not in indexes:
        op.create_index("ix_run_action_stats_environment_id", "run_action_stats", ["environment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_run_action_stats_environment_id", table_name="run_action_stats")
    op.drop_index("ix_run_action_stats_run_id", table_name="run_action_stats")
    op.drop_table("run_action_stats")
