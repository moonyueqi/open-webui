"""Backfill category_id for prompts/skills left over from before *_category existed

Revision ID: b5c6d7e8f9a0
Revises: a4b5c6d7e8f9
Create Date: 2026-08-18 12:30:00.000000

Same root cause and fix as a4b5c6d7e8f9, but for `prompt`/`prompt_category`
and `skill`/`skill_category`: the migrations that introduced those category
tables (a1b2c3d4e5f7, e1a2b3c4d5f7) added a nullable `category_id` column
but never backfilled pre-existing rows, so any prompt/skill created before
categories existed has `category_id IS NULL` and — now that the
category-based workspace UI only ever lists items by category — never
shows up in any category page, even though the row is still in the
database.

For each of `prompt` and `skill`, this migration creates a single
"未分类" (Uncategorized) category, grants it public read access (mirroring
the historical `access_control IS NULL == public` semantics), and repoints
orphaned rows at it.
"""

from typing import Sequence, Union
import time
import uuid

from alembic import op
import sqlalchemy as sa

from open_webui.migrations.util import get_existing_tables

revision: str = "b5c6d7e8f9a0"
down_revision: Union[str, None] = "a4b5c6d7e8f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_CATEGORY_NAME = "未分类"

# (item_table, category_table, resource_type)
RESOURCES = [
    ("prompt", "prompt_category", "prompt_category"),
    ("skill", "skill_category", "skill_category"),
]


def _backfill(conn, existing_tables, item_table, category_table, resource_type):
    if item_table not in existing_tables or category_table not in existing_tables:
        return

    orphaned = conn.execute(
        sa.text(f'SELECT id, user_id FROM "{item_table}" WHERE category_id IS NULL')
    ).fetchall()
    if not orphaned:
        return

    now = int(time.time())

    category_row = conn.execute(
        sa.text(f'SELECT id FROM "{category_table}" WHERE name = :name'),
        {"name": DEFAULT_CATEGORY_NAME},
    ).fetchone()

    if category_row:
        category_id = category_row[0]
    else:
        owner_row = None
        if "user" in existing_tables:
            owner_row = conn.execute(
                sa.text(
                    'SELECT id FROM "user" WHERE role = \'admin\' ORDER BY created_at ASC LIMIT 1'
                )
            ).fetchone()
        owner_id = owner_row[0] if owner_row else orphaned[0][1]

        category_id = str(uuid.uuid4())
        conn.execute(
            sa.text(
                f"""
                INSERT INTO "{category_table}" (id, user_id, name, description, meta, created_at, updated_at)
                VALUES (:id, :user_id, :name, :description, :meta, :created_at, :updated_at)
                """
            ),
            {
                "id": category_id,
                "user_id": owner_id,
                "name": DEFAULT_CATEGORY_NAME,
                "description": "系统自动创建：用于存放升级前已存在、尚未分类的数据。",
                "meta": None,
                "created_at": now,
                "updated_at": now,
            },
        )

        if "access_grant" in existing_tables:
            try:
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO access_grant (id, resource_type, resource_id, principal_type, principal_id, permission, created_at)
                        VALUES (:id, :resource_type, :resource_id, :principal_type, :principal_id, :permission, :created_at)
                        """
                    ),
                    {
                        "id": str(uuid.uuid4()),
                        "resource_type": resource_type,
                        "resource_id": category_id,
                        "principal_type": "user",
                        "principal_id": "*",
                        "permission": "read",
                        "created_at": now,
                    },
                )
            except Exception:
                pass

    conn.execute(
        sa.text(
            f'UPDATE "{item_table}" SET category_id = :category_id WHERE category_id IS NULL'
        ),
        {"category_id": category_id},
    )


def upgrade() -> None:
    existing_tables = set(get_existing_tables())
    conn = op.get_bind()

    for item_table, category_table, resource_type in RESOURCES:
        _backfill(conn, existing_tables, item_table, category_table, resource_type)


def downgrade() -> None:
    existing_tables = set(get_existing_tables())
    conn = op.get_bind()

    for item_table, category_table, resource_type in RESOURCES:
        if item_table not in existing_tables or category_table not in existing_tables:
            continue

        category_row = conn.execute(
            sa.text(f'SELECT id FROM "{category_table}" WHERE name = :name'),
            {"name": DEFAULT_CATEGORY_NAME},
        ).fetchone()
        if not category_row:
            continue

        category_id = category_row[0]

        conn.execute(
            sa.text(
                f'UPDATE "{item_table}" SET category_id = NULL WHERE category_id = :category_id'
            ),
            {"category_id": category_id},
        )

        if "access_grant" in existing_tables:
            conn.execute(
                sa.text(
                    "DELETE FROM access_grant WHERE resource_type = :resource_type AND resource_id = :category_id"
                ),
                {"resource_type": resource_type, "category_id": category_id},
            )

        conn.execute(
            sa.text(f'DELETE FROM "{category_table}" WHERE id = :category_id'),
            {"category_id": category_id},
        )
