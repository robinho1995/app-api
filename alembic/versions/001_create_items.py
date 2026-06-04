"""create items table

Revision ID: 001
Revises: None
Create Date: 2026-01-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), sa.Identity(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=True),
        sa.Column("price", sa.Float(), nullable=False, server_default="0"),
        sa.Column("status", sa.Enum("active", "inactive", name="itemstatus"), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_items_id", "items", ["id"])
    op.create_index("ix_items_name", "items", ["name"])


def downgrade() -> None:
    op.drop_index("ix_items_name", table_name="items")
    op.drop_index("ix_items_id", table_name="items")
    op.drop_table("items")