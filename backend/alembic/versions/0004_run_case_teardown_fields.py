"""add run_case teardown tracking fields

Revision ID: 0004_run_case_teardown_fields
Revises: 0003_runs_profiles_and_events
Create Date: 2026-06-23 01:30:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0004_run_case_teardown_fields"
down_revision: Union[str, Sequence[str], None] = "0003_runs_profiles_and_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("run_cases", sa.Column("teardown_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("run_cases", sa.Column("next_teardown_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("run_cases", "next_teardown_at")
    op.drop_column("run_cases", "teardown_attempts")
