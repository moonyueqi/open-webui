"""Helper functions for the structured memory system.

Ported from upstream but stripped of the Config / event / background-review
dependencies. Only the pure path/search/grouping helpers and operation
validation are kept, so this module has no side effects and no dependency on
the DB-backed config system.
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException

from open_webui.models.memories import Memories


def clean_memory_content(content: Optional[str]) -> str:
    value = (content or "").strip()
    if not value:
        raise HTTPException(status_code=400, detail="记忆内容不能为空")
    return value


def clean_memory_path(path: Optional[str]) -> Optional[str]:
    value = re.sub(r"/+", "/", (path or "").strip().strip("/"))
    if not value:
        return None
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or any(
        ord(char) < 32 for char in value
    ):
        raise HTTPException(status_code=400, detail="记忆路径无效")
    return value


def memory_vector_text(content: str, path: Optional[str] = None) -> str:
    path = clean_memory_path(path)
    return f"{path}\n{content}" if path else content


def memory_label(memory) -> str:
    return f"{memory.path}: {memory.content}" if memory.path else memory.content


def _path_parts(path: Optional[str]) -> list[str]:
    return [part for part in (path or "").split("/") if part]


def _parent_path(path: Optional[str]) -> Optional[str]:
    parts = _path_parts(path)
    return "/".join(parts[:-1]) if len(parts) > 1 else None


def _path_rank(memory_path: Optional[str], lookup_path: Optional[str]):
    if not lookup_path:
        return None

    memory_path = clean_memory_path(memory_path)
    lookup_path = clean_memory_path(lookup_path)
    if not memory_path or not lookup_path:
        return None

    if memory_path == lookup_path:
        return (0, 0)
    if memory_path.startswith(f"{lookup_path}/"):
        return (1, len(_path_parts(memory_path)) - len(_path_parts(lookup_path)))
    if lookup_path.startswith(f"{memory_path}/"):
        return (2, len(_path_parts(lookup_path)) - len(_path_parts(memory_path)))
    if _parent_path(memory_path) and _parent_path(memory_path) == _parent_path(
        lookup_path
    ):
        return (3, 0)

    memory_parts = set(_path_parts(memory_path))
    lookup_parts = set(_path_parts(lookup_path))
    shared = len(memory_parts & lookup_parts)
    if shared:
        return (4, -shared)
    if _path_parts(memory_path)[-1:] == _path_parts(lookup_path)[-1:]:
        return (5, 0)

    return None


def _memory_matches_query(memory, query: str) -> bool:
    value = query.strip().lower()
    if not value:
        return True
    return value in (memory.content or "").lower() or value in (
        memory.path or ""
    ).lower()


def search_memory_rows(
    memories: list,
    *,
    query: Optional[str] = None,
    path: Optional[str] = None,
    memory_id: Optional[str] = None,
    memory_type: str = "all",
    limit: int = 20,
) -> list:
    rows = list(memories or [])
    if memory_id:
        rows = [memory for memory in rows if memory.id == memory_id]
    if memory_type != "all":
        rows = [memory for memory in rows if memory.type == memory_type]

    query = (query or "").strip()
    lookup_path = clean_memory_path(path)
    if lookup_path:
        basename = (
            _path_parts(lookup_path)[-1] if _path_parts(lookup_path) else lookup_path
        )

        def related(memory) -> bool:
            rank = _path_rank(memory.path, lookup_path)
            if rank is not None:
                return True
            haystack = f'{memory.path or ""}\n{memory.content or ""}'.lower()
            return lookup_path.lower() in haystack or basename.lower() in haystack

        rows = [memory for memory in rows if related(memory)]

    if query:
        rows = [memory for memory in rows if _memory_matches_query(memory, query)]

    def sort_key(memory):
        rank = _path_rank(memory.path, lookup_path) if lookup_path else None
        return rank if rank is not None else (9, 0), -(memory.updated_at or 0)

    return sorted(rows, key=sort_key)[: max(1, min(limit or 20, 100))]


def list_memory_path_groups(
    memories: list,
    *,
    query: str = "",
    memory_type: str = "all",
    limit: int = 100,
) -> dict:
    rows = [
        memory
        for memory in (memories or [])
        if (memory_type == "all" or memory.type == memory_type)
        and _memory_matches_query(memory, query)
    ]
    grouped: dict = {}
    for memory in rows:
        key = (memory.path, memory.type)
        group = grouped.setdefault(
            key,
            {
                "path": memory.path,
                "type": memory.type,
                "count": 0,
                "updated_at": 0,
                "children": [],
            },
        )
        group["count"] += 1
        group["updated_at"] = max(group["updated_at"], memory.updated_at or 0)

    paths = [path for path, _ in grouped if path]
    for group in grouped.values():
        path = group["path"]
        if not path:
            continue
        prefix = f"{path}/"
        children = []
        for candidate in paths:
            if not candidate.startswith(prefix):
                continue
            remainder = candidate[len(prefix) :]
            child = f'{prefix}{remainder.split("/", 1)[0]}'
            if child not in children:
                children.append(child)
        group["children"] = children[:20]

    groups = sorted(grouped.values(), key=lambda item: item["updated_at"], reverse=True)
    return {"paths": groups[: max(1, min(limit or 100, 500))], "count": len(groups)}


def read_memory_path_rows(
    memories: list,
    *,
    path: str,
    memory_type: str = "all",
    include_children: bool = True,
    limit: int = 50,
) -> dict:
    lookup_path = clean_memory_path(path)
    if not lookup_path:
        raise HTTPException(status_code=400, detail="需要提供记忆路径")

    rows = [
        memory
        for memory in (memories or [])
        if memory_type == "all" or memory.type == memory_type
    ]
    path_set = {memory.path for memory in rows if memory.path}
    parents = [
        "/".join(_path_parts(lookup_path)[:idx])
        for idx in range(1, len(_path_parts(lookup_path)))
        if "/".join(_path_parts(lookup_path)[:idx]) in path_set
    ]
    children = sorted(
        {
            f'{lookup_path}/{memory.path[len(lookup_path) + 1:].split("/", 1)[0]}'
            for memory in rows
            if memory.path and memory.path.startswith(f"{lookup_path}/")
        }
    )

    def selected(memory) -> bool:
        if memory.path == lookup_path:
            return True
        if memory.path in parents:
            return True
        return bool(
            include_children
            and memory.path
            and memory.path.startswith(f"{lookup_path}/")
        )

    selected_rows = [memory for memory in rows if selected(memory)]

    def sort_key(memory):
        if memory.path == lookup_path:
            return (0, 0, -(memory.updated_at or 0))
        if memory.path and memory.path.startswith(f"{lookup_path}/"):
            return (1, len(_path_parts(memory.path)), -(memory.updated_at or 0))
        return (2, -len(_path_parts(memory.path)), -(memory.updated_at or 0))

    return {
        "path": lookup_path,
        "parents": parents,
        "children": children[:50],
        "memories": sorted(selected_rows, key=sort_key)[
            : max(1, min(limit or 50, 100))
        ],
    }


def validate_memory_operations(form_data) -> list[dict]:
    if not form_data.operations:
        raise HTTPException(status_code=400, detail="未提供记忆操作")

    operations = []
    for operation in form_data.operations:
        op = operation.model_dump()
        action = op.get("action")

        if action == "add":
            op["content"] = clean_memory_content(op.get("content"))
            op["type"] = Memories.normalize_memory_type(op.get("type"))
            op["path"] = clean_memory_path(op.get("path"))
        elif action == "replace":
            if not op.get("id"):
                raise HTTPException(status_code=400, detail="replace 操作需要记忆 id")
            op["content"] = clean_memory_content(op.get("content"))
            if op.get("type") is not None:
                op["type"] = Memories.normalize_memory_type(op.get("type"))
            op["path"] = clean_memory_path(op.get("path"))
        elif action == "move":
            if not op.get("id"):
                raise HTTPException(status_code=400, detail="move 操作需要记忆 id")
            op["path"] = clean_memory_path(op.get("path"))
        elif action == "remove":
            if not op.get("id"):
                raise HTTPException(status_code=400, detail="remove 操作需要记忆 id")
        else:
            raise HTTPException(
                status_code=400, detail=f"不支持的记忆操作: {action}"
            )

        operations.append(op)

    return operations
