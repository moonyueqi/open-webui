from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel

from sqlalchemy.orm import Session
from open_webui.internal.db import get_session
from open_webui.models.groups import Groups
from open_webui.models.tool_categories import (
    ToolCategories,
    ToolCategoryForm,
    ToolCategoryAccessResponse,
    ToolCategoryAccessListResponse,
    ToolCategoryAccessGrantsForm,
    ToolCategoryModel,
)
from open_webui.models.tools import Tools, ToolUserResponse
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
# GetToolCategories
############################


@router.get("/", response_model=ToolCategoryAccessListResponse)
async def get_tool_categories(
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

    result = ToolCategories.search_categories(
        user.id, filter=filter, skip=skip, limit=limit, db=db
    )

    category_ids = [c.id for c in result.items]
    writable_ids = AccessGrants.get_accessible_resource_ids(
        user_id=user.id,
        resource_type="tool_category",
        resource_ids=category_ids,
        permission="write",
        user_group_ids=user_group_ids,
        db=db,
    )

    return ToolCategoryAccessListResponse(
        items=[
            ToolCategoryAccessResponse(
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
# CreateToolCategory
############################


@router.post("/create", response_model=Optional[ToolCategoryModel])
async def create_tool_category(
    request: Request,
    form_data: ToolCategoryForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    require_permission(user, "workspace.tools", request, db=db)

    existing = ToolCategories.get_category_by_user_id_and_name(
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
        "sharing.public_tools",
    )

    category = ToolCategories.insert_new_category(user.id, form_data, db=db)

    if category:
        return category
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error creating category"),
        )


############################
# GetToolCategoryById
############################


class ToolCategoryDetailResponse(ToolCategoryAccessResponse):
    pass


@router.get("/{id}", response_model=Optional[ToolCategoryDetailResponse])
async def get_tool_category_by_id(
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = ToolCategories.get_category_by_id(id=id, db=db)

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
            resource_type="tool_category",
            resource_id=category.id,
            permission="read",
            db=db,
        )
    ):
        return ToolCategoryDetailResponse(
            **category.model_dump(),
            write_access=(
                user.id == category.user_id
                or (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                or AccessGrants.has_access(
                    user_id=user.id,
                    resource_type="tool_category",
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
# UpdateToolCategoryById
############################


@router.post("/{id}/update", response_model=Optional[ToolCategoryDetailResponse])
async def update_tool_category_by_id(
    request: Request,
    id: str,
    form_data: ToolCategoryForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = ToolCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        category.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="tool_category",
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
        existing = ToolCategories.get_category_by_user_id_and_name(
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
            "sharing.public_tools",
        )

    updated = ToolCategories.update_category_by_id(id, form_data, db=db)
    if updated:
        return ToolCategoryDetailResponse(
            **updated.model_dump(),
            write_access=True,
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error updating category"),
        )


############################
# UpdateToolCategoryAccess
############################


@router.post("/{id}/access/update", response_model=Optional[ToolCategoryDetailResponse])
async def update_tool_category_access(
    id: str,
    form_data: ToolCategoryAccessGrantsForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = ToolCategories.get_category_by_id(id=id, db=db)
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
        "tool_category", id, form_data.access_grants, db=db
    )
    updated = ToolCategories.get_category_by_id(id=id, db=db)

    return ToolCategoryDetailResponse(
        **updated.model_dump(),
        write_access=True,
    )


############################
# GetToolsByCategoryId
############################


class ToolListResponse(BaseModel):
    items: list[ToolUserResponse]
    total: int


@router.get("/{id}/tools", response_model=ToolListResponse)
async def get_tools_by_category_id(
    id: str,
    page: Optional[int] = 1,
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = ToolCategories.get_category_by_id(id=id, db=db)
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
            resource_type="tool_category",
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

    filter = {"category_id": id}
    if query:
        filter["query"] = query
    if view_option in ("created", "shared"):
        filter["view_option"] = view_option

    items, total = Tools.search_tools_by_category(
        user.id, filter=filter, skip=skip, limit=limit, db=db
    )

    return ToolListResponse(items=items, total=total)


############################
# DeleteToolCategoryById
############################


@router.delete("/{id}/delete", response_model=bool)
async def delete_tool_category_by_id(
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    category = ToolCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        category.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="tool_category",
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

    result = ToolCategories.delete_category_by_id(id, db=db)
    if result:
        return True
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error deleting category"),
        )
