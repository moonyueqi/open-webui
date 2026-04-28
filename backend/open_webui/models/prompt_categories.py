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
# PromptCategory DB Schema
####################


class PromptCategory(Base):
    __tablename__ = "prompt_category"

    id = Column(Text, unique=True, primary_key=True)
    user_id = Column(Text)
    name = Column(Text)
    description = Column(Text, nullable=True)
    meta = Column(JSON, nullable=True)
    created_at = Column(BigInteger, nullable=True)
    updated_at = Column(BigInteger, nullable=True)


class PromptCategoryModel(BaseModel):
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


class PromptCategoryUserResponse(PromptCategoryModel):
    user: Optional[UserResponse] = None
    prompt_count: Optional[int] = 0


class PromptCategoryAccessResponse(PromptCategoryUserResponse):
    write_access: Optional[bool] = False


class PromptCategoryForm(BaseModel):
    name: str
    description: Optional[str] = None
    access_grants: Optional[list[dict]] = None


class PromptCategoryListResponse(BaseModel):
    items: list[PromptCategoryUserResponse]
    total: int


class PromptCategoryAccessListResponse(BaseModel):
    items: list[PromptCategoryAccessResponse]
    total: int


class PromptCategoryAccessGrantsForm(BaseModel):
    access_grants: list[dict]


####################
# Table Operations
####################


class PromptCategoriesTable:
    def _get_access_grants(
        self, category_id: str, db: Optional[Session] = None
    ) -> list[AccessGrantModel]:
        return AccessGrants.get_grants_by_resource(
            "prompt_category", category_id, db=db
        )

    def _to_category_model(
        self,
        category: PromptCategory,
        access_grants: Optional[list[AccessGrantModel]] = None,
        db: Optional[Session] = None,
    ) -> PromptCategoryModel:
        category_data = PromptCategoryModel.model_validate(category).model_dump(
            exclude={"access_grants"}
        )
        category_data["access_grants"] = (
            access_grants
            if access_grants is not None
            else self._get_access_grants(category_data["id"], db=db)
        )
        return PromptCategoryModel.model_validate(category_data)

    def insert_new_category(
        self, user_id: str, form_data: PromptCategoryForm, db: Optional[Session] = None
    ) -> Optional[PromptCategoryModel]:
        with get_db_context(db) as db:
            category = PromptCategoryModel(
                **{
                    **form_data.model_dump(exclude={"access_grants"}),
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "created_at": int(time.time()),
                    "updated_at": int(time.time()),
                    "access_grants": [],
                }
            )

            try:
                result = PromptCategory(
                    **category.model_dump(exclude={"access_grants"})
                )
                db.add(result)
                db.commit()
                db.refresh(result)
                AccessGrants.set_access_grants(
                    "prompt_category", result.id, form_data.access_grants, db=db
                )
                if result:
                    return self._to_category_model(result, db=db)
                else:
                    return None
            except Exception:
                return None

    def get_categories(
        self, skip: int = 0, limit: int = 30, db: Optional[Session] = None
    ) -> list[PromptCategoryUserResponse]:
        with get_db_context(db) as db:
            all_categories = (
                db.query(PromptCategory)
                .order_by(PromptCategory.updated_at.desc())
                .all()
            )
            user_ids = list(set(c.user_id for c in all_categories))
            category_ids = [c.id for c in all_categories]

            users = Users.get_users_by_user_ids(user_ids, db=db) if user_ids else []
            users_dict = {user.id: user for user in users}
            grants_map = AccessGrants.get_grants_by_resources(
                "prompt_category", category_ids, db=db
            )

            categories = []
            for category in all_categories:
                user = users_dict.get(category.user_id)
                categories.append(
                    PromptCategoryUserResponse.model_validate(
                        {
                            **self._to_category_model(
                                category,
                                access_grants=grants_map.get(category.id, []),
                                db=db,
                            ).model_dump(),
                            "user": user.model_dump() if user else None,
                        }
                    )
                )
            return categories

    def search_categories(
        self,
        user_id: str,
        filter: dict,
        skip: int = 0,
        limit: int = 30,
        db: Optional[Session] = None,
    ) -> PromptCategoryListResponse:
        try:
            with get_db_context(db) as db:
                from open_webui.models.prompts import Prompt as PromptTable
                from sqlalchemy import func

                query = db.query(PromptCategory, User).outerjoin(
                    User, User.id == PromptCategory.user_id
                )

                if filter:
                    query_key = filter.get("query")
                    if query_key:
                        query = query.filter(
                            PromptCategory.name.ilike(f"%{query_key}%")
                        )

                    view_option = filter.get("view_option")
                    if view_option == "created":
                        query = query.filter(PromptCategory.user_id == user_id)
                    elif view_option == "shared":
                        query = query.filter(PromptCategory.user_id != user_id)

                    query = AccessGrants.has_permission_filter(
                        db=db,
                        query=query,
                        DocumentModel=PromptCategory,
                        filter=filter,
                        resource_type="prompt_category",
                        permission="read",
                    )

                query = query.order_by(
                    PromptCategory.updated_at.desc(), PromptCategory.id.asc()
                )

                total = query.count()
                if skip:
                    query = query.offset(skip)
                if limit:
                    query = query.limit(limit)

                items = query.all()

                category_ids = [c.id for c, _ in items]
                grants_map = AccessGrants.get_grants_by_resources(
                    "prompt_category", category_ids, db=db
                )

                prompt_counts = {}
                if category_ids:
                    try:
                        count_results = (
                            db.query(
                                PromptTable.category_id,
                                func.count(PromptTable.id),
                            )
                            .filter(
                                PromptTable.category_id.in_(category_ids),
                                PromptTable.is_active == True,
                            )
                            .group_by(PromptTable.category_id)
                            .all()
                        )
                        prompt_counts = {cid: cnt for cid, cnt in count_results}
                    except Exception as e:
                        log.warning("Failed to get prompt counts: %s", e)

                categories = []
                for category, user in items:
                    categories.append(
                        PromptCategoryUserResponse.model_validate(
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
                                "prompt_count": prompt_counts.get(category.id, 0),
                            }
                        )
                    )

                return PromptCategoryListResponse(items=categories, total=total)
        except Exception as e:
            log.error("search_categories failed: %s\n%s", e, traceback.format_exc())
            return PromptCategoryListResponse(items=[], total=0)

    def check_access_by_user_id(
        self, id: str, user_id: str, permission: str = "write", db: Optional[Session] = None
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
            resource_type="prompt_category",
            resource_id=category.id,
            permission=permission,
            user_group_ids=user_group_ids,
            db=db,
        )

    def get_category_by_id(
        self, id: str, db: Optional[Session] = None
    ) -> Optional[PromptCategoryModel]:
        try:
            with get_db_context(db) as db:
                category = db.query(PromptCategory).filter_by(id=id).first()
                return self._to_category_model(category, db=db) if category else None
        except Exception:
            return None

    def get_category_by_user_id_and_name(
        self, user_id: str, name: str, db: Optional[Session] = None
    ) -> Optional[PromptCategoryModel]:
        try:
            with get_db_context(db) as db:
                category = (
                    db.query(PromptCategory)
                    .filter_by(user_id=user_id, name=name)
                    .first()
                )
                return self._to_category_model(category, db=db) if category else None
        except Exception:
            return None

    def update_category_by_id(
        self,
        id: str,
        form_data: PromptCategoryForm,
        db: Optional[Session] = None,
    ) -> Optional[PromptCategoryModel]:
        try:
            with get_db_context(db) as db:
                db.query(PromptCategory).filter_by(id=id).update(
                    {
                        **form_data.model_dump(exclude={"access_grants"}),
                        "updated_at": int(time.time()),
                    }
                )
                db.commit()
                if form_data.access_grants is not None:
                    AccessGrants.set_access_grants(
                        "prompt_category", id, form_data.access_grants, db=db
                    )
                return self.get_category_by_id(id=id, db=db)
        except Exception:
            return None

    def delete_category_by_id(self, id: str, db: Optional[Session] = None) -> bool:
        try:
            with get_db_context(db) as db:
                from open_webui.models.prompts import Prompt

                db.query(Prompt).filter_by(category_id=id).update(
                    {"category_id": None}
                )
                db.commit()

                AccessGrants.revoke_all_access("prompt_category", id, db=db)
                db.query(PromptCategory).filter_by(id=id).delete()
                db.commit()
                return True
        except Exception:
            return False


PromptCategories = PromptCategoriesTable()
