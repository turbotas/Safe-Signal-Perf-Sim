"""add run api stats fields

Revision ID: 0005_run_api_stats
Revises: 0004_run_case_teardown_fields
Create Date: 2026-06-23 02:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_run_api_stats"
down_revision: Union[str, Sequence[str], None] = "0004_run_case_teardown_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("runs", sa.Column("api_calls_total", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("runs", sa.Column("api_calls_failed", sa.Integer(), nullable=False, server_default=sa.text("0")))
    op.add_column("runs", sa.Column("api_avg_response_ms", sa.Float(), nullable=False, server_default=sa.text("0")))
    op.add_column("runs", sa.Column("api_last_response_ms", sa.Float(), nullable=False, server_default=sa.text("0")))


def downgrade() -> None:
    op.drop_column("runs", "api_last_response_ms")
    op.drop_column("runs", "api_avg_response_ms")
    op.drop_column("runs", "api_calls_failed")
    op.drop_column("runs", "api_calls_total")
