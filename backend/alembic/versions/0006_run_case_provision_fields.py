"""add run_case provisioning tracking fields

Revision ID: 0006_run_case_provision_fields
Revises: 0005_run_api_stats
Create Date: 2026-06-23 02:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_run_case_provision_fields"
down_revision: Union[str, Sequence[str], None] = "0005_run_api_stats"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("run_cases", sa.Column("provision_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("run_cases", sa.Column("next_provision_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("run_cases", "next_provision_at")
    op.drop_column("run_cases", "provision_attempts")
