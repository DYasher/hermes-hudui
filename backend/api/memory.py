"""Memory endpoints."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.collectors.memory import collect_memory
from backend.collectors.config import collect_config
from backend.collectors.utils import default_hermes_dir, load_yaml
from backend.services import memory_service
from backend.services.memory_provider_catalog import (
    MEMORY_PROVIDER_CAPABILITIES,
    MEMORY_PROVIDER_OPTIONS,
    OFFICIAL_SCHEMA_PROVIDERS,
    provider_group,
)
from .serialize import to_dict

router = APIRouter()

ENTRY_DELIMITER = memory_service.ENTRY_DELIMITER
HOST_KEY = "hermes"

MemoryTarget = Literal["memory", "user"]


def _memory_path(target: MemoryTarget) -> Path:
    """Return the path for MEMORY.md or USER.md."""
    memories_dir = Path(default_hermes_dir()) / "memories"
    if target == "user":
        return memories_dir / "USER.md"
    return memories_dir / "MEMORY.md"


def _lock_path(target: MemoryTarget) -> Path:
    return _memory_path(target).with_suffix(".md.lock")


def _config_path() -> Path:
    return Path(default_hermes_dir()) / "config.yaml"


def _env_path() -> Path:
    return Path(default_hermes_dir()) / ".env"


def _relative_config_path(relative_path: str) -> Path:
    return Path(default_hermes_dir()) / relative_path


def _atomic_write_text(path: Path, text: str, prefix: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=prefix)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _read_config() -> dict:
    path = _config_path()
    if not path.exists():
        return {}
    try:
        data = load_yaml(path.read_text(encoding="utf-8")) or {}
    except OSError:
        raise HTTPException(500, "failed to read config.yaml") from None
    return data if isinstance(data, dict) else {}


def _write_config(config: dict) -> None:
    path = _config_path()
    text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    _atomic_write_text(path, text, ".config.yaml_")


def _read_env_values() -> dict[str, str]:
    path = _env_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    except OSError:
        raise HTTPException(500, "failed to read .env") from None

    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if key:
            values[key] = value
    return values


def _write_env_values(updates: dict[str, str]) -> None:
    path = _env_path()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        lines = []
    except OSError:
        raise HTTPException(500, "failed to read .env") from None

    written: set[str] = set()
    next_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                next_lines.append(f"{key}={updates[key]}")
                written.add(key)
                continue
        next_lines.append(line)

    for key, value in updates.items():
        if key not in written:
            next_lines.append(f"{key}={value}")

    _atomic_write_text(path, "\n".join(next_lines).rstrip() + "\n", ".env_")


def _read_json_file(relative_path: str) -> dict:
    path = _relative_config_path(relative_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"invalid JSON in {relative_path}: {exc.msg}") from exc
    except OSError:
        raise HTTPException(500, f"failed to read {relative_path}") from None
    return data if isinstance(data, dict) else {}


def _write_json_file(relative_path: str, data: dict) -> None:
    path = _relative_config_path(relative_path)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    _atomic_write_text(path, text, f".{Path(relative_path).name}_")


def _json_field_value(provider: str, data: dict, field: dict):
    name = field["name"]
    if provider == "honcho" and name in {"peerName", "workspace", "aiPeer"}:
        value = data.get(name)
        if value not in (None, ""):
            return value
        hosts = data.get("hosts")
        host = hosts.get(HOST_KEY) if isinstance(hosts, dict) else None
        if isinstance(host, dict):
            return host.get(name)
    return data.get(name)


def _config_section(config: dict, parts: list[str]) -> dict:
    current = config
    for part in parts:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    return current


def _yaml_field_value(config: dict, field: dict):
    current = config
    for part in field.get("section", []):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    if not isinstance(current, dict):
        return None
    return current.get(field["name"])


def _coerce_config_value(value: str):
    stripped = value.strip()
    lowered = stripped.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        return int(stripped)
    except ValueError:
        pass
    try:
        return float(stripped)
    except ValueError:
        return stripped


def _validate_config_value(name: str, value: str) -> str:
    value = value.strip()
    if "\n" in value or "\r" in value:
        raise HTTPException(400, f"{name} cannot contain newlines")
    return value


def _dependency_checks(info: dict) -> list[dict]:
    checks = []
    for dep in info.get("dependencies", []):
        kind = dep.get("kind")
        name = dep.get("name")
        present = False
        if kind == "command":
            present = bool(shutil.which(str(name)))
        elif kind == "python":
            present = importlib.util.find_spec(str(name)) is not None
        checks.append(
            {
                "kind": kind,
                "name": name,
                "ok": present,
            }
        )
    return checks


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _config_file_checks(info: dict) -> list[dict]:
    checks = []
    for relative_path in info.get("config_files", []):
        is_directory = str(relative_path).endswith("/")
        path = _relative_config_path(str(relative_path).rstrip("/"))
        checks.append(
            {
                "path": relative_path,
                "kind": "directory" if is_directory else "file",
                "exists": path.is_dir() if is_directory else path.is_file(),
            }
        )
    return checks


def _provider_health(
    provider: str,
    *,
    active: bool,
    configured: bool,
    missing_fields: list[str],
    missing_any: list[list[str]],
    dependency_checks: list[dict],
    status_command: dict | None = None,
) -> dict:
    dependencies_ok = all(check["ok"] for check in dependency_checks)
    return {
        "provider": provider,
        "active": active,
        "checked_at": _utc_now_iso(),
        "config_files": _config_file_checks(MEMORY_PROVIDER_OPTIONS[provider]),
        "required_config": {
            "ok": configured,
            "missing_fields": missing_fields,
            "missing_any": missing_any,
        },
        "dependencies": {
            "ok": dependencies_ok,
            "checks": dependency_checks,
        },
        "status_command": status_command,
    }


def _field_requirement(info: dict, field_name: str) -> tuple[str, list[str]]:
    if field_name in info.get("required_fields", []):
        return "required", []
    for group in info.get("required_any", []):
        if field_name in group:
            return "required_any", group
    return "optional", []


def _mode_specs(info: dict) -> list[dict]:
    modes = []
    for mode in info.get("modes", []):
        modes.append(
            {
                "id": mode["id"],
                "label": mode.get("label", mode["id"]),
                "storage": mode.get("storage", info.get("storage", "")),
                "description": mode.get("description", ""),
                "fields": mode.get("fields", []),
                "required_fields": mode.get("required_fields", []),
                "required_any": mode.get("required_any", []),
                "optional_fields": mode.get("optional_fields", []),
            }
        )
    return modes


def _default_mode(info: dict) -> str:
    modes = _mode_specs(info)
    return modes[0]["id"] if modes else ""


def _mode_by_id(info: dict, mode_id: str) -> dict | None:
    for mode in _mode_specs(info):
        if mode["id"] == mode_id:
            return mode
    return None


def _field_mode_ids(info: dict, field_name: str) -> list[str]:
    mode_ids = [
        mode["id"]
        for mode in _mode_specs(info)
        if field_name in mode.get("fields", [])
    ]
    if mode_ids:
        return mode_ids
    modes = _mode_specs(info)
    return [mode["id"] for mode in modes]


def _field_specs(info: dict) -> list[dict]:
    fields = []
    for field in info.get("fields", []):
        requirement, required_group = _field_requirement(info, field["name"])
        fields.append(
            {
                "name": field["name"],
                "label": field.get("label", field["name"]),
                "storage": field.get("storage", ""),
                "path": field.get("path", field.get("storage", "")),
                "secret": bool(field.get("secret", False)),
                "help": field.get("help", ""),
                "requirement": requirement,
                "required_group": required_group,
                "mode_ids": _field_mode_ids(info, field["name"]),
            }
        )
    return fields


def _provider_config_values(provider: str) -> dict[str, dict]:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    env_values = _read_env_values()
    config = _read_config()
    json_cache: dict[str, dict] = {}
    values: dict[str, dict] = {}

    for field in info.get("fields", []):
        name = field["name"]
        raw = None
        source = field.get("storage", "")
        if source == "env":
            raw = env_values.get(name)
            if raw in (None, ""):
                raw = os.environ.get(name)
        elif source == "json":
            relative_path = field.get("path", "")
            if relative_path not in json_cache:
                json_cache[relative_path] = _read_json_file(relative_path)
            raw = _json_field_value(provider, json_cache[relative_path], field)
            source = relative_path
        elif source == "yaml":
            raw = _yaml_field_value(config, field)
            source = "config.yaml"

        configured = raw not in (None, "")
        values[name] = {
            "configured": configured,
            "secret": bool(field.get("secret", False)),
            "source": source,
            "value": "" if field.get("secret") else ("" if raw is None else str(raw)),
        }
    return values


def _required_state(info: dict, values: dict[str, dict]) -> tuple[bool, list[str], list[list[str]]]:
    missing_fields = [
        name
        for name in info.get("required_fields", [])
        if not values.get(name, {}).get("configured", False)
    ]
    missing_any = [
        group
        for group in info.get("required_any", [])
        if not any(values.get(name, {}).get("configured", False) for name in group)
    ]
    if not info.get("fields") and not missing_fields and not missing_any:
        return True, [], []
    return not missing_fields and not missing_any, missing_fields, missing_any


def _required_state_for_mode(
    info: dict,
    values: dict[str, dict],
    mode_id: str,
) -> tuple[bool, list[str], list[list[str]]]:
    mode = _mode_by_id(info, mode_id)
    if not mode:
        return _required_state(info, values)

    missing_fields = [
        name
        for name in mode.get("required_fields", [])
        if name != "mode" and not values.get(name, {}).get("configured", False)
    ]
    missing_any = [
        group
        for group in mode.get("required_any", [])
        if not any(
            name == "mode" or values.get(name, {}).get("configured", False)
            for name in group
        )
    ]
    return not missing_fields and not missing_any, missing_fields, missing_any


def _current_config_mode(info: dict, values: dict[str, dict]) -> str:
    default_mode = _default_mode(info)
    modes = _mode_specs(info)
    if not modes:
        return ""

    configured_mode = values.get("mode", {}).get("value")
    if isinstance(configured_mode, str) and _mode_by_id(info, configured_mode):
        return configured_mode

    for field in info.get("fields", []):
        name = field["name"]
        if not values.get(name, {}).get("configured", False):
            continue
        mode_ids = _field_mode_ids(info, name)
        if len(mode_ids) == 1:
            return mode_ids[0]

    return default_mode


def _validate_config_mode(info: dict, mode: str) -> str:
    mode = mode.strip()
    if not mode:
        return ""
    if not _mode_by_id(info, mode):
        raise HTTPException(400, f"unknown provider config mode: {mode}")
    return mode


def _validate_required_provider_config(
    provider: str,
    fields: dict[str, str],
    mode: str = "",
) -> None:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    mode = _validate_config_mode(info, mode)
    values = _provider_config_values(provider)
    for name, raw_value in fields.items():
        value = str(raw_value).strip()
        if value and name in values:
            values[name] = {
                **values[name],
                "configured": True,
                "value": "" if values[name].get("secret") else value,
            }

    configured, missing_fields, missing_any = (
        _required_state_for_mode(info, values, mode) if mode else _required_state(info, values)
    )
    if configured:
        return

    missing = [*missing_fields, *[" / ".join(group) for group in missing_any]]
    raise HTTPException(
        400,
        "missing required provider config: " + ", ".join(missing),
    )


def _active_memory_provider(config: dict) -> str:
    memory_cfg = config.get("memory", {})
    if not isinstance(memory_cfg, dict):
        return ""
    provider = str(memory_cfg.get("provider") or "").strip()
    return provider if provider in MEMORY_PROVIDER_OPTIONS else ""


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
    active_provider = _active_memory_provider(_read_config())
    providers = {}
    for key, info in MEMORY_PROVIDER_OPTIONS.items():
        config_values = _provider_config_values(key)
        configured, missing_fields, missing_any = _required_state(info, config_values)
        checks = _dependency_checks(info)
        dependency_ok = all(check["ok"] for check in checks)
        active = key == active_provider
        current_mode = _current_config_mode(info, config_values)
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
            "config_modes": _mode_specs(info),
            "default_mode": _default_mode(info),
            "current_mode": current_mode,
            "config_fields": _field_specs(info),
            "config_values": config_values,
            "capabilities": _provider_capabilities(key),
            "schema_source": _provider_schema_source(key),
            "external_view": _provider_external_view_info(key),
            "health": _provider_health(
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
    config = _read_config()
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
    values = _provider_config_values(provider)
    current_mode = _current_config_mode(info, values)
    configured, _missing_fields, _missing_any = _required_state_for_mode(
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

    config = _read_config()
    memory_cfg = config.get("memory", {})
    if not isinstance(memory_cfg, dict):
        memory_cfg = {}
    if provider:
        memory_cfg["provider"] = provider
    else:
        memory_cfg.pop("provider", None)
    config["memory"] = memory_cfg

    try:
        _write_config(config)
    except OSError as exc:
        raise HTTPException(500, f"failed to write config.yaml: {exc}") from exc

    return _memory_provider_payload()


def _write_honcho_config(updates: dict[str, str]) -> None:
    data = _read_json_file("honcho.json")
    host_fields = {"peerName", "workspace", "aiPeer"}
    hosts = data.get("hosts")
    if not isinstance(hosts, dict):
        hosts = {}
        data["hosts"] = hosts
    host = hosts.get(HOST_KEY)
    if not isinstance(host, dict):
        host = {}
        hosts[HOST_KEY] = host
    if any(name in updates for name in host_fields):
        host.setdefault("enabled", True)

    for name, value in updates.items():
        data[name] = _coerce_config_value(value)
        if name in host_fields:
            host[name] = _coerce_config_value(value)

    _write_json_file("honcho.json", data)


def _save_provider_fields(provider: str, fields: dict[str, str], mode: str = "") -> None:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    mode = _validate_config_mode(info, mode)
    fields = {name: value for name, value in fields.items()}
    if mode and "mode" in {field["name"] for field in info.get("fields", [])}:
        fields.setdefault("mode", mode)

    specs = {field["name"]: field for field in info.get("fields", [])}
    unknown = [name for name in fields if name not in specs]
    if unknown:
        raise HTTPException(400, f"unknown config field: {unknown[0]}")
    _validate_required_provider_config(provider, fields, mode)

    env_updates: dict[str, str] = {}
    json_updates: dict[str, dict[str, str]] = {}
    yaml_updates: list[tuple[dict, str]] = []

    for name, raw_value in fields.items():
        spec = specs[name]
        value = _validate_config_value(name, str(raw_value))
        if not value:
            continue
        storage = spec.get("storage")
        if storage == "env":
            env_updates[name] = value
        elif storage == "json":
            relative_path = spec.get("path", "")
            json_updates.setdefault(relative_path, {})[name] = value
        elif storage == "yaml":
            yaml_updates.append((spec, value))

    if env_updates:
        _write_env_values(env_updates)

    for relative_path, updates in json_updates.items():
        if provider == "honcho" and relative_path == "honcho.json":
            _write_honcho_config(updates)
            continue
        data = _read_json_file(relative_path)
        for name, value in updates.items():
            data[name] = _coerce_config_value(value)
        _write_json_file(relative_path, data)

    if yaml_updates:
        config = _read_config()
        for spec, value in yaml_updates:
            section = _config_section(config, spec.get("section", []))
            section[spec["name"]] = _coerce_config_value(value)
        _write_config(config)


@router.put("/memory/providers/{provider}/config")
def save_memory_provider_config(provider: str, body: MemoryProviderConfigBody):
    """Save provider-specific local configuration without selecting it."""
    provider = provider.strip().lower()
    if provider not in MEMORY_PROVIDER_OPTIONS:
        raise HTTPException(400, "unknown memory provider")
    try:
        _save_provider_fields(provider, body.fields, body.mode)
    except OSError as exc:
        raise HTTPException(500, f"failed to write provider config: {exc}") from exc
    return _memory_provider_payload()


@router.post("/memory/providers/check")
def check_memory_provider_status(body: MemoryProviderBody):
    """Run Hermes' read-only memory status command."""
    provider = body.provider.strip().lower()
    if provider and provider not in MEMORY_PROVIDER_OPTIONS:
        raise HTTPException(400, "unknown memory provider")

    hermes = shutil.which("hermes")
    status = {
        "ok": False,
        "exit_code": None,
        "output": "",
        "error": "hermes CLI not found on PATH",
        "command": "hermes memory status",
    }
    if hermes:
        try:
            completed = subprocess.run(
                [hermes, "memory", "status"],
                cwd=str(default_hermes_dir()),
                capture_output=True,
                text=True,
                timeout=20,
            )
            status = {
                "ok": completed.returncode == 0,
                "exit_code": completed.returncode,
                "output": completed.stdout.strip(),
                "error": completed.stderr.strip(),
                "command": "hermes memory status",
            }
        except (OSError, subprocess.TimeoutExpired) as exc:
            status = {
                "ok": False,
                "exit_code": None,
                "output": "",
                "error": str(exc),
                "command": "hermes memory status",
            }

    payload = _memory_provider_payload()
    health = None
    if provider:
        provider_payload = payload["providers"].get(provider)
        if provider_payload:
            health = {
                **provider_payload["health"],
                "checked_at": _utc_now_iso(),
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
