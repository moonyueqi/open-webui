"""Backfill category_id for tools left over from before tool_category existed

Revision ID: a4b5c6d7e8f9
Revises: f3a1b2c4d5e6
Create Date: 2026-08-18 12:00:00.000000

The e2b3c4d5f6a8 migration added the (nullable) `tool.category_id` column
but never backfilled it for pre-existing tools. Since tool access is now
fully inherited from the parent tool_category, any tool with
`category_id IS NULL` became invisible everywhere in the workspace UI
(the tools page only lists categories, and category detail pages filter
strictly on `category_id = :id`) even though the row is still in the
database — which is why re-creating a tool with the same name/id still
reports "already exists".

This migration creates a single "未分类" (Uncategorized) tool_category for
any orphaned tools, grants it public read access (mirroring the historical
`access_control IS NULL == public` semantics used before access control was
normalized into access_grant), and repoints the orphaned tools at it so
they show up again.
"""

from typing import Sequence, Union
import time
import uuid

from alembic import op
import sqlalchemy as sa

from open_webui.migrations.util import get_existing_tables

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f3a1b2c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEFAULT_CATEGORY_NAME = "未分类"


def upgrade() -> None:
    existing_tables = set(get_existing_tables())
    if "tool" not in existing_tables or "tool_category" not in existing_tables:
        return

    conn = op.get_bind()

    orphaned = conn.execute(
        sa.text('SELECT id, user_id FROM "tool" WHERE category_id IS NULL')
    ).fetchall()
    if not orphaned:
        return

    now = int(time.time())

    category_row = conn.execute(
        sa.text('SELECT id FROM "tool_category" WHERE name = :name'),
        {"name": DEFAULT_CATEGORY_NAME},
    ).fetchone()

    if category_row:
        category_id = category_row[0]
    else:
        # Prefer an admin as the owner of the auto-created category; fall
        # back to the owner of the first orphaned tool if there is no
        # admin (e.g. non-standard setups).
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
                """
                INSERT INTO tool_category (id, user_id, name, description, meta, created_at, updated_at)
                VALUES (:id, :user_id, :name, :description, :meta, :created_at, :updated_at)
                """
            ),
            {
                "id": category_id,
                "user_id": owner_id,
                "name": DEFAULT_CATEGORY_NAME,
                "description": "系统自动创建：用于存放升级前已存在、尚未分类的工具。",
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
                        "resource_type": "tool_category",
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
            'UPDATE "tool" SET category_id = :category_id WHERE category_id IS NULL'
        ),
        {"category_id": category_id},
    )


def downgrade() -> None:
    existing_tables = set(get_existing_tables())
    if "tool" not in existing_tables or "tool_category" not in existing_tables:
        return

    conn = op.get_bind()

    category_row = conn.execute(
        sa.text('SELECT id FROM "tool_category" WHERE name = :name'),
        {"name": DEFAULT_CATEGORY_NAME},
    ).fetchone()
    if not category_row:
        return

    category_id = category_row[0]

    conn.execute(
        sa.text('UPDATE "tool" SET category_id = NULL WHERE category_id = :category_id'),
        {"category_id": category_id},
    )

    if "access_grant" in existing_tables:
        conn.execute(
            sa.text(
                "DELETE FROM access_grant WHERE resource_type = 'tool_category' AND resource_id = :category_id"
            ),
            {"category_id": category_id},
        )

    conn.execute(
        sa.text('DELETE FROM "tool_category" WHERE id = :category_id'),
        {"category_id": category_id},
    )
