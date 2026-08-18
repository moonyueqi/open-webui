import logging
from pathlib import Path
from typing import Optional
import time
import re
import aiohttp
from open_webui.env import AIOHTTP_CLIENT_TIMEOUT
from open_webui.models.groups import Groups
from pydantic import BaseModel, HttpUrl
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from open_webui.internal.db import get_session


from open_webui.models.oauth_sessions import OAuthSessions
from open_webui.models.tools import (
    ToolForm,
    ToolModel,
    ToolResponse,
    ToolUserResponse,
    ToolAccessResponse,
    Tools,
)
from open_webui.models.access_grants import AccessGrants
from open_webui.models.tool_categories import ToolCategories
from open_webui.utils.plugin import (
    load_tool_module_by_id,
    replace_imports,
    get_tool_module_from_cache,
    resolve_valves_schema_options,
)
from open_webui.utils.tools import get_tool_specs
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import require_permission
from open_webui.utils.tools import get_tool_servers

from open_webui.config import CACHE_DIR, BYPASS_ADMIN_ACCESS_CONTROL
from open_webui.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)


router = APIRouter()


def _user_has_tool_access(
    user,
    tool,
    permission: str,
    db: Session,
    user_group_ids: Optional[set] = None,
) -> bool:
    """Check whether a user has the given permission on a tool.

    Access is primarily inherited from the parent tool category. A user is
    granted access if they are the owner of the tool, an admin, or have the
    corresponding access_grant on the tool's parent category.

    As a fallback (mainly for tools left without a category_id, e.g. right
    after upgrading before the backfill migration has run), we also honor
    any legacy tool-level access_grant (resource_type="tool") that predates
    the category feature.
    """
    if user.role == "admin":
        return True
    if tool.user_id == user.id:
        return True
    if getattr(tool, "category_id", None) and AccessGrants.has_access(
        user_id=user.id,
        resource_type="tool_category",
        resource_id=tool.category_id,
        permission=permission,
        user_group_ids=user_group_ids,
        db=db,
    ):
        return True
    if AccessGrants.has_access(
        user_id=user.id,
        resource_type="tool",
        resource_id=tool.id,
        permission=permission,
        user_group_ids=user_group_ids,
        db=db,
    ):
        return True
    return False


def get_tool_module(request, tool_id, load_from_db=True):
    """
    Get the tool module by its ID.
    """
    tool_module, _ = get_tool_module_from_cache(request, tool_id, load_from_db)
    return tool_module


############################
# GetTools
############################


@router.get("/", response_model=list[ToolUserResponse])
async def get_tools(
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    tools = []

    # Local Tools
    for tool in Tools.get_tools(defer_content=True, db=db):
        tool_module = (
            request.app.state.TOOLS.get(tool.id)
            if hasattr(request.app.state, "TOOLS")
            else None
        )
        tools.append(
            ToolUserResponse(
                **{
                    **tool.model_dump(),
                    "has_user_valves": (
                        hasattr(tool_module, "UserValves") if tool_module else False
                    ),
                }
            )
        )

    # OpenAPI Tool Servers
    # 工具服务器的可见性统一通过其 config.category_id 关联的工具分类继承：
    #   - 设置了 category_id → 继承分类的 read 授权
    #   - 未设置 category_id → 默认对所有用户可读（向后兼容）
    # 写操作（修改 URL/鉴权/类别等）始终仅管理员可执行，由 configs 路由层兜底。
    server_category_map: dict[str, Optional[str]] = {}
    for server in await get_tool_servers(request):
        connection = request.app.state.config.TOOL_SERVER_CONNECTIONS[
            server.get("idx", 0)
        ]
        server_config = connection.get("config", {})

        server_id = f"server:{server.get('id')}"
        server_category_map[server_id] = server_config.get("category_id")

        tools.append(
            ToolUserResponse(
                **{
                    "id": server_id,
                    "user_id": server_id,
                    "name": server.get("openapi", {})
                    .get("info", {})
                    .get("title", "Tool Server"),
                    "meta": {
                        "description": server.get("openapi", {})
                        .get("info", {})
                        .get("description", ""),
                    },
                    "category_id": server_config.get("category_id"),
                    "updated_at": int(time.time()),
                    "created_at": int(time.time()),
                }
            )
        )

    # MCP Tool Servers
    for server in request.app.state.config.TOOL_SERVER_CONNECTIONS:
        if server.get("type", "openapi") == "mcp" and server.get("config", {}).get(
            "enable"
        ):
            server_id = server.get("info", {}).get("id")
            auth_type = server.get("auth_type", "none")

            session_token = None
            if auth_type == "oauth_2.1":
                splits = server_id.split(":")
                server_id = splits[-1] if len(splits) > 1 else server_id

                session_token = (
                    await request.app.state.oauth_client_manager.get_oauth_token(
                        user.id, f"mcp:{server_id}"
                    )
                )

            server_config = server.get("config", {})

            tool_id = f"server:mcp:{server.get('info', {}).get('id')}"
            server_category_map[tool_id] = server_config.get("category_id")

            tools.append(
                ToolUserResponse(
                    **{
                        "id": tool_id,
                        "user_id": tool_id,
                        "name": server.get("info", {}).get("name", "MCP Tool Server"),
                        "meta": {
                            "description": server.get("info", {}).get(
                                "description", ""
                            ),
                        },
                        "category_id": server_config.get("category_id"),
                        "updated_at": int(time.time()),
                        "created_at": int(time.time()),
                        **(
                            {
                                "authenticated": session_token is not None,
                            }
                            if auth_type == "oauth_2.1"
                            else {}
                        ),
                    }
                )
            )

    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        return tools

    user_group_ids = {
        group.id for group in Groups.get_groups_by_member_id(user.id, db=db)
    }

    def _server_visible(tool_id: str) -> bool:
        cat_id = server_category_map.get(tool_id)
        if not cat_id:
            # 未挂分类的工具服务器，默认对所有人可见（兜底）
            return True
        return AccessGrants.has_access(
            user_id=user.id,
            resource_type="tool_category",
            resource_id=cat_id,
            permission="read",
            user_group_ids=user_group_ids,
            db=db,
        )

    tools = [
        tool
        for tool in tools
        if (
            _server_visible(str(tool.id))
            if str(tool.id).startswith("server:")
            else _user_has_tool_access(
                user, tool, "read", db, user_group_ids=user_group_ids
            )
        )
    ]
    return tools


############################
# GetToolList
############################


@router.get("/list", response_model=list[ToolAccessResponse])
async def get_tool_list(
    user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        tools = Tools.get_tools(defer_content=True, db=db)
    else:
        tools = Tools.get_tools_by_user_id(user.id, "read", defer_content=True, db=db)

    user_group_ids = {
        group.id for group in Groups.get_groups_by_member_id(user.id, db=db)
    }

    # Batch-fetch writable categories so write access inherited from the
    # parent category is respected in the list view.
    category_ids = list({tool.category_id for tool in tools if tool.category_id})
    writable_category_ids = (
        AccessGrants.get_accessible_resource_ids(
            user_id=user.id,
            resource_type="tool_category",
            resource_ids=category_ids,
            permission="write",
            user_group_ids=user_group_ids,
            db=db,
        )
        if category_ids
        else set()
    )

    result = []
    for tool in tools:
        has_write = (
            (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
            or user.id == tool.user_id
            or (
                bool(tool.category_id)
                and tool.category_id in writable_category_ids
            )
        )
        result.append(
            ToolAccessResponse(
                **tool.model_dump(),
                write_access=has_write,
            )
        )
    return result


############################
# LoadFunctionFromLink
############################


class LoadUrlForm(BaseModel):
    url: HttpUrl


def github_url_to_raw_url(url: str) -> str:
    # Handle 'tree' (folder) URLs (add main.py at the end)
    m1 = re.match(r"https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)/(.*)", url)
    if m1:
        org, repo, branch, path = m1.groups()
        return f"https://raw.githubusercontent.com/{org}/{repo}/refs/heads/{branch}/{path.rstrip('/')}/main.py"

    # Handle 'blob' (file) URLs
    m2 = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)/(.*)", url)
    if m2:
        org, repo, branch, path = m2.groups()
        return (
            f"https://raw.githubusercontent.com/{org}/{repo}/refs/heads/{branch}/{path}"
        )

    # No match; return as-is
    return url


@router.post("/load/url", response_model=Optional[dict])
async def load_tool_from_url(
    request: Request, form_data: LoadUrlForm, user=Depends(get_admin_user)
):
    # NOTE: This is NOT a SSRF vulnerability:
    # This endpoint is admin-only (see get_admin_user), meant for *trusted* internal use,
    # and does NOT accept untrusted user input. Access is enforced by authentication.

    url = str(form_data.url)
    if not url:
        raise HTTPException(status_code=400, detail="请输入有效的 URL 地址。")

    url = github_url_to_raw_url(url)
    url_parts = url.rstrip("/").split("/")

    file_name = url_parts[-1]
    tool_name = (
        file_name[:-3]
        if (
            file_name.endswith(".py")
            and (not file_name.startswith(("main.py", "index.py", "__init__.py")))
        )
        else url_parts[-2] if len(url_parts) > 1 else "function"
    )

    try:
        async with aiohttp.ClientSession(
            trust_env=True, timeout=aiohttp.ClientTimeout(total=AIOHTTP_CLIENT_TIMEOUT)
        ) as session:
            async with session.get(
                url, headers={"Content-Type": "application/json"}
            ) as resp:
                if resp.status != 200:
                    raise HTTPException(
                        status_code=resp.status,
                        detail="获取工具失败，请检查 URL 是否正确。",
                    )
                data = await resp.text()
                if not data:
                    raise HTTPException(
                        status_code=400, detail="未从该 URL 获取到任何数据。"
                    )
        return {
            "name": tool_name,
            "content": data,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error importing tool: {e}")


############################
# ExportTools
############################


@router.get("/export", response_model=list[ToolModel])
async def export_tools(
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    require_permission(user, "workspace.tools_export", request, db=db)

    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        return Tools.get_tools(db=db)
    else:
        return Tools.get_tools_by_user_id(user.id, "read", db=db)


############################
# CreateNewTools
############################


@router.post("/create", response_model=Optional[ToolResponse])
async def create_new_tools(
    request: Request,
    form_data: ToolForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    require_permission(user, ["workspace.tools", "workspace.tools_import"], request, db=db)

    # A category is required: tools inherit access from their category.
    if not form_data.category_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先选择一个分类。",
        )

    category = ToolCategories.get_category_by_id(form_data.category_id, db=db)
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        user.role != "admin"
        and category.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="tool_category",
            resource_id=category.id,
            permission="write",
            db=db,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if not form_data.id.isidentifier():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ID 只允许使用字母、数字和下划线，且不能以数字开头",
        )

    form_data.id = form_data.id.lower()

    # Tools no longer carry their own access grants — access is inherited
    # from the parent category. Always clear any payload to be safe.
    form_data.access_grants = []

    existing_by_name = Tools.get_tool_by_name(form_data.name, db=db)
    if existing_by_name is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.TOOL_NAME_TAKEN,
        )

    tools = Tools.get_tool_by_id(form_data.id, db=db)
    if tools is None:
        try:
            form_data.content = replace_imports(form_data.content)
            tool_module, frontmatter = load_tool_module_by_id(
                form_data.id, content=form_data.content
            )
            form_data.meta.manifest = frontmatter

            TOOLS = request.app.state.TOOLS
            TOOLS[form_data.id] = tool_module

            specs = get_tool_specs(TOOLS[form_data.id])
            tools = Tools.insert_new_tool(user.id, form_data, specs, db=db)

            tool_cache_dir = CACHE_DIR / "tools" / form_data.id
            tool_cache_dir.mkdir(parents=True, exist_ok=True)

            if tools:
                return tools
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error creating tools"),
                )
        except Exception as e:
            log.exception(f"Failed to load the tool by id {form_data.id}: {e}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT(str(e)),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ID_TAKEN,
        )


############################
# GetToolsById
############################


@router.get("/id/{id}", response_model=Optional[ToolAccessResponse])
async def get_tools_by_id(
    id: str, user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    tools = Tools.get_tool_by_id(id, db=db)

    if tools:
        if _user_has_tool_access(user, tools, "read", db):
            return ToolAccessResponse(
                **tools.model_dump(),
                write_access=(
                    (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or _user_has_tool_access(user, tools, "write", db)
                ),
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdateToolsById
############################


@router.post("/id/{id}/update", response_model=Optional[ToolModel])
async def update_tools_by_id(
    request: Request,
    id: str,
    form_data: ToolForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    tools = Tools.get_tool_by_id(id, db=db)
    if not tools:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not _user_has_tool_access(user, tools, "write", db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    # If the caller wants to move the tool to another category, verify they
    # also have write permission on the destination category.
    new_category_id = form_data.category_id
    if new_category_id and new_category_id != tools.category_id:
        new_category = ToolCategories.get_category_by_id(new_category_id, db=db)
        if not new_category:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.NOT_FOUND,
            )
        if (
            user.role != "admin"
            and new_category.user_id != user.id
            and not AccessGrants.has_access(
                user_id=user.id,
                resource_type="tool_category",
                resource_id=new_category.id,
                permission="write",
                db=db,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )

    existing_by_name = Tools.get_tool_by_name(form_data.name, db=db)
    if existing_by_name is not None and existing_by_name.id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.TOOL_NAME_TAKEN,
        )

    try:
        form_data.content = replace_imports(form_data.content)
        tool_module, frontmatter = load_tool_module_by_id(id, content=form_data.content)
        form_data.meta.manifest = frontmatter

        TOOLS = request.app.state.TOOLS
        TOOLS[id] = tool_module

        specs = get_tool_specs(TOOLS[id])

        # Tools no longer carry independent access grants; always drop the
        # field from the update payload so callers cannot bypass the
        # category-inherited model.
        exclude_fields = {"id", "access_grants"}

        updated = {
            **form_data.model_dump(exclude=exclude_fields),
            "specs": specs,
        }

        log.debug(updated)
        tools = Tools.update_tool_by_id(id, updated, db=db)

        if tools:
            return tools
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error updating tools"),
            )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(str(e)),
        )


############################
# DeleteToolsById
############################


@router.delete("/id/{id}/delete", response_model=bool)
async def delete_tools_by_id(
    request: Request,
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    tools = Tools.get_tool_by_id(id, db=db)
    if not tools:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not _user_has_tool_access(user, tools, "write", db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    result = Tools.delete_tool_by_id(id, db=db)
    if result:
        TOOLS = request.app.state.TOOLS
        if id in TOOLS:
            del TOOLS[id]

    return result


############################
# GetToolValves
############################


@router.get("/id/{id}/valves", response_model=Optional[dict])
async def get_tools_valves_by_id(
    id: str, user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    tools = Tools.get_tool_by_id(id, db=db)
    if tools:
        try:
            valves = Tools.get_tool_valves_by_id(id, db=db)
            return valves
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT(str(e)),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# GetToolValvesSpec
############################


@router.get("/id/{id}/valves/spec", response_model=Optional[dict])
async def get_tools_valves_spec_by_id(
    request: Request,
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    tools = Tools.get_tool_by_id(id, db=db)
    if tools:
        if id in request.app.state.TOOLS:
            tools_module = request.app.state.TOOLS[id]
        else:
            tools_module, _ = load_tool_module_by_id(id)
            request.app.state.TOOLS[id] = tools_module

        if hasattr(tools_module, "Valves"):
            Valves = tools_module.Valves
            schema = Valves.schema()
            # Resolve dynamic options for select dropdowns
            schema = resolve_valves_schema_options(Valves, schema, user)
            return schema
        return None
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdateToolValves
############################


@router.post("/id/{id}/valves/update", response_model=Optional[dict])
async def update_tools_valves_by_id(
    request: Request,
    id: str,
    form_data: dict,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    tools = Tools.get_tool_by_id(id, db=db)
    if not tools:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not _user_has_tool_access(user, tools, "write", db):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    if id in request.app.state.TOOLS:
        tools_module = request.app.state.TOOLS[id]
    else:
        tools_module, _ = load_tool_module_by_id(id)
        request.app.state.TOOLS[id] = tools_module

    if not hasattr(tools_module, "Valves"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
    Valves = tools_module.Valves

    try:
        form_data = {k: v for k, v in form_data.items() if v is not None}
        valves = Valves(**form_data)
        valves_dict = valves.model_dump(exclude_unset=True)
        Tools.update_tool_valves_by_id(id, valves_dict, db=db)
        return valves_dict
    except Exception as e:
        log.exception(f"Failed to update tool valves by id {id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(str(e)),
        )


############################
# ToolUserValves
############################


@router.get("/id/{id}/valves/user", response_model=Optional[dict])
async def get_tools_user_valves_by_id(
    id: str, user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    tools = Tools.get_tool_by_id(id, db=db)
    if tools:
        try:
            user_valves = Tools.get_user_valves_by_id_and_user_id(id, user.id, db=db)
            return user_valves
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT(str(e)),
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.get("/id/{id}/valves/user/spec", response_model=Optional[dict])
async def get_tools_user_valves_spec_by_id(
    request: Request,
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    tools = Tools.get_tool_by_id(id, db=db)
    if tools:
        if id in request.app.state.TOOLS:
            tools_module = request.app.state.TOOLS[id]
        else:
            tools_module, _ = load_tool_module_by_id(id)
            request.app.state.TOOLS[id] = tools_module

        if hasattr(tools_module, "UserValves"):
            UserValves = tools_module.UserValves
            schema = UserValves.schema()
            # Resolve dynamic options for select dropdowns
            schema = resolve_valves_schema_options(UserValves, schema, user)
            return schema
        return None
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


@router.post("/id/{id}/valves/user/update", response_model=Optional[dict])
async def update_tools_user_valves_by_id(
    request: Request,
    id: str,
    form_data: dict,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    tools = Tools.get_tool_by_id(id, db=db)

    if tools:
        if id in request.app.state.TOOLS:
            tools_module = request.app.state.TOOLS[id]
        else:
            tools_module, _ = load_tool_module_by_id(id)
            request.app.state.TOOLS[id] = tools_module

        if hasattr(tools_module, "UserValves"):
            UserValves = tools_module.UserValves

            try:
                form_data = {k: v for k, v in form_data.items() if v is not None}
                user_valves = UserValves(**form_data)
                user_valves_dict = user_valves.model_dump(exclude_unset=True)
                Tools.update_user_valves_by_id_and_user_id(
                    id, user.id, user_valves_dict, db=db
                )
                return user_valves_dict
            except Exception as e:
                log.exception(f"Failed to update user valves by id {id}: {e}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT(str(e)),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.NOT_FOUND,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )
