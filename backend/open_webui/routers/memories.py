from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
import logging
import asyncio
from typing import Optional, Literal

from open_webui.models.memories import Memories, MemoryModel
from open_webui.retrieval.vector.factory import VECTOR_DB_CLIENT
from open_webui.config import RAG_EMBEDDING_QUERY_PREFIX
from open_webui.utils.auth import get_verified_user
from open_webui.internal.db import get_session
from sqlalchemy.orm import Session

from open_webui.utils.access_control import require_permission
from open_webui.utils.memory import (
    clean_memory_content,
    clean_memory_path,
    list_memory_path_groups,
    memory_vector_text,
    read_memory_path_rows,
    search_memory_rows,
    validate_memory_operations,
)
from open_webui.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)

router = APIRouter()


def _memory_metadata(memory: MemoryModel) -> dict:
    return {
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
        "type": memory.type,
        "path": memory.path,
    }


############################
# GetMemories
############################


@router.get("/", response_model=list[MemoryModel])
async def get_memories(
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    return Memories.get_memories_by_user_id(user.id, db=db)


############################
# AddMemory
############################


class AddMemoryForm(BaseModel):
    content: str
    type: Literal["user", "context"] = "context"
    path: Optional[str] = None


class MemoryUpdateModel(BaseModel):
    content: Optional[str] = None
    type: Optional[Literal["user", "context"]] = None
    path: Optional[str] = None


class MemoryOperationModel(BaseModel):
    action: Literal["add", "replace", "remove", "move"]
    id: Optional[str] = None
    content: Optional[str] = None
    type: Optional[Literal["user", "context"]] = None
    path: Optional[str] = None


class UpdateMemoriesForm(BaseModel):
    operations: list[MemoryOperationModel]
    source: Optional[Literal["tool", "background_review"]] = None


class SearchMemoriesForm(BaseModel):
    query: Optional[str] = None
    type: Literal["user", "context", "all"] = "all"
    path: Optional[str] = None
    memory_id: Optional[str] = None
    limit: int = 20


class ListMemoryPathsForm(BaseModel):
    query: Optional[str] = None
    type: Literal["user", "context", "all"] = "all"
    limit: int = 100


class ReadMemoryPathForm(BaseModel):
    path: str
    type: Literal["user", "context", "all"] = "all"
    include_children: bool = True
    limit: int = 50


@router.post("/add", response_model=Optional[MemoryModel])
async def add_memory(
    request: Request,
    form_data: AddMemoryForm,
    user=Depends(get_verified_user),
):
    # NOTE: We intentionally do NOT use Depends(get_session) here.
    # Database operations (insert_new_memory) manage their own short-lived sessions.
    # This prevents holding a connection during EMBEDDING_FUNCTION()
    # which makes external embedding API calls (1-5+ seconds).
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    content = clean_memory_content(form_data.content)
    path = clean_memory_path(form_data.path)
    memory = Memories.insert_new_memory(
        user.id,
        content,
        memory_type=form_data.type,
        path=path,
        meta={"created_by": "manual"},
    )

    try:
        vector = await request.app.state.EMBEDDING_FUNCTION(
            memory_vector_text(memory.content, memory.path), user=user
        )
    except Exception as e:
        log.exception(f"Embedding failed in add_memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ERROR_MESSAGES.EMBEDDING_MODEL_UNAVAILABLE,
        )

    VECTOR_DB_CLIENT.upsert(
        collection_name=f"user-memory-{user.id}",
        items=[
            {
                "id": memory.id,
                "text": memory_vector_text(memory.content, memory.path),
                "vector": vector,
                "metadata": _memory_metadata(memory),
            }
        ],
    )

    return memory


############################
# UpdateMemories (batch operations)
############################


@router.post("/update", response_model=list[dict])
async def update_memories(
    request: Request,
    form_data: UpdateMemoriesForm,
    user=Depends(get_verified_user),
):
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    operations = validate_memory_operations(form_data)
    metadata = getattr(request.state, "metadata", {}) or {}
    source = form_data.source or "tool"
    for operation in operations:
        if operation.get("action") in {"add", "replace", "move"}:
            operation["meta"] = {
                "created_by": source,
                "chat_id": metadata.get("chat_id"),
                "message_id": metadata.get("message_id"),
                "model": metadata.get("model"),
            }

    try:
        results = Memories.apply_memory_operations(user.id, operations)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    upsert_items = []
    delete_ids = []
    response = []

    for result in results:
        memory = result.get("memory")
        if isinstance(memory, MemoryModel):
            result = {**result, "memory": memory.model_dump()}
            if result.get("status") in {"created", "updated"}:
                try:
                    vector = await request.app.state.EMBEDDING_FUNCTION(
                        memory_vector_text(memory.content, memory.path),
                        user=user,
                    )
                except Exception as e:
                    log.exception(f"Embedding failed in update_memories: {e}")
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail=ERROR_MESSAGES.EMBEDDING_MODEL_UNAVAILABLE,
                    )
                upsert_items.append(
                    {
                        "id": memory.id,
                        "text": memory_vector_text(memory.content, memory.path),
                        "vector": vector,
                        "metadata": _memory_metadata(memory),
                    }
                )
        if result.get("status") == "deleted" and result.get("id"):
            delete_ids.append(result["id"])
        response.append(result)

    if upsert_items:
        VECTOR_DB_CLIENT.upsert(
            collection_name=f"user-memory-{user.id}", items=upsert_items
        )

    if delete_ids:
        VECTOR_DB_CLIENT.delete(
            collection_name=f"user-memory-{user.id}", ids=delete_ids
        )

    return response


############################
# QueryMemory
############################


class QueryMemoryForm(BaseModel):
    content: str
    k: Optional[int] = 1


@router.post("/query")
async def query_memory(
    request: Request,
    form_data: QueryMemoryForm,
    user=Depends(get_verified_user),
):
    # NOTE: We intentionally do NOT use Depends(get_session) here.
    # Database operations (get_memories_by_user_id) manage their own short-lived sessions.
    # This prevents holding a connection during EMBEDDING_FUNCTION()
    # which makes external embedding API calls (1-5+ seconds).
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    memories = Memories.get_memories_by_user_id(user.id)
    if not memories:
        raise HTTPException(status_code=404, detail="未找到该用户的记忆。")

    try:
        vector = await request.app.state.EMBEDDING_FUNCTION(
            form_data.content, prefix=RAG_EMBEDDING_QUERY_PREFIX, user=user
        )
    except Exception as e:
        log.exception(f"Embedding failed in query_memory: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ERROR_MESSAGES.EMBEDDING_MODEL_UNAVAILABLE,
        )

    results = VECTOR_DB_CLIENT.search(
        collection_name=f"user-memory-{user.id}",
        vectors=[vector],
        limit=form_data.k,
    )

    # Filter results by relevance threshold to avoid returning unrelated
    # memories. Vector similarity search always returns the top-K nearest
    # neighbours even when they are completely irrelevant; applying the same
    # RELEVANCE_THRESHOLD used by RAG ensures only genuinely matching memories
    # are surfaced (distances are normalised to 0->1, higher is better).
    # Defaults to 0.0 which keeps the legacy behaviour (no filtering).
    relevance_threshold = getattr(
        request.app.state.config, "RELEVANCE_THRESHOLD", 0.0
    )
    if (
        results
        and relevance_threshold > 0.0
        and results.distances
        and results.distances[0]
    ):
        from open_webui.retrieval.vector.main import SearchResult

        filtered_ids = []
        filtered_docs = []
        filtered_metas = []
        filtered_dists = []

        for idx, score in enumerate(results.distances[0]):
            if score >= relevance_threshold:
                if results.ids and results.ids[0]:
                    filtered_ids.append(results.ids[0][idx])
                if results.documents and results.documents[0]:
                    filtered_docs.append(results.documents[0][idx])
                if results.metadatas and results.metadatas[0]:
                    filtered_metas.append(results.metadatas[0][idx])
                filtered_dists.append(score)

        results = SearchResult(
            ids=[filtered_ids] if filtered_ids else [[]],
            documents=[filtered_docs] if filtered_docs else [[]],
            metadatas=[filtered_metas] if filtered_metas else [[]],
            distances=[filtered_dists] if filtered_dists else [[]],
        )

    return results


############################
# SearchMemories / ListMemoryPaths / ReadMemoryPath (text/path browsing)
############################


@router.post("/search", response_model=list[MemoryModel])
async def search_memories(
    request: Request,
    form_data: SearchMemoriesForm,
    user=Depends(get_verified_user),
):
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    memories = Memories.get_memories_by_user_id(user.id)
    return search_memory_rows(
        memories,
        query=form_data.query,
        path=form_data.path,
        memory_id=form_data.memory_id,
        memory_type=form_data.type,
        limit=form_data.limit,
    )


@router.post("/paths")
async def list_memory_paths(
    request: Request,
    form_data: ListMemoryPathsForm,
    user=Depends(get_verified_user),
):
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    memories = Memories.get_memories_by_user_id(user.id)
    return list_memory_path_groups(
        memories,
        query=form_data.query or "",
        memory_type=form_data.type,
        limit=form_data.limit,
    )


@router.post("/path")
async def read_memory_path(
    request: Request,
    form_data: ReadMemoryPathForm,
    user=Depends(get_verified_user),
):
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    memories = Memories.get_memories_by_user_id(user.id)
    result = read_memory_path_rows(
        memories,
        path=form_data.path,
        memory_type=form_data.type,
        include_children=form_data.include_children,
        limit=form_data.limit,
    )
    return {
        **result,
        "memories": [memory.model_dump() for memory in result["memories"]],
    }


############################
# ResetMemoryFromVectorDB
############################
@router.post("/reset", response_model=bool)
async def reset_memory_from_vector_db(
    request: Request,
    user=Depends(get_verified_user),
):
    """Reset user's memory vector embeddings.

    CRITICAL: We intentionally do NOT use Depends(get_session) here.
    This endpoint generates embeddings for ALL user memories in parallel using
    asyncio.gather(). A user with 100 memories would trigger 100 embedding API
    calls simultaneously. With a session held, this could block a connection
    for MINUTES, completely exhausting the connection pool.
    """
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    VECTOR_DB_CLIENT.delete_collection(f"user-memory-{user.id}")

    memories = Memories.get_memories_by_user_id(user.id)

    try:
        vectors = await asyncio.gather(
            *[
                request.app.state.EMBEDDING_FUNCTION(
                    memory_vector_text(memory.content, memory.path), user=user
                )
                for memory in memories
            ]
        )
    except Exception as e:
        log.exception(f"Embedding failed in reset_memory_from_vector_db: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ERROR_MESSAGES.EMBEDDING_MODEL_UNAVAILABLE,
        )

    VECTOR_DB_CLIENT.upsert(
        collection_name=f"user-memory-{user.id}",
        items=[
            {
                "id": memory.id,
                "text": memory_vector_text(memory.content, memory.path),
                "vector": vectors[idx],
                "metadata": _memory_metadata(memory),
            }
            for idx, memory in enumerate(memories)
        ],
    )

    return True


############################
# DeleteMemoriesByUserId
############################


@router.delete("/delete/user", response_model=bool)
async def delete_memory_by_user_id(
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    result = Memories.delete_memories_by_user_id(user.id, db=db)

    if result:
        try:
            VECTOR_DB_CLIENT.delete_collection(f"user-memory-{user.id}")
        except Exception as e:
            log.error(e)
        return True

    return False


############################
# UpdateMemoryById
############################


@router.post("/{memory_id}/update", response_model=Optional[MemoryModel])
async def update_memory_by_id(
    memory_id: str,
    request: Request,
    form_data: MemoryUpdateModel,
    user=Depends(get_verified_user),
):
    # NOTE: We intentionally do NOT use Depends(get_session) here.
    # Database operations (update_memory_by_id_and_user_id) manage their own
    # short-lived sessions. This prevents holding a connection during
    # EMBEDDING_FUNCTION() which makes external API calls (1-5+ seconds).
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    content = (
        clean_memory_content(form_data.content)
        if form_data.content is not None
        else None
    )
    path = clean_memory_path(form_data.path)
    if content is None and form_data.type is None and form_data.path is None:
        raise HTTPException(status_code=400, detail="未提供任何记忆更新内容。")

    memory = Memories.update_memory_by_id_and_user_id(
        memory_id,
        user.id,
        content,
        memory_type=form_data.type,
        path=path,
        update_path=form_data.path is not None,
        meta={"created_by": "manual"},
    )
    if memory is None:
        raise HTTPException(status_code=404, detail="未找到该记忆。")

    if form_data.content is not None or form_data.path is not None:
        try:
            vector = await request.app.state.EMBEDDING_FUNCTION(
                memory_vector_text(memory.content, memory.path), user=user
            )
        except Exception as e:
            log.exception(f"Embedding failed in update_memory_by_id: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=ERROR_MESSAGES.EMBEDDING_MODEL_UNAVAILABLE,
            )

        VECTOR_DB_CLIENT.upsert(
            collection_name=f"user-memory-{user.id}",
            items=[
                {
                    "id": memory.id,
                    "text": memory_vector_text(memory.content, memory.path),
                    "vector": vector,
                    "metadata": _memory_metadata(memory),
                }
            ],
        )

    return memory


############################
# DeleteMemoryById
############################


@router.delete("/{memory_id}", response_model=bool)
async def delete_memory_by_id(
    memory_id: str,
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    if not request.app.state.config.ENABLE_MEMORIES:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    require_permission(user, "features.memories", request)

    result = Memories.delete_memory_by_id_and_user_id(memory_id, user.id, db=db)

    if result:
        VECTOR_DB_CLIENT.delete(
            collection_name=f"user-memory-{user.id}", ids=[memory_id]
        )
        return True

    return False
