"""Skills endpoints."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from backend.collectors.skills import (
    collect_skills,
    collect_skill_translation_options,
    read_skill_detail,
    translate_skill_detail,
)
from backend.services.skills_manager import (
    create_skill,
    delete_skill,
    import_skills_zip_bytes,
    install_market_skill,
    save_skill_content,
    search_skill_market,
    set_skill_enabled,
)
from .serialize import to_dict

router = APIRouter()


class SkillTranslationRequest(BaseModel):
    path: str
    target_lang: str = "auto"
    provider: str | None = None
    model: str | None = None
    force: bool = False
    cache_only: bool = False


class SkillCreateRequest(BaseModel):
    category: str = "uncategorized"
    name: str
    description: str = ""
    content: str = ""


class SkillSaveRequest(BaseModel):
    path: str
    content: str


class SkillToggleRequest(BaseModel):
    name: str
    enabled: bool


class SkillDeleteRequest(BaseModel):
    path: str


class SkillMarketInstallRequest(BaseModel):
    identifier: str
    category: str | None = None
    force: bool = False


@router.get("/skills")
async def get_skills():
    state = collect_skills()
    result = to_dict(state)
    # These are methods, not properties, so they're not auto-serialized
    result["by_category"] = to_dict(state.by_category())
    result["category_counts"] = to_dict(state.category_counts())
    result["recently_modified"] = to_dict(state.recently_modified(10))
    return result


@router.get("/skills/detail")
async def get_skill_detail(path: str = Query(...)):
    detail = read_skill_detail(path)
    if detail is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    return to_dict(detail)


@router.get("/skills/translation-options")
async def get_skill_translation_options():
    return to_dict(collect_skill_translation_options())


@router.post("/skills/translate")
async def get_skill_translation(request: SkillTranslationRequest):
    detail = read_skill_detail(request.path)
    if detail is None:
        raise HTTPException(status_code=404, detail="Skill not found")
    try:
        result = await run_in_threadpool(
            translate_skill_detail,
            detail,
            request.target_lang,
            request.provider,
            request.model,
            request.force,
            request.cache_only,
        )
        return to_dict(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/skills")
async def create_skill_endpoint(request: SkillCreateRequest):
    try:
        result = await run_in_threadpool(
            create_skill,
            request.category,
            request.name,
            request.description,
            request.content,
        )
        return to_dict(result)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/skills/detail")
async def save_skill_detail(request: SkillSaveRequest):
    try:
        result = await run_in_threadpool(
            save_skill_content,
            request.path,
            request.content,
        )
        return to_dict(result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/skills/toggle")
async def toggle_skill(request: SkillToggleRequest):
    try:
        result = await run_in_threadpool(
            set_skill_enabled,
            request.name,
            request.enabled,
        )
        return to_dict(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/skills")
async def delete_skill_endpoint(request: SkillDeleteRequest):
    try:
        result = await run_in_threadpool(delete_skill, request.path)
        return to_dict(result)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/skills/import-zip")
async def import_skills_zip(
    request: Request,
    filename: str = Query("skills.zip"),
    overwrite: bool = Query(False),
):
    try:
        payload = await request.body()
        result = await run_in_threadpool(
            import_skills_zip_bytes,
            payload,
            filename,
            overwrite,
        )
        return to_dict(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/skills/market/search")
async def search_skills_market(
    q: str = Query(""),
    source: str = Query("official"),
    limit: int = Query(20, ge=1, le=100),
):
    try:
        result = await run_in_threadpool(search_skill_market, q, source, limit)
        return to_dict(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.post("/skills/market/install")
async def install_skill_from_market(request: SkillMarketInstallRequest):
    try:
        result = await run_in_threadpool(
            install_market_skill,
            request.identifier,
            request.category,
            request.force,
        )
        return to_dict(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
