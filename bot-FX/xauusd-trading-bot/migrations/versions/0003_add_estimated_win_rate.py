"""Add estimated win rate to trades.

Revision ID: 0003_add_estimated_win_rate
Revises: 0002_data_reset_markers
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_add_estimated_win_rate"
down_revision = "0002_data_reset_markers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trades", sa.Column("estimated_win_rate", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("trades", "estimated_win_rate")
