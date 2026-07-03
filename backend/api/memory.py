"""Memory endpoints."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.collectors.memory import collect_memory
from backend.collectors.config import collect_config
from backend.collectors.utils import default_hermes_dir
from backend.services import memory_service
from backend.services import memory_provider_config
from backend.services import memory_provider_health
from backend.services.memory_provider_catalog import (
    MEMORY_PROVIDER_CAPABILITIES,
    MEMORY_PROVIDER_OPTIONS,
    OFFICIAL_SCHEMA_PROVIDERS,
    provider_group,
)
from .serialize import to_dict

router = APIRouter()

ENTRY_DELIMITER = memory_service.ENTRY_DELIMITER

MemoryTarget = Literal["memory", "user"]


def _memory_path(target: MemoryTarget) -> Path:
    """Return the path for MEMORY.md or USER.md."""
    memories_dir = Path(default_hermes_dir()) / "memories"
    if target == "user":
        return memories_dir / "USER.md"
    return memories_dir / "MEMORY.md"


def _lock_path(target: MemoryTarget) -> Path:
    return _memory_path(target).with_suffix(".md.lock")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _provider_capabilities(provider: str) -> dict:
    return {
        "external_read": False,
        "external_read_mode": "none",
        "direct_hud_config": bool(MEMORY_PROVIDER_OPTIONS[provider].get("fields")),
        "requires_network": MEMORY_PROVIDER_OPTIONS[provider].get("storage") not in {"local"},
        "local_storage": False,
        "supports_tools": False,
        "supports_auto_recall": False,
        "supports_session_ingest": False,
        "supports_manual_write": False,
        "hooks": [],
        **MEMORY_PROVIDER_CAPABILITIES.get(provider, {}),
    }


def _provider_schema_source(provider: str) -> dict:
    if provider in OFFICIAL_SCHEMA_PROVIDERS:
        return {
            "kind": "official_schema",
            "method": "get_config_schema",
            "fallback": False,
            "source": "official memory provider plugin",
        }
    return {
        "kind": "hud_metadata",
        "method": "",
        "fallback": True,
        "source": "HUD static metadata",
    }


def _provider_external_view_info(provider: str) -> dict:
    if provider == "holographic":
        return {
            "available": True,
            "readonly": True,
            "endpoint": "/api/memory/providers/holographic/external",
            "view_type": "facts",
            "reason": "",
        }
    if _provider_capabilities(provider).get("external_read_mode") == "provider_summary":
        return {
            "available": True,
            "readonly": True,
            "endpoint": f"/api/memory/providers/{provider}/external",
            "view_type": "summary",
            "reason": "summary_only",
        }
    return {
        "available": False,
        "readonly": True,
        "endpoint": "",
        "view_type": "",
        "reason": "provider_specific_api_not_configured",
    }


def _memory_provider_payload() -> dict:
    active_provider = memory_provider_config.active_memory_provider(
        memory_provider_config.read_config()
    )
    providers = {}
    for key, info in MEMORY_PROVIDER_OPTIONS.items():
        config_values = memory_provider_config.provider_config_values(key)
        configured, missing_fields, missing_any = memory_provider_config.required_state(
            info,
            config_values,
        )
        checks = memory_provider_health.dependency_checks(info)
        dependency_ok = all(check["ok"] for check in checks)
        active = key == active_provider
        current_mode = memory_provider_config.current_config_mode(info, config_values)
        if not configured:
            readiness = "selected" if active else "missing_config"
        elif active and dependency_ok:
            readiness = "ready"
        elif active:
            readiness = "selected"
        else:
            readiness = "configured"

        providers[key] = {
            **info,
            "id": key,
            "group": provider_group(key),
            "active": active,
            "configured": configured,
            "readiness": readiness,
            "missing_fields": missing_fields,
            "missing_any": missing_any,
            "checks": checks,
            "config_modes": memory_provider_config.mode_specs(info),
            "default_mode": memory_provider_config.default_mode(info),
            "current_mode": current_mode,
            "config_fields": memory_provider_config.field_specs(info),
            "config_values": config_values,
            "capabilities": _provider_capabilities(key),
            "schema_source": _provider_schema_source(key),
            "external_view": _provider_external_view_info(key),
            "health": memory_provider_health.provider_health(
                key,
                active=active,
                configured=configured,
                missing_fields=missing_fields,
                missing_any=missing_any,
                dependency_checks=checks,
            ),
        }
    return {
        "builtin": {
            "enabled": True,
            "sources": ["MEMORY.md", "USER.md"],
        },
        "active_provider": active_provider,
        "providers": providers,
        "setup_command": "hermes memory setup",
        "status_command": "hermes memory status",
        "off_command": "hermes memory off",
    }


def _read_entries(target: MemoryTarget) -> list[str]:
    """Read and split entries from a memory file."""
    return memory_service.read_entries(target)


def _write_entries(target: MemoryTarget, entries: list[str]) -> None:
    """Atomically write entries back to a memory file."""
    memory_service.write_entries(target, entries)


def _with_lock(target: MemoryTarget, fn):
    """Execute fn while holding the memory file lock."""
    return memory_service.with_memory_lock(target, fn)


@router.get("/memory")
async def get_memory():
    """Memory and user profile state."""
    config = collect_config()
    memory, user = collect_memory(
        memory_char_limit=config.memory_char_limit,
        user_char_limit=config.user_char_limit,
    )
    return {
        "memory": to_dict(memory),
        "user": to_dict(user),
    }


@router.get("/memory/files")
def get_memory_files():
    """Built-in MEMORY.md and USER.md state."""
    return memory_service.memory_files_payload()


@router.put("/memory/files/{target}")
def save_memory_file(target: str, body: MemoryFileBody):
    """Save a full built-in memory file."""
    normalized = target.strip().lower()
    if normalized not in {"memory", "user"}:
        raise HTTPException(400, "unknown memory file")
    return memory_service.save_memory_file(normalized, body.content)


def _state_db_path() -> Path:
    return Path(default_hermes_dir()) / "state.db"


def _sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(row[1]) for row in rows}


def _sqlite_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {str(row[0]) for row in rows}


def _column_expr(table: str, columns: set[str], name: str, default: str) -> str:
    return f"{table}.{name}" if name in columns else default


def _history_snippet(content: str, query: str, max_len: int = 220) -> str:
    text = content.strip()
    if len(text) <= max_len:
        return text
    if query:
        idx = text.lower().find(query.lower())
        if idx >= 0:
            start = max(0, idx - 70)
            end = min(len(text), idx + len(query) + 130)
            return ("..." if start else "") + text[start:end].strip() + ("..." if end < len(text) else "")
    return text[:max_len].rstrip() + "..."


def _suggest_memory_target(content: str) -> MemoryTarget:
    lowered = content.lower()
    user_markers = (
        "i prefer",
        "i like",
        "my preference",
        "user prefer",
        "user prefers",
        "user likes",
        "用户",
        "偏好",
        "喜欢",
        "我喜欢",
        "我希望",
    )
    return "user" if any(marker in lowered for marker in user_markers) else "memory"


def _memory_history_candidate(row: sqlite3.Row, query: str) -> dict[str, Any]:
    content = str(row["content"] or "")
    session_id = str(row["session_id"] or "")
    title = str(row["title"] or "") or session_id[:8]
    return {
        "session_id": session_id,
        "message_id": str(row["message_id"] or ""),
        "title": title,
        "source": str(row["source"] or ""),
        "started_at": row["started_at"] or 0,
        "message_count": row["message_count"] or 0,
        "role": str(row["role"] or ""),
        "timestamp": row["timestamp"] or 0,
        "snippet": _history_snippet(content, query),
        "content": content,
        "suggested_target": _suggest_memory_target(content),
    }


@router.get("/memory/history")
def get_memory_history(q: str = "", limit: int = 12):
    """Search conversation history for memory candidates."""
    query = q.strip()
    limit = max(1, min(int(limit or 12), 50))
    db = _state_db_path()
    if not db.exists():
        return {"query": query, "count": 0, "status": "database_missing", "candidates": []}

    try:
        conn = sqlite3.connect(str(db))
        conn.row_factory = sqlite3.Row
        tables = _sqlite_tables(conn)
        if not {"sessions", "messages"}.issubset(tables):
            return {"query": query, "count": 0, "status": "schema_missing", "candidates": []}

        session_columns = _sqlite_columns(conn, "sessions")
        message_columns = _sqlite_columns(conn, "messages")
        if not {"session_id", "content"}.issubset(message_columns):
            return {"query": query, "count": 0, "status": "schema_missing", "candidates": []}

        title_expr = _column_expr("sessions", session_columns, "title", "''")
        source_expr = _column_expr("sessions", session_columns, "source", "''")
        started_expr = _column_expr("sessions", session_columns, "started_at", "0")
        count_expr = _column_expr("sessions", session_columns, "message_count", "0")
        message_id_expr = _column_expr("messages", message_columns, "id", "CAST(messages.rowid AS TEXT)")
        role_expr = _column_expr("messages", message_columns, "role", "''")
        timestamp_expr = _column_expr("messages", message_columns, "timestamp", "0")
        where = ["LOWER(COALESCE({source}, '')) != 'tool'".format(source=source_expr)]
        if "parent_session_id" in session_columns:
            where.append("sessions.parent_session_id IS NULL")
        if "role" in message_columns:
            where.append("messages.role IN ('user', 'assistant')")
        where.append("TRIM(COALESCE(messages.content, '')) != ''")
        params: list[Any] = []
        if query:
            where.append("(messages.content LIKE ? OR {title} LIKE ?)".format(title=title_expr))
            params.extend([f"%{query}%", f"%{query}%"])
        params.append(limit)
        rows = conn.execute(
            """
            SELECT sessions.id AS session_id,
                   {message_id} AS message_id,
                   {title} AS title,
                   {source} AS source,
                   {started_at} AS started_at,
                   {message_count} AS message_count,
                   {role} AS role,
                   {timestamp} AS timestamp,
                   messages.content AS content
            FROM messages
            JOIN sessions ON messages.session_id = sessions.id
            WHERE {where}
            ORDER BY timestamp DESC
            LIMIT ?
            """.format(
                message_id=message_id_expr,
                title=title_expr,
                source=source_expr,
                started_at=started_expr,
                message_count=count_expr,
                role=role_expr,
                timestamp=timestamp_expr,
                where=" AND ".join(where),
            ),
            params,
        ).fetchall()
    except sqlite3.Error as exc:
        raise HTTPException(500, f"failed to read state.db: {exc}") from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass

    candidates = [_memory_history_candidate(row, query) for row in rows]
    return {
        "query": query,
        "count": len(candidates),
        "status": "ok",
        "candidates": candidates,
    }


@router.post("/memory/history/commit")
def commit_memory_history_candidate(body: MemoryHistoryCommitBody):
    """Save a selected history candidate into MEMORY.md or USER.md."""
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "content cannot be empty")
    metadata = {
        "source_session_id": body.source_session_id,
        "source_message_id": body.source_message_id,
    }
    if memory_service.memory_settings_payload()["write_approval"]:
        record = memory_service.stage_pending_memory_write(
            body.target,
            content,
            origin="history_candidate",
            summary=content[:160],
            metadata=metadata,
        )
        return {
            "ok": True,
            "staged": True,
            "target": body.target,
            "pending_id": record["id"],
        }

    result = memory_service.apply_memory_operation("add", body.target, content)
    return {
        **result,
        "staged": False,
        "target": body.target,
    }


def _provider_export_payload() -> dict[str, Any]:
    provider_payload = _memory_provider_payload()
    active_provider = provider_payload["active_provider"]
    redactions: list[str] = []
    providers: dict[str, Any] = {}

    for provider_id, provider in provider_payload["providers"].items():
        exported_fields: dict[str, Any] = {}
        for field in provider.get("config_fields", []):
            name = field["name"]
            current = provider.get("config_values", {}).get(name, {})
            configured = bool(current.get("configured"))
            secret = bool(field.get("secret"))
            exported_fields[name] = {
                "label": field.get("label", name),
                "storage": field.get("storage", ""),
                "source": current.get("source") or field.get("path") or field.get("storage", ""),
                "configured": configured,
                "redacted": secret and configured,
                "value": "" if secret else str(current.get("value") or ""),
            }
            if secret and configured:
                redactions.append(f"{provider_id}.{name}")

        if provider_id == active_provider or any(field["configured"] for field in exported_fields.values()):
            providers[provider_id] = {
                "label": provider.get("label", provider_id),
                "storage": provider.get("storage", ""),
                "active": bool(provider.get("active")),
                "configured": bool(provider.get("configured")),
                "current_mode": provider.get("current_mode", ""),
                "fields": exported_fields,
            }

    return {
        "active_provider": active_provider,
        "providers": providers,
        "redactions": redactions,
    }


@router.get("/memory/export")
def get_memory_export():
    """Return a redacted memory export payload."""
    return {
        "generated_at": _utc_now_iso(),
        "hermes_home": str(default_hermes_dir()),
        "files": {
            target: memory_service.read_memory_file(target)
            for target in ("memory", "user")
        },
        "settings": memory_service.memory_settings_payload(),
        "provider": _provider_export_payload(),
    }


@router.post("/memory/export")
def create_memory_export_backup(body: MemoryExportBody | None = None):
    """Write a redacted memory export backup under Hermes home."""
    payload = get_memory_export()
    backup_dir = Path(default_hermes_dir()) / "backups" / "memory"
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = backup_dir / f"hud-memory-export-{timestamp}.json"
    try:
        memory_service.atomic_write_text(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            ".memory_export_",
        )
    except OSError as exc:
        raise HTTPException(500, f"failed to write memory export backup: {exc}") from exc
    return {
        "ok": True,
        "path": str(path),
        "generated_at": payload["generated_at"],
        "export": payload,
    }


@router.get("/memory/settings")
def get_memory_settings():
    """Memory-related config values from config.yaml."""
    return memory_service.memory_settings_payload()


@router.put("/memory/settings")
def save_memory_settings(body: MemorySettingsBody):
    """Update memory settings while preserving unrelated config."""
    updates = {
        name: getattr(body, name)
        for name in body.model_fields_set
    }
    return memory_service.save_memory_settings(updates)


@router.get("/memory/pending")
def get_memory_pending():
    """Pending memory writes staged by memory.write_approval."""
    return memory_service.pending_payload()


@router.post("/memory/pending/{pending_id}/approve")
def approve_pending_memory(pending_id: str):
    """Apply a staged memory write and remove it from pending."""
    return memory_service.apply_pending_memory_write(pending_id)


@router.post("/memory/pending/{pending_id}/reject")
def reject_pending_memory(pending_id: str):
    """Reject a staged memory write."""
    return memory_service.reject_pending_memory_write(pending_id)


@router.get("/memory/providers")
def get_memory_providers():
    """External memory provider state.

    Built-in MEMORY.md / USER.md remains active regardless of external provider.
    """
    return _memory_provider_payload()


def _holographic_db_path() -> Path:
    hermes_home = Path(default_hermes_dir())
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


def _split_holographic_tags(raw) -> list[str]:
    if isinstance(raw, list):
        return [str(tag).strip() for tag in raw if str(tag).strip()]
    text = "" if raw is None else str(raw)
    return [tag.strip() for tag in text.split(",") if tag.strip()]


def _empty_holographic_external_view(path: Path, reason: str = "") -> dict:
    payload = {
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


def _holographic_external_view(limit: int = 100) -> dict:
    path = _holographic_db_path()
    if not path.exists():
        return _empty_holographic_external_view(path, "store_not_found")

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
            return _empty_holographic_external_view(path, "facts_table_missing")

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
                "tags": _split_holographic_tags(row["tags"]),
                "trust_score": row["trust_score"],
                "retrieval_count": row["retrieval_count"] or 0,
                "helpful_count": row["helpful_count"] or 0,
                "created_at": row["created_at"] or "",
                "updated_at": row["updated_at"] or "",
            }
            for row in rows
        ],
    }


def _provider_summary_external_view(provider: str) -> dict:
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


@router.get("/memory/providers/{provider}/external")
def get_memory_provider_external_view(provider: str):
    """Read provider-specific external memory data when the HUD can do so safely."""
    provider = provider.strip().lower()
    if provider not in MEMORY_PROVIDER_OPTIONS:
        raise HTTPException(400, "unknown memory provider")
    if provider == "holographic":
        return _holographic_external_view()
    if _provider_capabilities(provider).get("external_read_mode") == "provider_summary":
        return _provider_summary_external_view(provider)
    return {
        "provider": provider,
        "available": False,
        "readonly": True,
        "reason": "provider_specific_api_not_configured",
        "items": [],
    }


class AddBody(BaseModel):
    target: MemoryTarget
    content: str


class EditBody(BaseModel):
    target: MemoryTarget
    old_text: str
    content: str


class DeleteBody(BaseModel):
    target: MemoryTarget
    old_text: str


class MemoryProviderBody(BaseModel):
    provider: str = ""


class MemoryProviderConfigBody(BaseModel):
    mode: str = ""
    fields: dict[str, str] = Field(default_factory=dict)


class MemoryFileBody(BaseModel):
    content: str


class MemoryHistoryCommitBody(BaseModel):
    target: MemoryTarget
    content: str
    source_session_id: str = ""
    source_message_id: str = ""


class MemoryExportBody(BaseModel):
    pass


class MemorySettingsBody(BaseModel):
    memory_enabled: bool | None = None
    user_profile_enabled: bool | None = None
    memory_char_limit: int | None = None
    user_char_limit: int | None = None
    write_approval: bool | None = None
    memory_notifications: str | None = None


@router.put("/memory/providers")
def set_memory_provider(body: MemoryProviderBody):
    """Select one external memory provider or disable external providers."""
    provider = body.provider.strip().lower()
    if provider and provider not in MEMORY_PROVIDER_OPTIONS:
        raise HTTPException(400, "unknown memory provider")

    config = memory_provider_config.read_config()
    memory_cfg = config.get("memory", {})
    if not isinstance(memory_cfg, dict):
        memory_cfg = {}
    if provider:
        memory_cfg["provider"] = provider
    else:
        memory_cfg.pop("provider", None)
    config["memory"] = memory_cfg

    try:
        memory_provider_config.write_config(config)
    except OSError as exc:
        raise HTTPException(500, f"failed to write config.yaml: {exc}") from exc

    return _memory_provider_payload()


@router.put("/memory/providers/{provider}/config")
def save_memory_provider_config(provider: str, body: MemoryProviderConfigBody):
    """Save provider-specific local configuration without selecting it."""
    provider = provider.strip().lower()
    if provider not in MEMORY_PROVIDER_OPTIONS:
        raise HTTPException(400, "unknown memory provider")
    try:
        memory_provider_config.save_provider_fields(provider, body.fields, body.mode)
    except OSError as exc:
        raise HTTPException(500, f"failed to write provider config: {exc}") from exc
    return _memory_provider_payload()


@router.post("/memory/providers/check")
def check_memory_provider_status(body: MemoryProviderBody):
    """Run Hermes' read-only memory status command."""
    provider = body.provider.strip().lower()
    if provider and provider not in MEMORY_PROVIDER_OPTIONS:
        raise HTTPException(400, "unknown memory provider")

    status = memory_provider_health.hermes_status_command()

    payload = _memory_provider_payload()
    health = None
    if provider:
        provider_payload = payload["providers"].get(provider)
        if provider_payload:
            health = {
                **provider_payload["health"],
                "checked_at": memory_provider_health.utc_now_iso(),
                "status_command": status,
            }

    return {
        "provider": provider,
        "active_provider": payload["active_provider"],
        "status_command": status,
        "health": health,
    }


@router.post("/memory")
def add_entry(body: AddBody):
    """Add a new memory entry."""
    content = body.content.strip()
    if not content:
        raise HTTPException(400, "content cannot be empty")

    def do():
        entries = _read_entries(body.target)
        for e in entries:
            if e == content:
                raise HTTPException(409, "Duplicate entry")
        entries.append(content)
        _write_entries(body.target, entries)
        return {"ok": True, "entry_count": len(entries)}

    return _with_lock(body.target, do)


@router.put("/memory")
def edit_entry(body: EditBody):
    """Replace a memory entry (matched by old_text substring)."""
    new_content = body.content.strip()
    if not new_content:
        raise HTTPException(400, "content cannot be empty")

    def do():
        entries = _read_entries(body.target)
        matches = [i for i, e in enumerate(entries) if body.old_text in e]
        if not matches:
            raise HTTPException(404, "No entry matches old_text")
        if len(matches) > 1:
            raise HTTPException(409, "Multiple entries match — use a more specific old_text")
        entries[matches[0]] = new_content
        _write_entries(body.target, entries)
        return {"ok": True, "entry_count": len(entries)}

    return _with_lock(body.target, do)


@router.delete("/memory")
def delete_entry(body: DeleteBody):
    """Remove a memory entry (matched by old_text substring)."""

    def do():
        entries = _read_entries(body.target)
        matches = [i for i, e in enumerate(entries) if body.old_text in e]
        if not matches:
            raise HTTPException(404, "No entry matches old_text")
        if len(matches) > 1:
            raise HTTPException(409, "Multiple entries match — use a more specific old_text")
        entries.pop(matches[0])
        _write_entries(body.target, entries)
        return {"ok": True, "entry_count": len(entries)}

    return _with_lock(body.target, do)
