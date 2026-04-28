"""Add prompt_category table and category_id to prompt

Revision ID: a1b2c3d4e5f7
Revises: b2c3d4e5f6a7
Create Date: 2026-04-20 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "a1b2c3d4e5f7"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_category",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("user_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("meta", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.BigInteger(), nullable=True),
    )

    op.add_column("prompt", sa.Column("category_id", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("prompt") as batch:
        batch.drop_column("category_id")

    op.drop_table("prompt_category")
