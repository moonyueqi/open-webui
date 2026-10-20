"""
Sub-agent delegation.

Ported from upstream Open WebUI v0.11.0 `backend/open_webui/utils/subagents.py`,
adapted to this fork's synchronous model layer and `PersistentConfig` settings.

A sub-agent is a real chat that runs the full completion pipeline through
`app.state.CHAT_COMPLETION_HANDLER`, exactly like a user-driven request. That is
what gives it the same model, tools, skills and filters as the parent chat; the
final assistant message is then read back from the database and returned to the
parent tool loop.

Background delegation (upstream's `SUBAGENTS_MAX_ASYNC` / `background=True`) is
not implemented here; only foreground sub-agents run.
"""

import asyncio
import copy
import logging
import time
from uuid import uuid4

from fastapi import Request
from starlette.datastructures import Headers

from open_webui.internal.db import get_db
from open_webui.models.chats import Chat, ChatForm, Chats
from open_webui.models.users import UserModel, Users

log = logging.getLogger(__name__)

DEFAULT_SUBAGENT_SYSTEM_PROMPT = """You are a sub-agent working on a specific task assigned by the lead agent.

Focus exclusively on your assigned task. Do NOT work on anything outside your scope.

When done, end with a clear summary:
- What you did
- What files you changed (if any)
- Any issues or open questions
"""

# A sub-agent runs unattended, so it must not be able to rewrite what the user
# has told the assistant to remember.
MUTATING_MEMORY_TOOLS = {
    "add_memory",
    "delete_memory",
    "replace_memory_content",
    "update_memory",
}

_foreground_semaphore: asyncio.Semaphore | None = None
_foreground_semaphore_size: int | None = None


def _build_request(source: Request) -> Request:
    """Build a minimal internal ASGI Request for the sub-agent completion.

    `state.internal` marks the request as agent-driven: it strips memory-mutating
    tools and blocks a sub-agent from delegating again.
    """
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.0"},
        "method": "POST",
        "path": "/api/v1/subagents/internal",
        "query_string": b"",
        "headers": Headers({}).raw,
        "client": ("127.0.0.1", 0),
        "server": ("127.0.0.1", 80),
        "scheme": "http",
        "app": source.app,
    }
    request = Request(scope)
    request.state.token = None
    request.state.enable_api_keys = False
    request.state.internal = True
    return request


def _get_foreground_semaphore(max_concurrent: int) -> asyncio.Semaphore | None:
    """Cap concurrent foreground sub-agents; -1 means unlimited."""
    global _foreground_semaphore, _foreground_semaphore_size

    if max_concurrent == -1:
        return None

    max_concurrent = max(1, max_concurrent)
    if _foreground_semaphore is None or _foreground_semaphore_size != max_concurrent:
        _foreground_semaphore = asyncio.Semaphore(max_concurrent)
        _foreground_semaphore_size = max_concurrent
    return _foreground_semaphore


def _mark_subagent_chat(chat_id: str, meta: dict) -> None:
    """Flag the chat as a sub-agent run and archive it so it stays out of the list.

    Upstream passes `internal_meta` straight to `Chats.insert_new_chat`; this
    fork's signature has no such parameter, so the row is updated afterwards.
    """
    try:
        with get_db() as db:
            row = db.get(Chat, chat_id)
            if not row:
                return
            row.meta = {**(row.meta or {}), **meta}
            row.archived = True
            row.updated_at = int(time.time())
            db.commit()
    except Exception:
        log.exception("Failed to mark sub-agent chat %s", chat_id)


def _extract_summary(message: dict | None) -> str:
    """Read the assistant reply, falling back to structured output items."""
    if not message:
        return ""

    summary = message.get("content") or ""
    if isinstance(summary, list):
        summary = "".join(
            str(item.get("text", ""))
            for item in summary
            if isinstance(item, dict) and item.get("type") == "text"
        )
    if not summary:
        summary = "".join(
            str(part.get("text", ""))
            for item in message.get("output") or []
            if item.get("type") == "message"
            for part in item.get("content") or []
            if part.get("type") == "output_text"
        )
    return summary


async def delegate(
    task: str,
    context: str,
    *,
    request: Request,
    user_data: dict,
    metadata: dict,
    parent_chat_id: str,
    parent_message_id: str | None,
) -> str:
    task = (task or "").strip()
    if not task:
        return "Error: task must not be empty."
    if not user_data.get("id"):
        return "Error: user context is required."

    config = request.app.state.config
    max_concurrent = int(config.SUBAGENTS_MAX_CONCURRENT or 20)
    max_iterations = max(1, int(config.SUBAGENTS_MAX_ITERATIONS or 30))
    max_output = max(1, int(config.SUBAGENTS_MAX_OUTPUT or 30_000))

    run = {
        "model_id": metadata.get("model_id") or (metadata.get("model") or {}).get("id"),
        "session_id": metadata.get("session_id"),
        "tool_ids": copy.deepcopy(metadata.get("tool_ids") or []),
        "skill_ids": copy.deepcopy(metadata.get("skill_ids") or []),
        "filter_ids": copy.deepcopy(metadata.get("filter_ids") or []),
        "terminal_id": metadata.get("terminal_id"),
        "features": copy.deepcopy(metadata.get("features") or {}),
        "files": copy.deepcopy(metadata.get("files") or []),
        "variables": copy.deepcopy(metadata.get("variables") or {}),
        "direct": bool(metadata.get("direct")),
    }
    if not run["model_id"]:
        return "Error: model context is required."
    if run["direct"]:
        return "Error: sub-agents are unavailable for direct connections."

    delegation_id = f"deleg_{uuid4().hex[:8]}"
    semaphore = _get_foreground_semaphore(max_concurrent)
    if semaphore:
        await semaphore.acquire()

    try:
        user = UserModel(**user_data) if isinstance(user_data, dict) else user_data
        user_row = Users.get_user_by_id(user.id)
        if not user_row:
            raise RuntimeError("user not found")

        user_message_id = str(uuid4())
        assistant_message_id = str(uuid4())
        prompt = f"{task}\n\n## Context\n{context}" if context else task

        chat = Chats.insert_new_chat(
            user.id,
            ChatForm(
                chat={
                    "title": f"Sub-agent: {task[:60]}",
                    "models": [run["model_id"]],
                    "history": {
                        "currentId": assistant_message_id,
                        "messages": {
                            user_message_id: {
                                "id": user_message_id,
                                "parentId": None,
                                "childrenIds": [assistant_message_id],
                                "role": "user",
                                "content": prompt,
                                "timestamp": int(time.time()),
                                "models": [run["model_id"]],
                            },
                            assistant_message_id: {
                                "id": assistant_message_id,
                                "parentId": user_message_id,
                                "childrenIds": [],
                                "role": "assistant",
                                "content": "",
                                "done": False,
                                "model": run["model_id"],
                                "timestamp": int(time.time()),
                            },
                        },
                    },
                    "messages": [{"role": "user", "content": prompt}],
                }
            ),
        )
        if not chat:
            raise RuntimeError("failed to create sub-agent chat")

        chat_id = chat.id
        _mark_subagent_chat(
            chat_id,
            {
                "internal": True,
                "type": "subagent",
                "parent_chat_id": parent_chat_id,
                "parent_message_id": parent_message_id,
                "delegation_id": delegation_id,
            },
        )
    except Exception as e:
        if semaphore:
            semaphore.release()
        log.exception("Failed to create sub-agent chat")
        return f"Error: failed to create sub-agent: {e}"

    async def run_subagent_chat() -> str:
        started_at = time.perf_counter()
        try:
            child_request = _build_request(request)
            child_request.state.max_tool_call_iterations = max_iterations

            subagent_system_prompt = (
                str(config.SUBAGENTS_SYSTEM_PROMPT or "").strip()
                or DEFAULT_SUBAGENT_SYSTEM_PROMPT
            )

            form_data = {
                "model": run["model_id"],
                "messages": [
                    {"role": "system", "content": subagent_system_prompt},
                    {"role": "user", "content": prompt},
                ],
                "stream": True,
                "chat_id": chat_id,
                "id": assistant_message_id,
                "parent_id": None,
                "session_id": run["session_id"] or f"subagent:{chat_id}",
                "background_tasks": {},
                "tool_ids": run["tool_ids"],
                "skill_ids": run["skill_ids"],
                "filter_ids": run["filter_ids"],
                "features": run["features"],
                "files": run["files"],
                "variables": run["variables"],
            }
            if run["terminal_id"]:
                form_data["terminal_id"] = run["terminal_id"]

            await request.app.state.CHAT_COMPLETION_HANDLER(
                child_request, form_data, user=user_row
            )

            message = Chats.get_message_by_id_and_message_id(
                chat_id, assistant_message_id
            )
            if not message:
                return "Error: sub-agent completion message no longer exists."

            error = message.get("error")
            if error:
                detail = error.get("content") if isinstance(error, dict) else error
                return f"Error: {detail}"

            summary = _extract_summary(message)
            if len(summary) > max_output:
                summary = f"{summary[:max_output]}\n\n[output truncated]"
            return summary or "Sub-agent produced no output."
        finally:
            log.info(
                "Sub-agent %s finished in %.1fs",
                delegation_id,
                time.perf_counter() - started_at,
            )
            if semaphore:
                semaphore.release()

    try:
        from open_webui.tasks import create_task

        _, child_task = await create_task(
            request.app.state.redis, run_subagent_chat(), id=chat_id
        )
    except Exception as e:
        if semaphore:
            semaphore.release()
        log.exception("Failed to start sub-agent task")
        return f"Error: {e}"

    try:
        return await child_task
    except asyncio.CancelledError:
        current = asyncio.current_task()
        if current and current.cancelling():
            raise
        return "Error: sub-agent was cancelled."
    except Exception as e:
        log.exception("Sub-agent run failed")
        return f"Error: {e}"
