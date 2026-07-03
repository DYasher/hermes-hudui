"""Memory provider catalog helpers."""

from __future__ import annotations

OFFICIAL_PROVIDER_GROUP = "official"
COMMUNITY_PROVIDER_GROUP = "community"

COMMUNITY_SCHEMA_PROVIDERS = {
    "cognee",
    "agentmemory",
    "memos",
}


def provider_group(provider: str) -> str:
    """Return the display group for a memory provider."""
    return (
        COMMUNITY_PROVIDER_GROUP
        if provider in COMMUNITY_SCHEMA_PROVIDERS
        else OFFICIAL_PROVIDER_GROUP
    )
