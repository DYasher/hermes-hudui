"""Skills endpoints."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel

from backend.collectors.skills import (
    collect_skills,
    collect_skill_translation_options,
    read_skill_detail,
    translate_skill_detail,
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
