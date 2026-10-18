"""Add data reset markers.

Revision ID: 0002_data_reset_markers
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_data_reset_markers"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "data_reset_markers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("reset_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("starting_equity", sa.Float(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_data_reset_markers_reset_at"), "data_reset_markers", ["reset_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_data_reset_markers_reset_at"), table_name="data_reset_markers")
    op.drop_table("data_reset_markers")
