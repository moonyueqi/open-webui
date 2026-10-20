"""Backfill meta.has_user_valves for pre-existing tools

Revision ID: c6d7e8f9a0b1
Revises: b5c6d7e8f9a0
Create Date: 2026-08-25 13:00:00.000000

The tools list endpoint decides whether to show the chat-side valves
(config) button via `has_user_valves`. That flag used to be computed only
from the in-memory module cache (app.state.TOOLS), which is emptied on
every restart, so after each redeploy the button disappeared until each
tool was loaded once (upstream open-webui issue #26256).

The fix persists `has_user_valves` into `tool.meta` on create/update and
falls back to it when the module isn't cached. This migration backfills
the flag for tools created before the fix, by statically checking whether
the tool source defines a `UserValves` class. Static inspection is used
instead of importing the module so the migration never executes
user-supplied tool code.
"""

import json
import re
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from open_webui.migrations.util import get_existing_tables

revision: str = "c6d7e8f9a0b1"
down_revision: Union[str, None] = "b5c6d7e8f9a0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Matches a top-level or nested `class UserValves(...):` definition.
USER_VALVES_RE = re.compile(r"^\s*class\s+UserValves\b", re.MULTILINE)


def upgrade() -> None:
    if "tool" not in set(get_existing_tables()):
        return

    conn = op.get_bind()

    rows = conn.execute(sa.text('SELECT id, content, meta FROM "tool"')).fetchall()

    for tool_id, content, meta_raw in rows:
        try:
            meta = json.loads(meta_raw) if meta_raw else {}
        except (ValueError, TypeError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}

        if "has_user_valves" in meta:
            continue

        meta["has_user_valves"] = bool(USER_VALVES_RE.search(content or ""))

        conn.execute(
            sa.text('UPDATE "tool" SET meta = :meta WHERE id = :id'),
            {"meta": json.dumps(meta), "id": tool_id},
        )


def downgrade() -> None:
    if "tool" not in set(get_existing_tables()):
        return

    conn = op.get_bind()

    rows = conn.execute(sa.text('SELECT id, meta FROM "tool"')).fetchall()

    for tool_id, meta_raw in rows:
        try:
            meta = json.loads(meta_raw) if meta_raw else None
        except (ValueError, TypeError):
            continue
        if not isinstance(meta, dict) or "has_user_valves" not in meta:
            continue

        meta.pop("has_user_valves", None)
        conn.execute(
            sa.text('UPDATE "tool" SET meta = :meta WHERE id = :id'),
            {"meta": json.dumps(meta), "id": tool_id},
        )
