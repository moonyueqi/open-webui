from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request

from sqlalchemy.orm import Session
from open_webui.internal.db import get_session
from open_webui.models.groups import Groups
from open_webui.models.skill_categories import (
    SkillCategories,
    SkillCategoryForm,
    SkillCategoryUserResponse,
    SkillCategoryAccessResponse,
    SkillCategoryAccessListResponse,
    SkillCategoryAccessGrantsForm,
    SkillCategoryModel,
)
from open_webui.models.skills import (
    Skill,
    SkillUserResponse,
    SkillListResponse,
    Skills,
)
from open_webui.models.users import User, UserModel, UserResponse
from open_webui.models.access_grants import AccessGrants
from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_verified_user
from open_webui.utils.access_control import (
    require_permission,
    filter_allowed_access_grants,
)
from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL

router = APIRouter()

PAGE_ITEM_COUNT = 30


############################
# GetSkillCategories
############################


@router.get("/", response_model=SkillCategoryAccessListResponse)
async def get_skill_categories(
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

    result = SkillCategories.search_categories(
        user.id, filter=filter, skip=skip, limit=limit, db=db
    )

    category_ids = [c.id for c in result.items]
    writable_ids = AccessGrants.get_accessible_resource_ids(
        user_id=user.id,
        resource_type="skill_category",
        resource_ids=category_ids,
        permission="write",
        user_group_ids=user_group_ids,
        db=db,
    )

    return SkillCategoryAccessListResponse(
        items=[
            SkillCategoryAccessResponse(
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
# CreateSkillCategory
############################


@router.post("/create", response_model=Optional[SkillCategoryModel])
async def create_skill_category(
    request: Request,
    form_data: SkillCategoryForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    require_permission(user, "workspace.skills", request, db=db)

    existing = SkillCategories.get_category_by_user_id_and_name(
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
        "sharing.public_skills",
    )

    category = SkillCategories.insert_new_category(user.id, form_data, db=db)

    if category:
        return category
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error creating category"),
        )


############################
# GetSkillCategoryById
############################


class SkillCategoryDetailResponse(SkillCategoryAccessResponse):
    pass


@router.get("/{id}", response_model=Optional[SkillCategoryDetailResponse])
async def get_skill_category_by_id(
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = SkillCategories.get_category_by_id(id=id, db=db)

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
            resource_type="skill_category",
            resource_id=category.id,
            permission="read",
            db=db,
        )
    ):
        return SkillCategoryDetailResponse(
            **category.model_dump(),
            write_access=(
                user.id == category.user_id
                or (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                or AccessGrants.has_access(
                    user_id=user.id,
                    resource_type="skill_category",
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
# UpdateSkillCategoryById
############################


@router.post("/{id}/update", response_model=Optional[SkillCategoryDetailResponse])
async def update_skill_category_by_id(
    request: Request,
    id: str,
    form_data: SkillCategoryForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = SkillCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        category.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="skill_category",
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
        existing = SkillCategories.get_category_by_user_id_and_name(
            user.id, form_data.name, db=db
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="已存在同名的分类，请使用其他名称。",
            )

    if category.user_id != user.id and user.role != "admin":
        form_data.access_grants = None
    else:
        form_data.access_grants = filter_allowed_access_grants(
            request.app.state.config.USER_PERMISSIONS,
            user.id,
            user.role,
            form_data.access_grants,
            "sharing.public_skills",
        )

    updated = SkillCategories.update_category_by_id(id, form_data, db=db)
    if updated:
        return SkillCategoryDetailResponse(
            **updated.model_dump(),
            write_access=True,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error updating category"),
        )


############################
# UpdateSkillCategoryAccess
############################


@router.post("/{id}/access/update", response_model=Optional[SkillCategoryDetailResponse])
async def update_skill_category_access(
    id: str,
    form_data: SkillCategoryAccessGrantsForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = SkillCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if category.user_id != user.id and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    AccessGrants.set_access_grants(
        "skill_category", id, form_data.access_grants, db=db
    )
    updated = SkillCategories.get_category_by_id(id=id, db=db)

    return SkillCategoryDetailResponse(
        **updated.model_dump(),
        write_access=True,
    )


############################
# GetSkillsByCategoryId
############################


@router.get("/{id}/skills", response_model=SkillListResponse)
async def get_skills_by_category_id(
    id: str,
    page: Optional[int] = 1,
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = SkillCategories.get_category_by_id(id=id, db=db)
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
            resource_type="skill_category",
            resource_id=category.id,
            permission="read",
            db=db,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    page = max(page, 1)
    limit = PAGE_ITEM_COUNT
    skip = (page - 1) * limit

    filter = {
        "category_id": id,
        "skip_access_filter": True,
    }
    if query:
        filter["query"] = query
    if view_option in ("created", "shared"):
        filter["view_option"] = view_option

    result = Skills.search_skills(
        user.id, filter=filter, skip=skip, limit=limit, db=db
    )

    return SkillListResponse(items=result.items, total=result.total)


############################
# DeleteSkillCategoryById
############################


@router.delete("/{id}/delete", response_model=bool)
async def delete_skill_category_by_id(
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = SkillCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        category.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="skill_category",
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

    result = SkillCategories.delete_category_by_id(id, db=db)
    if result:
        return True
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error deleting category"),
        )
