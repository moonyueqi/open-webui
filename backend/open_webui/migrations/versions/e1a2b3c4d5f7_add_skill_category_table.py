"""Add skill_category table and category_id to skill

Revision ID: e1a2b3c4d5f7
Revises: 56359461a091
Create Date: 2026-06-04 13:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from open_webui.migrations.util import get_existing_tables

revision: str = "e1a2b3c4d5f7"
down_revision: Union[str, None] = "56359461a091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    existing_tables = set(get_existing_tables())

    if "skill_category" not in existing_tables:
        op.create_table(
            "skill_category",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("user_id", sa.Text(), nullable=False),
            sa.Column("name", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("meta", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.BigInteger(), nullable=True),
            sa.Column("updated_at", sa.BigInteger(), nullable=True),
        )

    # Add category_id column to existing skill table if missing.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    skill_columns = {col["name"] for col in inspector.get_columns("skill")}
    if "category_id" not in skill_columns:
        op.add_column("skill", sa.Column("category_id", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("skill") as batch:
        batch.drop_column("category_id")

    op.drop_table("skill_category")
