from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from sqlalchemy.orm import Session
from open_webui.internal.db import get_session
from open_webui.models.groups import Groups
from open_webui.models.prompt_categories import (
    PromptCategories,
    PromptCategoryForm,
    PromptCategoryUserResponse,
    PromptCategoryAccessResponse,
    PromptCategoryAccessListResponse,
    PromptCategoryAccessGrantsForm,
    PromptCategoryModel,
)
from open_webui.models.prompts import (
    Prompt,
    PromptModel,
    PromptUserResponse,
    PromptListResponse,
    Prompts,
)
from open_webui.models.users import User, UserModel, UserResponse
from open_webui.models.access_grants import AccessGrants
from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_verified_user
from open_webui.utils.access_control import require_permission, filter_allowed_access_grants
from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL

router = APIRouter()

PAGE_ITEM_COUNT = 30


############################
# GetPromptCategories
############################


@router.get("/", response_model=PromptCategoryAccessListResponse)
async def get_prompt_categories(
    page: Optional[int] = 1,
    view_option: Optional[str] = None,
    query: Optional[str] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    page = max(page, 1)
    limit = PAGE_ITEM_COUNT
    skip = (page - 1) * limit

    filter = {}
    groups = Groups.get_groups_by_member_id(user.id, db=db)
    user_group_ids = {group.id for group in groups}

    if not (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL):
        if groups:
            filter["group_ids"] = [group.id for group in groups]
        filter["user_id"] = user.id

    if view_option in ("created", "shared"):
        filter["view_option"] = view_option

    if query:
        filter["query"] = query

    result = PromptCategories.search_categories(
        user.id, filter=filter, skip=skip, limit=limit, db=db
    )

    category_ids = [c.id for c in result.items]
    writable_ids = AccessGrants.get_accessible_resource_ids(
        user_id=user.id,
        resource_type="prompt_category",
        resource_ids=category_ids,
        permission="write",
        user_group_ids=user_group_ids,
        db=db,
    )

    return PromptCategoryAccessListResponse(
        items=[
            PromptCategoryAccessResponse(
                **category.model_dump(),
                write_access=(
                    user.id == category.user_id
                    or (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or category.id in writable_ids
                ),
            )
            for category in result.items
        ],
        total=result.total,
    )


############################
# CreatePromptCategory
############################


@router.post("/create", response_model=Optional[PromptCategoryModel])
async def create_prompt_category(
    request: Request,
    form_data: PromptCategoryForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    require_permission(user, "workspace.prompts", request)

    existing = PromptCategories.get_category_by_user_id_and_name(
        user.id, form_data.name, db=db
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="已存在同名的分类，请使用其他名称。",
        )

    form_data.access_grants = filter_allowed_access_grants(
        request.app.state.config.USER_PERMISSIONS,
        user.id,
        user.role,
        form_data.access_grants,
        "sharing.public_prompts",
    )

    category = PromptCategories.insert_new_category(user.id, form_data, db=db)

    if category:
        return category
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error creating category"),
        )


############################
# GetPromptCategoryById
############################


class PromptCategoryDetailResponse(PromptCategoryAccessResponse):
    pass


@router.get("/{id}", response_model=Optional[PromptCategoryDetailResponse])
async def get_prompt_category_by_id(
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = PromptCategories.get_category_by_id(id=id, db=db)

    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        user.role == "admin"
        or category.user_id == user.id
        or AccessGrants.has_access(
            user_id=user.id,
            resource_type="prompt_category",
            resource_id=category.id,
            permission="read",
            db=db,
        )
    ):
        return PromptCategoryDetailResponse(
            **category.model_dump(),
            write_access=(
                user.id == category.user_id
                or (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                or AccessGrants.has_access(
                    user_id=user.id,
                    resource_type="prompt_category",
                    resource_id=category.id,
                    permission="write",
                    db=db,
                )
            ),
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )


############################
# UpdatePromptCategoryById
############################


@router.post("/{id}/update", response_model=Optional[PromptCategoryDetailResponse])
async def update_prompt_category_by_id(
    request: Request,
    id: str,
    form_data: PromptCategoryForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = PromptCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        category.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="prompt_category",
            resource_id=category.id,
            permission="write",
            db=db,
        )
        and user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if form_data.name != category.name:
        existing = PromptCategories.get_category_by_user_id_and_name(
            user.id, form_data.name, db=db
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="已存在同名的分类，请使用其他名称。",
            )

    # Only the owner / admin can change access grants. A `write` collaborator
    # may only edit content; ignore any access_grants pushed via the
    # content-update endpoint to prevent privilege escalation.
    if category.user_id != user.id and user.role != "admin":
        form_data.access_grants = None
    else:
        form_data.access_grants = filter_allowed_access_grants(
            request.app.state.config.USER_PERMISSIONS,
            user.id,
            user.role,
            form_data.access_grants,
            "sharing.public_prompts",
        )

    updated = PromptCategories.update_category_by_id(id, form_data, db=db)
    if updated:
        return PromptCategoryDetailResponse(
            **updated.model_dump(),
            write_access=True,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error updating category"),
        )


############################
# UpdatePromptCategoryAccess
############################


@router.post("/{id}/access/update", response_model=Optional[PromptCategoryDetailResponse])
async def update_prompt_category_access(
    id: str,
    form_data: PromptCategoryAccessGrantsForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = PromptCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    # Only the resource owner or an admin may modify access grants.
    # A user with `write` permission can edit content but cannot change who has access.
    if category.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    AccessGrants.set_access_grants(
        "prompt_category", id, form_data.access_grants, db=db
    )
    updated = PromptCategories.get_category_by_id(id=id, db=db)

    return PromptCategoryDetailResponse(
        **updated.model_dump(),
        write_access=True,
    )


############################
# GetPromptsByCategoryId
############################


@router.get("/{id}/prompts", response_model=PromptListResponse)
async def get_prompts_by_category_id(
    id: str,
    page: Optional[int] = 1,
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = PromptCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        user.role != "admin"
        and category.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="prompt_category",
            resource_id=category.id,
            permission="read",
            db=db,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    from open_webui.internal.db import get_db_context
    from open_webui.models.users import Users

    page = max(page, 1)
    limit = PAGE_ITEM_COUNT
    skip = (page - 1) * limit

    with get_db_context(db) as db:
        prompt_query = (
            db.query(Prompt, User)
            .outerjoin(User, User.id == Prompt.user_id)
            .filter(Prompt.category_id == id)
            .filter(Prompt.is_active == True)
        )

        if query:
            prompt_query = prompt_query.filter(
                Prompt.name.ilike(f"%{query}%")
            )
        if view_option == "created":
            prompt_query = prompt_query.filter(Prompt.user_id == user.id)
        elif view_option == "shared":
            prompt_query = prompt_query.filter(Prompt.user_id != user.id)

        prompt_query = prompt_query.order_by(Prompt.updated_at.desc())

        total = prompt_query.count()

        if skip:
            prompt_query = prompt_query.offset(skip)
        if limit:
            prompt_query = prompt_query.limit(limit)

        items = prompt_query.all()

        prompt_ids = [p.id for p, _ in items]
        grants_map = AccessGrants.get_grants_by_resources("prompt", prompt_ids, db=db)

        prompts = []
        for prompt, prompt_user in items:
            prompts.append(
                PromptUserResponse(
                    **Prompts._to_prompt_model(
                        prompt,
                        access_grants=grants_map.get(prompt.id, []),
                        db=db,
                    ).model_dump(),
                    user=(
                        UserResponse(**UserModel.model_validate(prompt_user).model_dump())
                        if prompt_user
                        else None
                    ),
                )
            )

        return PromptListResponse(items=prompts, total=total)


############################
# DeletePromptCategoryById
############################


@router.delete("/{id}/delete", response_model=bool)
async def delete_prompt_category_by_id(
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = PromptCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        category.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="prompt_category",
            resource_id=category.id,
            permission="write",
            db=db,
        )
        and user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    result = PromptCategories.delete_category_by_id(id, db=db)
    if result:
        return True
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error deleting category"),
        )
