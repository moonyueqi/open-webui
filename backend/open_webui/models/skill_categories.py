import logging
import time
import traceback
import uuid
from typing import Optional

from sqlalchemy.orm import Session
from open_webui.internal.db import Base, get_db_context
from open_webui.models.groups import Groups
from open_webui.models.users import User, UserModel, Users, UserResponse
from open_webui.models.access_grants import AccessGrantModel, AccessGrants

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Column, Text, JSON

log = logging.getLogger(__name__)

####################
# SkillCategory DB Schema
####################


class SkillCategory(Base):
    __tablename__ = "skill_category"

    id = Column(Text, unique=True, primary_key=True)
    user_id = Column(Text)
    name = Column(Text)
    description = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(BigInteger, nullable=True)
    updated_at = Column(BigInteger, nullable=True)


class SkillCategoryModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    name: str
    description: Optional[str] = None
    meta: Optional[dict] = None
    access_grants: list[AccessGrantModel] = Field(default_factory=list)
    created_at: Optional[int] = None
    updated_at: Optional[int] = None


####################
# Forms & Responses
####################


class SkillCategoryUserResponse(SkillCategoryModel):
    user: Optional[UserResponse] = None
    skill_count: Optional[int] = 0


class SkillCategoryAccessResponse(SkillCategoryUserResponse):
    write_access: Optional[bool] = False


class SkillCategoryForm(BaseModel):
    name: str
    description: Optional[str] = None
    access_grants: Optional[list[dict]] = None


class SkillCategoryListResponse(BaseModel):
    items: list[SkillCategoryUserResponse]
    total: int


class SkillCategoryAccessListResponse(BaseModel):
    items: list[SkillCategoryAccessResponse]
    total: int


class SkillCategoryAccessGrantsForm(BaseModel):
    access_grants: list[dict]


####################
# Table Operations
####################


class SkillCategoriesTable:
    def _get_access_grants(
        self, category_id: str, db: Optional[Session] = None
    ) -> list[AccessGrantModel]:
        return AccessGrants.get_grants_by_resource(
            "skill_category", category_id, db=db
        )

    def _to_category_model(
        self,
        category: SkillCategory,
        access_grants: Optional[list[AccessGrantModel]] = None,
        db: Optional[Session] = None,
    ) -> SkillCategoryModel:
        category_data = SkillCategoryModel.model_validate(category).model_dump(
            exclude={"access_grants"}
        )
        category_data["access_grants"] = (
            access_grants
            if access_grants is not None
            else self._get_access_grants(category_data["id"], db=db)
        )
        return SkillCategoryModel.model_validate(category_data)

    def insert_new_category(
        self,
        user_id: str,
        form_data: SkillCategoryForm,
        db: Optional[Session] = None,
    ) -> Optional[SkillCategoryModel]:
        with get_db_context(db) as db:
            try:
                now = int(time.time())
                payload = {
                    **form_data.model_dump(exclude={"access_grants"}),
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "created_at": now,
                    "updated_at": now,
                }

                result = SkillCategory(**payload)
                db.add(result)
                db.commit()
                db.refresh(result)

                new_id = result.id
                AccessGrants.set_access_grants(
                    "skill_category", new_id, form_data.access_grants, db=db
                )

                return self.get_category_by_id(new_id, db=db)
            except Exception:
                log.exception("Failed to create skill category")
                return None

    def search_categories(
        self,
        user_id: str,
        filter: dict,
        skip: int = 0,
        limit: int = 30,
        db: Optional[Session] = None,
    ) -> SkillCategoryListResponse:
        try:
            with get_db_context(db) as db:
                from open_webui.models.skills import Skill as SkillTable
                from sqlalchemy import func

                query = db.query(SkillCategory, User).outerjoin(
                    User, User.id == SkillCategory.user_id
                )

                if filter:
                    query_key = filter.get("query")
                    if query_key:
                        query = query.filter(
                            SkillCategory.name.ilike(f"%{query_key}%")
                        )

                    view_option = filter.get("view_option")
                    if view_option == "created":
                        query = query.filter(SkillCategory.user_id == user_id)
                    elif view_option == "shared":
                        query = query.filter(SkillCategory.user_id != user_id)

                    query = AccessGrants.has_permission_filter(
                        db=db,
                        query=query,
                        DocumentModel=SkillCategory,
                        filter=filter,
                        resource_type="skill_category",
                        permission="read",
                    )

                query = query.order_by(
                    SkillCategory.updated_at.desc(), SkillCategory.id.asc()
                )

                total = query.count()
                if skip:
                    query = query.offset(skip)
                if limit:
                    query = query.limit(limit)

                items = query.all()

                category_ids = [c.id for c, _ in items]
                grants_map = AccessGrants.get_grants_by_resources(
                    "skill_category", category_ids, db=db
                )

                skill_counts = {}
                if category_ids:
                    try:
                        count_results = (
                            db.query(
                                SkillTable.category_id,
                                func.count(SkillTable.id),
                            )
                            .filter(SkillTable.category_id.in_(category_ids))
                            .group_by(SkillTable.category_id)
                            .all()
                        )
                        skill_counts = {cid: cnt for cid, cnt in count_results}
                    except Exception as e:
                        log.warning("Failed to get skill counts: %s", e)

                categories = []
                for category, user in items:
                    categories.append(
                        SkillCategoryUserResponse.model_validate(
                            {
                                **self._to_category_model(
                                    category,
                                    access_grants=grants_map.get(category.id, []),
                                    db=db,
                                ).model_dump(),
                                "user": (
                                    UserModel.model_validate(user).model_dump()
                                    if user
                                    else None
                                ),
                                "skill_count": skill_counts.get(category.id, 0),
                            }
                        )
                    )

                return SkillCategoryListResponse(items=categories, total=total)
        except Exception as e:
            log.error("search_categories failed: %s\n%s", e, traceback.format_exc())
            return SkillCategoryListResponse(items=[], total=0)

    def check_access_by_user_id(
        self,
        id: str,
        user_id: str,
        permission: str = "write",
        db: Optional[Session] = None,
    ) -> bool:
        category = self.get_category_by_id(id, db=db)
        if not category:
            return False
        if category.user_id == user_id:
            return True
        user_group_ids = {
            group.id for group in Groups.get_groups_by_member_id(user_id, db=db)
        }
        return AccessGrants.has_access(
            user_id=user_id,
            resource_type="skill_category",
            resource_id=category.id,
            permission=permission,
            user_group_ids=user_group_ids,
            db=db,
        )

    def get_category_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[SkillCategoryModel]:
        try:
            with get_db_context(db) as db:
                category = db.query(SkillCategory).filter_by(id=id).first()
                return self._to_category_model(category, db=db) if category else None
        except Exception:
            return None

    def get_category_by_user_id_and_name(
        self, user_id: str, name: str, db: Optional[Session] = None
    ) -> Optional[SkillCategoryModel]:
        try:
            with get_db_context(db) as db:
                category = (
                    db.query(SkillCategory)
                    .filter_by(user_id=user_id, name=name)
                    .first()
                )
                return self._to_category_model(category, db=db) if category else None
        except Exception:
            return None

    def update_category_by_id(
        self,
        id: str,
        form_data: SkillCategoryForm,
        db: Optional[Session] = None,
    ) -> Optional[SkillCategoryModel]:
        try:
            with get_db_context(db) as db:
                db.query(SkillCategory).filter_by(id=id).update(
                    {
                        **form_data.model_dump(exclude={"access_grants"}),
                        "updated_at": int(time.time()),
                    }
                )
                db.commit()
                if form_data.access_grants is not None:
                    AccessGrants.set_access_grants(
                        "skill_category", id, form_data.access_grants, db=db
                    )
                return self.get_category_by_id(id=id, db=db)
        except Exception:
            log.exception("Failed to update skill category")
            return None

    def delete_category_by_id(self, id: str, db: Optional[Session] = None) -> bool:
        try:
            with get_db_context(db) as db:
                from open_webui.models.skills import Skill

                # Delete all skills belonging to this category (cascading).
                # Skills inherit access from the category, so removing the
                # category implies removing its skills as well.
                skill_ids = [
                    sid
                    for (sid,) in db.query(Skill.id)
                    .filter_by(category_id=id)
                    .all()
                ]
                for sid in skill_ids:
                    AccessGrants.revoke_all_access("skill", sid, db=db)
                db.query(Skill).filter_by(category_id=id).delete()
                db.commit()

                AccessGrants.revoke_all_access("skill_category", id, db=db)
                db.query(SkillCategory).filter_by(id=id).delete()
                db.commit()
                return True
        except Exception:
            log.exception("Failed to delete skill category")
            return False


SkillCategories = SkillCategoriesTable()
