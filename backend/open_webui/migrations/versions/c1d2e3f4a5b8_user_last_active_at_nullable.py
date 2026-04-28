"""Make user.last_active_at nullable

Older databases that were initialized via the legacy Peewee migrations
(internal/migrations/007_add_user_last_active_at.py) ended up with a
NOT NULL constraint on `user.last_active_at`. The current SQLAlchemy
model treats this column as nullable (`Optional[int]`) and inserts
`None` for freshly created users so they don't appear "online" until
they actually become active.

This migration aligns the schema with the model on legacy installs.
On databases where the column is already nullable this is a no-op
in practice (batch_alter_table will recreate the table with the
intended definition).

Revision ID: c1d2e3f4a5b8
Revises: a1b2c3d4e5f7
Create Date: 2026-04-22 11:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f4a5b8"
down_revision: Union[str, None] = "a1b2c3d4e5f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column(
            "last_active_at",
            existing_type=sa.BigInteger(),
            nullable=True,
        )


def downgrade() -> None:
    with op.batch_alter_table("user") as batch_op:
        batch_op.alter_column(
            "last_active_at",
            existing_type=sa.BigInteger(),
            nullable=False,
        )
