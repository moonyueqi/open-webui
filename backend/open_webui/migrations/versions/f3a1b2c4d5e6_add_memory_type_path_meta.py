"""Add type/path/meta columns and indexes to memory table

Revision ID: f3a1b2c4d5e6
Revises: e2b3c4d5f6a8
Create Date: 2026-07-22 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a1b2c4d5e6"
down_revision: Union[str, None] = "e2b3c4d5f6a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    memory_columns = {col["name"] for col in inspector.get_columns("memory")}
    memory_indexes = {idx["name"] for idx in inspector.get_indexes("memory")}

    with op.batch_alter_table("memory") as batch_op:
        if "type" not in memory_columns:
            batch_op.add_column(
                sa.Column(
                    "type",
                    sa.String(),
                    nullable=True,
                    server_default="context",
                )
            )
        if "path" not in memory_columns:
            batch_op.add_column(sa.Column("path", sa.Text(), nullable=True))
        if "meta" not in memory_columns:
            batch_op.add_column(sa.Column("meta", sa.JSON(), nullable=True))

    # Backfill NULL type values for existing rows (defensive; server_default
    # already covers new inserts but pre-existing rows may be NULL).
    op.execute("UPDATE memory SET type = 'context' WHERE type IS NULL")

    if "ix_memory_user_id" not in memory_indexes:
        op.create_index("ix_memory_user_id", "memory", ["user_id"])
    if "ix_memory_type" not in memory_indexes:
        op.create_index("ix_memory_type", "memory", ["type"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    memory_indexes = {idx["name"] for idx in inspector.get_indexes("memory")}
    if "ix_memory_type" in memory_indexes:
        op.drop_index("ix_memory_type", table_name="memory")
    if "ix_memory_user_id" in memory_indexes:
        op.drop_index("ix_memory_user_id", table_name="memory")

    with op.batch_alter_table("memory") as batch_op:
        memory_columns = {col["name"] for col in inspector.get_columns("memory")}
        if "meta" in memory_columns:
            batch_op.drop_column("meta")
        if "path" in memory_columns:
            batch_op.drop_column("path")
        if "type" in memory_columns:
            batch_op.drop_column("type")
