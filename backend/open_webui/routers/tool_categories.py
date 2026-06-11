import time
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
from open_webui.models.tools import Tools, ToolAccessResponse
from open_webui.models.access_grants import AccessGrants
from open_webui.constants import ERROR_MESSAGES
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import filter_allowed_access_grants

router = APIRouter()

PAGE_ITEM_COUNT = 30


def _count_servers_in_category(request: Request, category_id: str) -> int:
    """统计挂在指定分类下、且已启用的工具服务器数量。"""
    connections = (
        getattr(request.app.state.config, "TOOL_SERVER_CONNECTIONS", None) or []
    )
    count = 0
    for conn in connections:
        conn_config = conn.get("config", {}) or {}
        if (
            conn_config.get("category_id") == category_id
            and conn_config.get("enable", True)
        ):
            count += 1
    return count


############################
# GetToolCategories
############################


@router.get("/", response_model=ToolCategoryAccessListResponse)
async def get_tool_categories(
    request: Request,
    page: Optional[int] = 1,
    query: Optional[str] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """
    返回全局工具分类目录。
    - 管理员：可见所有分类。
    - 普通用户：可见任意带有 `read` 授权（含 `user:*` 公开）的分类。

    `write_access` 表示"是否能在该分类下创建/修改/删除本地 Python 工具"。
    分类本身的属性（名称、描述、Access 授权）仅 admin 可修改，由路由
    dependency 直接拦截。
    """
    page = max(page, 1)
    limit = PAGE_ITEM_COUNT
    skip = (page - 1) * limit

    filter: dict = {}
    groups = Groups.get_groups_by_member_id(user.id, db=db)
    user_group_ids = {group.id for group in groups}

    if user.role != "admin":
        # 通过 user_id + group_ids 让 has_permission_filter 把
        # "user:* 公开" / "直接授权给我" / "授权给我所在组" 一并匹配。
        filter["user_id"] = user.id
        if groups:
            filter["group_ids"] = [group.id for group in groups]

    if query:
        filter["query"] = query

    result = ToolCategories.search_categories(
        user.id, filter=filter, skip=skip, limit=limit, db=db
    )

    category_ids = [c.id for c in result.items]
    writable_category_ids = (
        AccessGrants.get_accessible_resource_ids(
            user_id=user.id,
            resource_type="tool_category",
            resource_ids=category_ids,
            permission="write",
            user_group_ids=user_group_ids,
            db=db,
        )
        if (category_ids and user.role != "admin")
        else set()
    )

    # 把挂在每个分类下的工具服务器数量加到 tool_count 上
    # （tool_count 在 search_categories 里只数了本地 tool 表）
    items: list[ToolCategoryAccessResponse] = []
    for category in result.items:
        merged = category.model_dump()
        merged["tool_count"] = (
            (merged.get("tool_count") or 0)
            + _count_servers_in_category(request, category.id)
        )
        items.append(
            ToolCategoryAccessResponse(
                **merged,
                write_access=(
                    user.role == "admin" or category.id in writable_category_ids
                ),
            )
        )

    return ToolCategoryAccessListResponse(items=items, total=result.total)


############################
# CreateToolCategory
############################


@router.post("/create", response_model=Optional[ToolCategoryModel])
async def create_tool_category(
    request: Request,
    form_data: ToolCategoryForm,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    # 工具分类是全局目录，仅管理员可创建。
    existing = ToolCategories.get_category_by_name(form_data.name, db=db)
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
    request: Request,
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

    user_group_ids = {
        group.id for group in Groups.get_groups_by_member_id(user.id, db=db)
    }

    if user.role == "admin" or AccessGrants.has_access(
        user_id=user.id,
        resource_type="tool_category",
        resource_id=category.id,
        permission="read",
        user_group_ids=user_group_ids,
        db=db,
    ):
        # write_access 表示"是否能在此分类下创建/修改/删除本地 Python 工具"，
        # 即对本地工具的协作权限。分类本身的属性（名称、描述、访问授权）
        # 仅 admin 可修改，由路由 dependency 直接拦截。
        write_access = user.role == "admin" or AccessGrants.has_access(
            user_id=user.id,
            resource_type="tool_category",
            resource_id=category.id,
            permission="write",
            user_group_ids=user_group_ids,
            db=db,
        )

        # 计数补上挂在此分类下的工具服务器
        merged = category.model_dump()
        merged["tool_count"] = (
            (merged.get("tool_count") or 0)
            + _count_servers_in_category(request, category.id)
        )

        return ToolCategoryDetailResponse(
            **merged,
            write_access=write_access,
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
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    # 仅管理员可修改分类（包括名称、描述、访问授权）。
    category = ToolCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if form_data.name != category.name:
        existing = ToolCategories.get_category_by_name(form_data.name, db=db)
        if existing and existing.id != category.id:
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
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    category = ToolCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
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
    items: list[ToolAccessResponse]
    total: int


@router.get("/{id}/tools", response_model=ToolListResponse)
async def get_tools_by_category_id(
    request: Request,
    id: str,
    page: Optional[int] = 1,
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    """
    返回某个分类下的全部工具：
    - `tool` 表里 category_id 匹配的本地 Python 工具；
    - 以及挂在同一分类下的 OpenAPI / MCP 工具服务器（来源于
      `TOOL_SERVER_CONNECTIONS` 配置）。

    每条工具都会带上 `write_access` 标记：
    - 本地工具：admin / 工具所有者 / 分类被授予 write 权限的用户都为 True
    - 工具服务器：始终 False（仅管理员可在管理面板修改）
    """
    category = ToolCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    user_group_ids = {
        group.id for group in Groups.get_groups_by_member_id(user.id, db=db)
    }

    if user.role != "admin" and not AccessGrants.has_access(
        user_id=user.id,
        resource_type="tool_category",
        resource_id=category.id,
        permission="read",
        user_group_ids=user_group_ids,
        db=db,
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

    local_items, local_total = Tools.search_tools_by_category(
        user.id, filter=filter, skip=skip, limit=limit, db=db
    )

    # 仅当不是 admin 时才需要按分类的 write 授权计算单条工具的 write_access
    category_has_write = user.role == "admin" or AccessGrants.has_access(
        user_id=user.id,
        resource_type="tool_category",
        resource_id=category.id,
        permission="write",
        user_group_ids=user_group_ids,
        db=db,
    )

    local_access_items: list[ToolAccessResponse] = []
    for tool in local_items:
        has_write = (
            user.role == "admin"
            or tool.user_id == user.id
            or category_has_write
        )
        local_access_items.append(
            ToolAccessResponse(
                **tool.model_dump(),
                write_access=has_write,
            )
        )

    # 收集挂在此分类下的工具服务器
    server_items: list[ToolAccessResponse] = []
    connections = (
        getattr(request.app.state.config, "TOOL_SERVER_CONNECTIONS", None) or []
    )
    now = int(time.time())
    for conn in connections:
        conn_config = conn.get("config", {}) or {}
        if conn_config.get("category_id") != id:
            continue
        if not conn_config.get("enable", True):
            continue

        conn_type = conn.get("type", "openapi")
        info = conn.get("info", {}) or {}

        if conn_type == "mcp":
            server_id = f"server:mcp:{info.get('id', '')}"
            display_name = info.get("name") or "MCP Tool Server"
            description = info.get("description", "")
        else:
            server_id = f"server:{info.get('id', '')}"
            display_name = info.get("name") or conn.get("url") or "Tool Server"
            description = info.get("description", "")

        if query and query.lower() not in display_name.lower():
            continue

        server_items.append(
            ToolAccessResponse(
                **{
                    "id": server_id,
                    "user_id": server_id,
                    "name": display_name,
                    "meta": {"description": description},
                    "category_id": id,
                    "updated_at": now,
                    "created_at": now,
                    # 工具服务器永远不可在分类详情页内编辑/删除
                    "write_access": False,
                }
            )
        )

    return ToolListResponse(
        items=[*local_access_items, *server_items],
        total=local_total + len(server_items),
    )


############################
# DeleteToolCategoryById
############################


@router.delete("/{id}/delete", response_model=bool)
async def delete_tool_category_by_id(
    id: str,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    category = ToolCategories.get_category_by_id(id=id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    result = ToolCategories.delete_category_by_id(id, db=db)
    if result:
        return True
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT("Error deleting category"),
        )
