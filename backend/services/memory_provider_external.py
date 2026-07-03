"""Read-only external memory provider views."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from urllib.parse import quote

from backend.services import memory_service
from backend.services import memory_provider_config
from backend.services.memory_provider_catalog import (
    MEMORY_PROVIDER_CAPABILITIES,
    MEMORY_PROVIDER_OPTIONS,
)


def holographic_db_path() -> Path:
    hermes_home = memory_service.hermes_home()
    config = memory_provider_config.read_config()
    plugin_cfg = config.get("plugins", {})
    if isinstance(plugin_cfg, dict):
        plugin_cfg = plugin_cfg.get("hermes-memory-store", {})
    if not isinstance(plugin_cfg, dict):
        plugin_cfg = {}

    configured = plugin_cfg.get("db_path") or ""
    if not configured:
        return hermes_home / "memory_store.db"

    expanded = str(configured).replace("${HERMES_HOME}", str(hermes_home))
    expanded = expanded.replace("$HERMES_HOME", str(hermes_home))
    path = Path(expanded).expanduser()
    if not path.is_absolute():
        return hermes_home / path
    return path


def split_holographic_tags(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(tag).strip() for tag in raw if str(tag).strip()]
    text = "" if raw is None else str(raw)
    return [tag.strip() for tag in text.split(",") if tag.strip()]


def empty_holographic_external_view(path: Path, reason: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "provider": "holographic",
        "available": True,
        "readonly": True,
        "db_path": str(path),
        "summary": {"total": 0, "categories": {}},
        "items": [],
    }
    if reason:
        payload["reason"] = reason
    return payload


def holographic_external_view(limit: int = 100) -> dict[str, Any]:
    path = holographic_db_path()
    if not path.exists():
        return empty_holographic_external_view(path, "store_not_found")

    uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True)
        conn.row_factory = sqlite3.Row
    except sqlite3.Error as exc:
        return {
            "provider": "holographic",
            "available": False,
            "readonly": True,
            "db_path": str(path),
            "reason": "sqlite_open_failed",
            "error": str(exc),
            "summary": {"total": 0, "categories": {}},
            "items": [],
        }

    try:
        table = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'facts'"
        ).fetchone()
        if not table:
            return empty_holographic_external_view(path, "facts_table_missing")

        category_rows = conn.execute(
            "SELECT category, COUNT(*) AS count FROM facts GROUP BY category"
        ).fetchall()
        categories = {
            str(row["category"] or "general"): int(row["count"] or 0)
            for row in category_rows
        }
        total = sum(categories.values())

        rows = conn.execute(
            """
            SELECT fact_id, content, category, tags, trust_score, retrieval_count,
                   helpful_count, created_at, updated_at
            FROM facts
            ORDER BY updated_at DESC, fact_id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.Error as exc:
        return {
            "provider": "holographic",
            "available": False,
            "readonly": True,
            "db_path": str(path),
            "reason": "sqlite_read_failed",
            "error": str(exc),
            "summary": {"total": 0, "categories": {}},
            "items": [],
        }
    finally:
        conn.close()

    return {
        "provider": "holographic",
        "available": True,
        "readonly": True,
        "db_path": str(path),
        "summary": {"total": total, "categories": categories},
        "items": [
            {
                "id": str(row["fact_id"]),
                "content": row["content"] or "",
                "category": row["category"] or "general",
                "tags": split_holographic_tags(row["tags"]),
                "trust_score": row["trust_score"],
                "retrieval_count": row["retrieval_count"] or 0,
                "helpful_count": row["helpful_count"] or 0,
                "created_at": row["created_at"] or "",
                "updated_at": row["updated_at"] or "",
            }
            for row in rows
        ],
    }


def provider_summary_external_view(provider: str) -> dict[str, Any]:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    values = memory_provider_config.provider_config_values(provider)
    current_mode = memory_provider_config.current_config_mode(info, values)
    configured, _missing_fields, _missing_any = memory_provider_config.required_state_for_mode(
        info,
        values,
        current_mode,
    )
    configured_count = 1 if configured else 0
    return {
        "provider": provider,
        "available": True,
        "readonly": True,
        "reason": "summary_only",
        "summary": {"total": configured_count, "categories": {"configured": configured_count}},
        "items": [],
    }


def external_view(provider: str) -> dict[str, Any]:
    if provider == "holographic":
        return holographic_external_view()
    if MEMORY_PROVIDER_CAPABILITIES.get(provider, {}).get("external_read_mode") == "provider_summary":
        return provider_summary_external_view(provider)
    return {
        "provider": provider,
        "available": False,
        "readonly": True,
        "reason": "provider_specific_api_not_configured",
        "items": [],
    }
