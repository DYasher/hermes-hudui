"""Runtime safety posture endpoint."""

from fastapi import APIRouter

from backend.collectors.safety import collect_safety
from .serialize import to_dict

router = APIRouter()


@router.get("/safety")
async def get_safety():
    return to_dict(collect_safety())
