"""add run_case case reference field

Revision ID: 0007_run_case_reference
Revises: 0006_run_case_provision_fields
Create Date: 2026-06-23 03:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_run_case_reference"
down_revision: Union[str, Sequence[str], None] = "0006_run_case_provision_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("run_cases", sa.Column("case_reference", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("run_cases", "case_reference")
