import logging
from typing import Optional

from open_webui.models.groups import Groups
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from open_webui.internal.db import get_session
from open_webui.models.skills import (
    SkillForm,
    SkillModel,
    SkillResponse,
    SkillUserResponse,
    SkillAccessResponse,
    SkillAccessListResponse,
    Skills,
)
from open_webui.models.access_grants import AccessGrants
from open_webui.models.skill_categories import SkillCategories
from open_webui.utils.auth import get_admin_user, get_verified_user
from open_webui.utils.access_control import has_access, require_permission, filter_allowed_access_grants

from open_webui.config import BYPASS_ADMIN_ACCESS_CONTROL
from open_webui.constants import ERROR_MESSAGES

log = logging.getLogger(__name__)

PAGE_ITEM_COUNT = 30

router = APIRouter()


def _user_has_skill_access(
    user,
    skill,
    permission: str,
    db: Session,
    user_group_ids: Optional[set] = None,
) -> bool:
    """Check whether a user has the given permission on a skill.

    Access is fully inherited from the parent skill category. A user is granted
    access if they are the owner of the skill, an admin, or have the
    corresponding access_grant on the skill's parent category.
    """
    if user.role == "admin":
        return True
    if skill.user_id == user.id:
        return True
    if getattr(skill, "category_id", None) and AccessGrants.has_access(
        user_id=user.id,
        resource_type="skill_category",
        resource_id=skill.category_id,
        permission=permission,
        user_group_ids=user_group_ids,
        db=db,
    ):
        return True
    return False


############################
# GetSkills
############################


@router.get("/", response_model=list[SkillUserResponse])
async def get_skills(
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        skills = Skills.get_skills(db=db)
    else:
        user_group_ids = {
            group.id for group in Groups.get_groups_by_member_id(user.id, db=db)
        }
        all_skills = Skills.get_skills(db=db)
        skills = [
            skill
            for skill in all_skills
            if _user_has_skill_access(
                user, skill, "read", db, user_group_ids=user_group_ids
            )
        ]

    return skills


############################
# GetSkillList
############################


@router.get("/list", response_model=SkillAccessListResponse)
async def get_skill_list(
    query: Optional[str] = None,
    view_option: Optional[str] = None,
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

    # Skill list is now category-first; the legacy "all skills" listing
    # delegates write_access to the parent category access grants.
    groups = Groups.get_groups_by_member_id(user.id, db=db)
    user_group_ids = {group.id for group in groups}

    if not (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL):
        if groups:
            filter["group_ids"] = [group.id for group in groups]

        filter["user_id"] = user.id

    result = Skills.search_skills(user.id, filter=filter, skip=skip, limit=limit, db=db)

    # Batch-fetch writable categories so write access inherited from the
    # parent category is respected in the list view.
    category_ids = list(
        {skill.category_id for skill in result.items if skill.category_id}
    )
    writable_category_ids = (
        AccessGrants.get_accessible_resource_ids(
            user_id=user.id,
            resource_type="skill_category",
            resource_ids=category_ids,
            permission="write",
            user_group_ids=user_group_ids,
            db=db,
        )
        if category_ids
        else set()
    )

    return SkillAccessListResponse(
        items=[
            SkillAccessResponse(
                **skill.model_dump(),
                write_access=(
                    (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or user.id == skill.user_id
                    or (
                        skill.category_id
                        and skill.category_id in writable_category_ids
                    )
                ),
            )
            for skill in result.items
        ],
        total=result.total,
    )


############################
# ExportSkills
############################


@router.get("/export", response_model=list[SkillModel])
async def export_skills(
    request: Request,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    require_permission(user, "workspace.skills", request, db=db)

    if user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL:
        return Skills.get_skills(db=db)
    else:
        return Skills.get_skills_by_user_id(user.id, "read", db=db)


############################
# CreateNewSkill
############################


@router.post("/create", response_model=Optional[SkillResponse])
async def create_new_skill(
    request: Request,
    form_data: SkillForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    require_permission(user, "workspace.skills", request, db=db)

    # A category is required: skills inherit access from their category.
    if not form_data.category_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请先选择一个分类。",
        )

    category = SkillCategories.get_category_by_id(form_data.category_id, db=db)
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
            resource_type="skill_category",
            resource_id=category.id,
            permission="write",
            db=db,
        )
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
        )

    form_data.id = form_data.id.lower().replace(" ", "-")

    # Skills no longer carry their own access grants — access is inherited
    # from the parent category. Always clear any payload to be safe.
    form_data.access_grants = []

    existing = Skills.get_skill_by_id(form_data.id, db=db)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.ID_TAKEN,
        )

    existing_by_name = Skills.get_skill_by_name(form_data.name, db=db)
    if existing_by_name is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.SKILL_NAME_TAKEN,
        )

    try:
        skill = Skills.insert_new_skill(user.id, form_data, db=db)
        if skill:
            return skill
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error creating skill"),
            )
    except Exception as e:
        log.exception(f"Failed to create skill: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(str(e)),
        )


############################
# GetSkillById
############################


@router.get("/id/{id}", response_model=Optional[SkillAccessResponse])
async def get_skill_by_id(
    id: str, user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    skill = Skills.get_skill_by_id(id, db=db)

    if skill:
        if _user_has_skill_access(user, skill, "read", db):
            return SkillAccessResponse(
                **skill.model_dump(),
                write_access=(
                    (user.role == "admin" and BYPASS_ADMIN_ACCESS_CONTROL)
                    or _user_has_skill_access(user, skill, "write", db)
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
# UpdateSkillById
############################


@router.post("/id/{id}/update", response_model=Optional[SkillModel])
async def update_skill_by_id(
    request: Request,
    id: str,
    form_data: SkillForm,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    skill = Skills.get_skill_by_id(id, db=db)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not _user_has_skill_access(user, skill, "write", db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    # If the caller wants to move the skill to another category, verify they
    # also have write permission on the destination category.
    new_category_id = form_data.category_id
    if new_category_id and new_category_id != skill.category_id:
        new_category = SkillCategories.get_category_by_id(new_category_id, db=db)
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
                resource_type="skill_category",
                resource_id=new_category.id,
                permission="write",
                db=db,
            )
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.ACCESS_PROHIBITED,
            )

    existing_by_name = Skills.get_skill_by_name(form_data.name, db=db)
    if existing_by_name is not None and existing_by_name.id != id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.SKILL_NAME_TAKEN,
        )

    try:
        # Skills no longer carry independent access grants; always drop the
        # field from the update payload so callers cannot bypass the
        # category-inherited model.
        exclude_fields = {"id", "access_grants"}

        updated = {
            **form_data.model_dump(exclude=exclude_fields),
        }

        skill = Skills.update_skill_by_id(id, updated, db=db)

        if skill:
            return skill
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=ERROR_MESSAGES.DEFAULT("Error updating skill"),
            )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=ERROR_MESSAGES.DEFAULT(str(e)),
        )


############################
# ToggleSkillById
############################


@router.post("/id/{id}/toggle", response_model=Optional[SkillModel])
async def toggle_skill_by_id(
    id: str, user=Depends(get_verified_user), db: Session = Depends(get_session)
):
    skill = Skills.get_skill_by_id(id, db=db)
    if skill:
        if _user_has_skill_access(user, skill, "write", db):
            skill = Skills.toggle_skill_by_id(id, db=db)

            if skill:
                return skill
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=ERROR_MESSAGES.DEFAULT("Error toggling skill"),
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=ERROR_MESSAGES.UNAUTHORIZED,
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )


############################
# DeleteSkillById
############################


@router.delete("/id/{id}/delete", response_model=bool)
async def delete_skill_by_id(
    request: Request,
    id: str,
    user=Depends(get_verified_user),
    db: Session = Depends(get_session),
):
    skill = Skills.get_skill_by_id(id, db=db)
    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ERROR_MESSAGES.NOT_FOUND,
        )

    if not _user_has_skill_access(user, skill, "write", db):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=ERROR_MESSAGES.UNAUTHORIZED,
        )

    result = Skills.delete_skill_by_id(id, db=db)
    return result
