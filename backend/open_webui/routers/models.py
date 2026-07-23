from typing import Optional
import io
import base64
import json
import asyncio
import logging

from open_webui.models.groups import Groups
from open_webui.models.models import (
    ModelForm,
    ModelMeta,
    ModelModel,
    ModelParams,
    ModelResponse,
    ModelListResponse,
    ModelAccessListResponse,
    ModelAccessResponse,
    Models,
)
from open_webui.models.access_grants import AccessGrants

from pydantic import BaseModel
from open_webui.constants import ERROR_MESSAGES
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Request,
    status,
    Response,
)
from fastapi.responses import FileResponse, StreamingResponse


from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import require_permission, filter_allowed_access_grants
from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL, STATIC_DIR
from open_webui.internal.db import get_session
from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

router = APIRouter()


def is_valid_model_id(model_id: str) -> bool:
    return model_id and len(model_id) <= 256


###########################
# GetModels
###########################


PAGE_ITEM_COUNT = 30


@router.get(
    "/list", response_model=ModelAccessListResponse
)  # do NOT use "/" as path, conflicts with main.py
async def get_models(
    query: Optional[str] = None,
    view_option: Optional[str] = None,
    tag: Optional[str] = None,
    order_by: Optional[str] = None,
    direction: Optional[str] = None,
    page: Optional[int] = 1,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):

    limit = PAGE_ITEM_COUNT

    page = max(1, page)
    skip = (page - 1) * limit

    filter = {}
    if query:
        filter["query"] = query
    if view_option:
        filter["view_option"] = view_option
    if tag:
        filter["tag"] = tag
    if order_by:
        filter["order_by"] = order_by
    if direction:
        filter["direction"] = direction

    # Pre-fetch user group IDs once - used for both filter and write_access check
    groups = Groups.get_groups_by_member_id(user.id, db=db)
    user_group_ids = {group.id for group in groups}

    if not user.role == "admin" or not BYPASS_ADMIN_ACCESS_CONTROL:
        if groups:
            filter["group_ids"] = [group.id for group in groups]

        filter["user_id"] = user.id

    result = Models.search_models(user.id, filter=filter, skip=skip, limit=limit, db=db)

    # Batch-fetch writable model IDs in a single query instead of N has_access calls
    model_ids = [model.id for model in result.items]
    writable_model_ids = AccessGrants.get_accessible_resource_ids(
        user_id=user.id,
        resource_type="model",
        resource_ids=model_ids,
        permission="write",
        user_group_ids=user_group_ids,
        db=db,
    )

    return ModelAccessListResponse(
        items=[
            ModelAccessResponse(
                **model.model_dump(),
                write_access=(
                    (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or user.id == model.user_id
                    or model.id in writable_model_ids
                ),
            )
            for model in result.items
        ],
        total=result.total,
    )


###########################
# GetBaseModels
###########################


@router.get("/base", response_model=list[ModelResponse])
async def get_base_models(
    user=Depends(get_admin_user), db: Session = Depends(get_session)
):
    return Models.get_base_models(db=db)


###########################
# GetModelTags
###########################


@router.get("/tags", response_model=list[str])
async def get_model_tags(
    user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        models = Models.get_models(db=db)
    else:
        models = Models.get_models_by_user_id(user.id, db=db)

    tags_set = set()
    for model in models:
        if model.meta:
            meta = model.meta.model_dump()
            for tag in meta.get("tags", []):
                tags_set.add((tag.get("name")))

    tags = [tag for tag in tags_set]
    tags.sort()
    return tags


############################
# CreateNewModel
############################


@router.post("/create", response_model=Optional[ModelModel])
async def create_new_model(
    request: Request,
    form_data: ModelForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    require_permission(user, "workspace.models", request, db=db)

    model = Models.get_model_by_id(form_data.id, db=db)
    if model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.MODEL_ID_TAKEN,
        )

    if not is_valid_model_id(form_data.id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.MODEL_ID_TOO_LONG,
        )

    else:
        model = Models.insert_new_model(form_data, user.id, db=db)
        if model:
            return model
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.DEFAULT(),
            )


############################
# ExportModels
############################


@router.get("/export", response_model=list[ModelModel])
async def export_models(
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    require_permission(user, "workspace.models_export", request, db=db)

    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        return Models.get_models(db=db)
    else:
        return Models.get_models_by_user_id(user.id, db=db)


############################
# ImportModels
############################


class ModelsImportForm(BaseModel):
    models: list[dict]


@router.post("/import", response_model=bool)
async def import_models(
    request: Request,
    user=Depends(get_verified_user),
    form_data: ModelsImportForm = (...),
    db: Session = Depends(get_session),
):
    require_permission(user, "workspace.models_import", request, db=db)
    try:
        data = form_data.models
        if isinstance(data, list):
            # Batch-fetch all existing models in one query to avoid N+1
            model_ids = [
                model_data.get("id")
                for model_data in data
                if model_data.get("id") and is_valid_model_id(model_data.get("id"))
            ]
            existing_models = {
                model.id: model
                for model in (
                    Models.get_models_by_ids(model_ids, db=db) if model_ids else []
                )
            }

            for model_data in data:
                # Here, you can add logic to validate model_data if needed
                model_id = model_data.get("id")

                if model_id and is_valid_model_id(model_id):
                    existing_model = existing_models.get(model_id)
                    if existing_model:
                        # Update existing model
                        model_data["meta"] = model_data.get("meta", {})
                        model_data["params"] = model_data.get("params", {})

                        updated_model = ModelForm(
                            **{**existing_model.model_dump(), **model_data}
                        )
                        Models.update_model_by_id(model_id, updated_model, db=db)
                    else:
                        # Insert new model
                        model_data["meta"] = model_data.get("meta", {})
                        model_data["params"] = model_data.get("params", {})
                        new_model = ModelForm(**model_data)
                        Models.insert_new_model(
                            user_id=user.id, form_data=new_model, db=db
                        )
            return True
        else:
            raise HTTPException(status_code=400, detail="JSON 格式无效，请检查输入内容。")
    except Exception as e:
        log.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


############################
# SyncModels
############################


class SyncModelsForm(BaseModel):
    models: list[ModelModel] = []


@router.post("/sync", response_model=list[ModelModel])
async def sync_models(
    request: Request,
    form_data: SyncModelsForm,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    return Models.sync_models(user.id, form_data.models, db=db)


###########################
# GetModelById
###########################


class ModelIdForm(BaseModel):
    id: str


# Note: We're not using the typical url path param here, but instead using a query parameter to allow '/' in the id
@router.get("/model", response_model=Optional[ModelAccessResponse])
async def get_model_by_id(
    id: str, user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    model = Models.get_model_by_id(id, db=db)
    if model:
        if (
            (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
            or model.user_id == user.id
            or AccessGrants.has_access(
                user_id=user.id,
                resource_type="model",
                resource_id=model.id,
                permission="read",
                db=db,
            )
        ):
            return ModelAccessResponse(
                **model.model_dump(),
                write_access=(
                    (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or user.id == model.user_id
                    or AccessGrants.has_access(
                        user_id=user.id,
                        resource_type="model",
                        resource_id=model.id,
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
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


###########################
# GetModelById
###########################


@router.get("/model/profile/image")
def get_model_profile_image(id: str, user=Depends(get_verified_user)):
    model = Models.get_model_by_id(id)

    if model:
        etag = f'"{model.updated_at}"' if model.updated_at else None

        if model.meta.profile_image_url:
            if model.meta.profile_image_url.startswith("http"):
                return Response(
                    status_code=status.HTTP_302_FOUND,
                    headers={"Location": model.meta.profile_image_url},
                )
            elif model.meta.profile_image_url.startswith("data:image"):
                try:
                    header, base64_data = model.meta.profile_image_url.split(",", 1)
                    image_data = base64.b64decode(base64_data)
                    image_buffer = io.BytesIO(image_data)
                    media_type = header.split(";")[0].lstrip("data:")

                    headers = {"Content-Disposition": "inline"}
                    if etag:
                        headers["ETag"] = etag

                    return StreamingResponse(
                        image_buffer,
                        media_type=media_type,
                        headers=headers,
                    )
                except Exception as e:
                    pass

        return FileResponse(f"{STATIC_DIR}/favicon.png")
    else:
        return FileResponse(f"{STATIC_DIR}/favicon.png")


############################
# ToggleModelById
############################


@router.post("/model/toggle", response_model=Optional[ModelResponse])
async def toggle_model_by_id(
    id: str, user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    model = Models.get_model_by_id(id, db=db)
    if model:
        if (
            user.role == "admin"
            or model.user_id == user.id
            or AccessGrants.has_access(
                user_id=user.id,
                resource_type="model",
                resource_id=model.id,
                permission="write",
                db=db,
            )
        ):
            model = Models.toggle_model_by_id(id, db=db)

            if model:
                return model
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error updating function"),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.UNAUTHORIZED,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# UpdateModelById
############################


@router.post("/model/update", response_model=Optional[ModelModel])
async def update_model_by_id(
    form_data: ModelForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    model = Models.get_model_by_id(form_data.id, db=db)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        model.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="model",
            resource_id=model.id,
            permission="write",
            db=db,
        )
        and user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    model = Models.update_model_by_id(
        form_data.id, ModelForm(**form_data.model_dump()), db=db
    )
    return model


############################
# UpdateModelAccessById
############################


class ModelAccessGrantsForm(BaseModel):
    id: str
    name: Optional[str] = None
    access_grants: list[dict]


@router.post("/model/access/update", response_model=Optional[ModelModel])
async def update_model_access_by_id(
    request: Request,
    form_data: ModelAccessGrantsForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    model = Models.get_model_by_id(form_data.id, db=db)

    # Non-preset models (e.g. direct Ollama/OpenAI models) may not have a DB
    # entry yet. Create a minimal one so access grants can be stored.
    if not model:
        if user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )
        model = Models.insert_new_model(
            ModelForm(
                id=form_data.id,
                name=form_data.name or form_data.id,
                meta=ModelMeta(),
                params=ModelParams(),
            ),
            user.id,
            db=db,
        )
        if not model:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=ERROR_MESSAGES.DEFAULT("Error creating model entry"),
            )

    if (
        model.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="model",
            resource_id=model.id,
            permission="write",
            db=db,
        )
        and user.role != "admin"
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    form_data.access_grants = filter_allowed_access_grants(
        request.app.state.config.USER_PERMISSIONS,
        user.id,
        user.role,
        form_data.access_grants,
        "sharing.public_models",
    )

    AccessGrants.set_access_grants(
        "model", form_data.id, form_data.access_grants, db=db
    )

    return Models.get_model_by_id(form_data.id, db=db)


############################
# RegisterToolToModels
############################


class ModelToolRegisterForm(BaseModel):
    tool_id: str
    model_ids: list[str]


@router.post("/model/tools/register", response_model=list[str])
async def register_tool_to_models(
    request: Request,
    form_data: ModelToolRegisterForm,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    """Register (or unregister) a tool to a set of models by editing each
    model's meta.toolIds. Models without a DB entry (e.g. direct
    Ollama/OpenAI models) get a minimal record created first, mirroring
    update_model_access_by_id. Returns the final list of model ids that
    have this tool registered (limited to the ids passed in)."""

    tool_id = form_data.tool_id
    target_ids = set(form_data.model_ids or [])

    registered_ids: list[str] = []

    for model_id in target_ids:
        model = Models.get_model_by_id(model_id, db=db)

        if not model:
            # Non-preset external model without a DB entry: create a minimal
            # one so we can store the tool association.
            model = Models.insert_new_model(
                ModelForm(
                    id=model_id,
                    name=model_id,
                    meta=ModelMeta(),
                    params=ModelParams(),
                ),
                user.id,
                db=db,
            )
            if not model:
                log.warning(f"Failed to create model entry for {model_id}")
                continue

        meta = model.meta.model_dump() if model.meta else {}
        tool_ids = list(meta.get("toolIds") or [])

        if tool_id not in tool_ids:
            tool_ids.append(tool_id)

        meta["toolIds"] = tool_ids

        updated = Models.update_model_by_id(
            model_id,
            ModelForm(
                id=model.id,
                base_model_id=model.base_model_id,
                name=model.name,
                meta=ModelMeta(**meta),
                params=model.params,
                is_active=model.is_active,
            ),
            db=db,
        )
        if updated:
            registered_ids.append(model_id)

    return registered_ids


@router.post("/model/tools/unregister", response_model=list[str])
async def unregister_tool_from_models(
    request: Request,
    form_data: ModelToolRegisterForm,
    user=Depends(get_admin_user),
    db: Session = Depends(get_session),
):
    """Remove a tool from each given model's meta.toolIds. Missing models are
    skipped. Returns the list of model ids that were updated."""

    tool_id = form_data.tool_id
    target_ids = set(form_data.model_ids or [])

    updated_ids: list[str] = []

    for model_id in target_ids:
        model = Models.get_model_by_id(model_id, db=db)
        if not model:
            continue

        meta = model.meta.model_dump() if model.meta else {}
        tool_ids = list(meta.get("toolIds") or [])

        if tool_id not in tool_ids:
            continue

        tool_ids = [t for t in tool_ids if t != tool_id]
        if tool_ids:
            meta["toolIds"] = tool_ids
        else:
            meta.pop("toolIds", None)

        updated = Models.update_model_by_id(
            model_id,
            ModelForm(
                id=model.id,
                base_model_id=model.base_model_id,
                name=model.name,
                meta=ModelMeta(**meta),
                params=model.params,
                is_active=model.is_active,
            ),
            db=db,
        )
        if updated:
            updated_ids.append(model_id)

    return updated_ids


############################
# DeleteModelById
############################


@router.post("/model/delete", response_model=bool)
async def delete_model_by_id(
    form_data: ModelIdForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    model = Models.get_model_by_id(form_data.id, db=db)
    if not model:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if (
        user.role != "admin"
        and model.user_id != user.id
        and not AccessGrants.has_access(
            user_id=user.id,
            resource_type="model",
            resource_id=model.id,
            permission="write",
            db=db,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    result = Models.delete_model_by_id(form_data.id, db=db)
    return result


@router.delete("/delete/all", response_model=bool)
async def delete_all_models(
    user=Depends(get_admin_user), db: Session = Depends(get_session)
):
    result = Models.delete_all_models(db=db)
    return result
