import time
import uuid
from typing import Optional, Literal

from sqlalchemy.orm import Session
from open_webui.internal.db import Base, get_db, get_db_context
from pydantic import BaseModel, ConfigDict
from sqlalchemy import JSON, BigInteger, Column, String, Text

####################
# Memory DB Schema
####################


class Memory(Base):
    __tablename__ = "memory"

    id = Column(String, primary_key=True, unique=True)
    user_id = Column(String, index=True)
    type = Column(String, default="context", server_default="context", index=True)
    path = Column(Text, nullable=True)
    content = Column(Text)
    meta = Column(JSON, nullable=True)
    updated_at = Column(BigInteger)
    created_at = Column(BigInteger)


class MemoryModel(BaseModel):
    id: str
    user_id: str
    type: Literal["user", "context"] = "context"
    path: Optional[str] = None
    content: str
    meta: Optional[dict] = None
    updated_at: int  # timestamp in epoch
    created_at: int  # timestamp in epoch

    model_config = ConfigDict(from_attributes=True)


####################
# Forms
####################


class MemoriesTable:
    @staticmethod
    def normalize_memory_type(memory_type: Optional[str] = None) -> str:
        return "user" if memory_type == "user" else "context"

    def insert_new_memory(
        self,
        user_id: str,
        content: str,
        memory_type: Optional[str] = None,
        path: Optional[str] = None,
        meta: Optional[dict] = None,
        db: Optional[Session] = None,
    ) -> Optional[MemoryModel]:
        with get_db_context(db) as db:
            id = str(uuid.uuid4())
            now = int(time.time())

            result = Memory(
                id=id,
                user_id=user_id,
                type=self.normalize_memory_type(memory_type),
                path=path,
                content=content,
                meta=meta,
                created_at=now,
                updated_at=now,
            )
            db.add(result)
            db.commit()
            db.refresh(result)
            if result:
                return MemoryModel.model_validate(result)
            else:
                return None

    def update_memory_by_id_and_user_id(
        self,
        id: str,
        user_id: str,
        content: Optional[str],
        memory_type: Optional[str] = None,
        path: Optional[str] = None,
        update_path: bool = False,
        meta: Optional[dict] = None,
        db: Optional[Session] = None,
    ) -> Optional[MemoryModel]:
        with get_db_context(db) as db:
            try:
                memory = db.get(Memory, id)
                if not memory or memory.user_id != user_id:
                    return None

                if content is not None:
                    memory.content = content
                if memory_type is not None:
                    memory.type = self.normalize_memory_type(memory_type)
                if update_path:
                    memory.path = path
                if meta is not None:
                    memory.meta = {**(memory.meta or {}), **meta}
                memory.updated_at = int(time.time())

                db.commit()
                db.refresh(memory)
                return MemoryModel.model_validate(memory)
            except Exception:
                return None

    def get_memories(self, db: Optional[Session] = None) -> list[MemoryModel]:
        with get_db_context(db) as db:
            try:
                memories = db.query(Memory).all()
                return [MemoryModel.model_validate(memory) for memory in memories]
            except Exception:
                return None

    def get_memories_by_user_id(
        self, user_id: str, db: Optional[Session] = None
    ) -> list[MemoryModel]:
        with get_db_context(db) as db:
            try:
                memories = db.query(Memory).filter_by(user_id=user_id).all()
                return [MemoryModel.model_validate(memory) for memory in memories]
            except Exception:
                return None

    def get_memory_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[MemoryModel]:
        with get_db_context(db) as db:
            try:
                memory = db.get(Memory, id)
                return MemoryModel.model_validate(memory)
            except Exception:
                return None

    def delete_memory_by_id(self, id: str, db: Optional[Session] = None) -> bool:
        with get_db_context(db) as db:
            try:
                db.query(Memory).filter_by(id=id).delete()
                db.commit()

                return True

            except Exception:
                return False

    def delete_memories_by_user_id(
        self, user_id: str, db: Optional[Session] = None
    ) -> bool:
        with get_db_context(db) as db:
            try:
                db.query(Memory).filter_by(user_id=user_id).delete()
                db.commit()

                return True
            except Exception:
                return False

    def delete_memory_by_id_and_user_id(
        self, id: str, user_id: str, db: Optional[Session] = None
    ) -> bool:
        with get_db_context(db) as db:
            try:
                memory = db.get(Memory, id)
                if not memory or memory.user_id != user_id:
                    return None

                # Delete the memory
                db.delete(memory)
                db.commit()

                return True
            except Exception:
                return False

    def apply_memory_operations(
        self,
        user_id: str,
        operations: list[dict],
        db: Optional[Session] = None,
    ) -> list[dict]:
        now = int(time.time())
        results: list[dict] = []

        with get_db_context(db) as db:
            for operation in operations:
                action = operation.get("action")

                if action == "add":
                    content = operation.get("content", "").strip()
                    memory_type = self.normalize_memory_type(operation.get("type"))
                    path = operation.get("path")
                    existing = (
                        db.query(Memory)
                        .filter_by(
                            user_id=user_id,
                            content=content,
                            type=memory_type,
                            path=path,
                        )
                        .first()
                    )
                    if existing:
                        results.append(
                            {
                                "action": action,
                                "status": "skipped",
                                "memory": MemoryModel.model_validate(existing),
                                "reason": "duplicate",
                            }
                        )
                        continue

                    memory = Memory(
                        id=str(uuid.uuid4()),
                        user_id=user_id,
                        type=memory_type,
                        path=path,
                        content=content,
                        meta=operation.get("meta"),
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(memory)
                    db.flush()
                    results.append(
                        {
                            "action": action,
                            "status": "created",
                            "memory": MemoryModel.model_validate(memory),
                        }
                    )

                elif action == "replace":
                    memory_id = operation.get("id")
                    content = operation.get("content", "").strip()
                    memory = db.get(Memory, memory_id)
                    if not memory or memory.user_id != user_id:
                        raise ValueError(f"Memory not found: {memory_id}")

                    memory.content = content
                    if operation.get("type") is not None:
                        memory.type = self.normalize_memory_type(operation.get("type"))
                    if "path" in operation:
                        memory.path = operation.get("path")
                    if operation.get("meta") is not None:
                        memory.meta = {**(memory.meta or {}), **operation.get("meta")}
                    memory.updated_at = now
                    db.flush()
                    results.append(
                        {
                            "action": action,
                            "status": "updated",
                            "memory": MemoryModel.model_validate(memory),
                        }
                    )

                elif action == "move":
                    memory_id = operation.get("id")
                    memory = db.get(Memory, memory_id)
                    if not memory or memory.user_id != user_id:
                        raise ValueError(f"Memory not found: {memory_id}")

                    memory.path = operation.get("path")
                    if operation.get("meta") is not None:
                        memory.meta = {**(memory.meta or {}), **operation.get("meta")}
                    memory.updated_at = now
                    db.flush()
                    results.append(
                        {
                            "action": action,
                            "status": "updated",
                            "memory": MemoryModel.model_validate(memory),
                        }
                    )

                elif action == "remove":
                    memory_id = operation.get("id")
                    memory = db.get(Memory, memory_id)
                    if not memory or memory.user_id != user_id:
                        raise ValueError(f"Memory not found: {memory_id}")

                    db.delete(memory)
                    results.append(
                        {"action": action, "status": "deleted", "id": memory_id}
                    )

                else:
                    raise ValueError(f"Unsupported memory operation: {action}")

            db.commit()

        return results


Memories = MemoriesTable()
