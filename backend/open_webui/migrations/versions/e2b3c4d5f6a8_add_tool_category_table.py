"""Add tool_category table and category_id to tool

Revision ID: e2b3c4d5f6a8
Revises: e1a2b3c4d5f7
Create Date: 2026-06-04 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from open_webui.migrations.util import get_existing_tables

revision: str = "e2b3c4d5f6a8"
down_revision: Union[str, None] = "e1a2b3c4d5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing_tables = set(get_existing_tables())

    if "tool_category" not in existing_tables:
        op.create_table(
            "tool_category",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.BigInteger(), nullable=True),
            sa.Column("updated_at", sa.BigInteger(), nullable=True),
        )

    # Add category_id column to existing tool table if missing.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tool_columns = {col["name"] for col in inspector.get_columns("tool")}
    if "category_id" not in tool_columns:
        op.add_column("tool", sa.Column("category_id", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("tool") as batch:
        batch.drop_column("category_id")

    op.drop_table("tool_category")
