"""add environment auth sessions

Revision ID: 0002_environment_auth_sessions
Revises: 0001_initial_phase1
Create Date: 2026-06-23 00:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_environment_auth_sessions"
down_revision: Union[str, Sequence[str], None] = "0001_initial_phase1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "environment_auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("environment_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False, server_default="failed"),
        sa.Column("encrypted_session_blob", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("challenge_type", sa.String(length=40), nullable=True),
        sa.Column("challenge_context", sa.Text(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), nullable=True),
        sa.Column("last_success_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_environment_auth_sessions_environment_id", "environment_auth_sessions", ["environment_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_environment_auth_sessions_environment_id", table_name="environment_auth_sessions")
    op.drop_table("environment_auth_sessions")
