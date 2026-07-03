"""Service helpers for Hermes memory files, settings, and pending approvals."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import HTTPException

from backend.collectors.memory import MEMORY_MAX_CHARS, USER_MAX_CHARS, _parse_entries
from backend.collectors.utils import default_hermes_dir, load_yaml

ENTRY_DELIMITER = "\n§\n"
MemoryTarget = Literal["memory", "user"]
MemoryFileTarget = Literal["memory", "user"]

MEMORY_FILE_DEFS: dict[MemoryFileTarget, dict[str, Any]] = {
    "memory": {
        "label": "MEMORY.md",
        "path_parts": ("memories", "MEMORY.md"),
        "max_chars": MEMORY_MAX_CHARS,
        "editable": True,
    },
    "user": {
        "label": "USER.md",
        "path_parts": ("memories", "USER.md"),
        "max_chars": USER_MAX_CHARS,
        "editable": True,
    },
}

DISPLAY_MEMORY_NOTIFICATION_VALUES = {"off", "on", "verbose"}


def hermes_home() -> Path:
    return Path(default_hermes_dir())


def memory_path(target: MemoryFileTarget) -> Path:
    info = MEMORY_FILE_DEFS[target]
    return hermes_home().joinpath(*info["path_parts"])


def lock_path(target: MemoryFileTarget) -> Path:
    return memory_path(target).with_suffix(".md.lock")


def config_path() -> Path:
    return hermes_home() / "config.yaml"


def pending_memory_dir() -> Path:
    return hermes_home() / "pending" / "memory"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_write_text(path: Path, text: str, prefix: str) -> None:
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


def read_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        return {}
    try:
        data = load_yaml(path.read_text(encoding="utf-8")) or {}
    except OSError:
        raise HTTPException(500, "failed to read config.yaml") from None
    return data if isinstance(data, dict) else {}


def write_config(config: dict[str, Any]) -> None:
    text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    atomic_write_text(config_path(), text, ".config.yaml_")


def memory_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = read_config() if config is None else config
    section = config.get("memory", {})
    return section if isinstance(section, dict) else {}


def display_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = read_config() if config is None else config
    section = config.get("display", {})
    return section if isinstance(section, dict) else {}


def normalize_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "on", "1", "enabled"}:
            return True
        if lowered in {"false", "no", "off", "0", "disabled"}:
            return False
    return default


def coerce_positive_int(name: str, value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{name} must be an integer") from None
    if parsed <= 0:
        raise HTTPException(400, f"{name} must be positive")
    return parsed


def memory_settings_payload() -> dict[str, Any]:
    config = read_config()
    mem = memory_config(config)
    display = display_config(config)
    notification = str(display.get("memory_notifications") or "on").strip().lower()
    if notification not in DISPLAY_MEMORY_NOTIFICATION_VALUES:
        notification = "on"
    return {
        "memory_enabled": normalize_bool(mem.get("memory_enabled"), True),
        "user_profile_enabled": normalize_bool(mem.get("user_profile_enabled"), True),
        "memory_char_limit": coerce_positive_int(
            "memory_char_limit",
            mem.get("memory_char_limit", MEMORY_MAX_CHARS),
        ),
        "user_char_limit": coerce_positive_int(
            "user_char_limit",
            mem.get("user_char_limit", USER_MAX_CHARS),
        ),
        "write_approval": normalize_bool(mem.get("write_approval"), False),
        "memory_notifications": notification,
        "pending_count": len(list_pending_memory_writes()),
    }


def save_memory_settings(updates: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "memory_enabled",
        "user_profile_enabled",
        "memory_char_limit",
        "user_char_limit",
        "write_approval",
        "memory_notifications",
    }
    unknown = [name for name in updates if name not in allowed]
    if unknown:
        raise HTTPException(400, f"unknown memory setting: {unknown[0]}")

    config = read_config()
    mem = config.get("memory", {})
    if not isinstance(mem, dict):
        mem = {}
    display = config.get("display", {})
    if not isinstance(display, dict):
        display = {}

    for name in ("memory_enabled", "user_profile_enabled", "write_approval"):
        if name in updates:
            mem[name] = normalize_bool(updates[name], False)
    if "memory_char_limit" in updates:
        mem["memory_char_limit"] = coerce_positive_int("memory_char_limit", updates["memory_char_limit"])
    if "user_char_limit" in updates:
        mem["user_char_limit"] = coerce_positive_int("user_char_limit", updates["user_char_limit"])
    if "memory_notifications" in updates:
        value = str(updates["memory_notifications"]).strip().lower()
        if value not in DISPLAY_MEMORY_NOTIFICATION_VALUES:
            raise HTTPException(400, "memory_notifications must be off, on, or verbose")
        display["memory_notifications"] = value

    config["memory"] = mem
    config["display"] = display
    try:
        write_config(config)
    except OSError as exc:
        raise HTTPException(500, f"failed to write config.yaml: {exc}") from exc
    return memory_settings_payload()


def read_entries(target: MemoryTarget) -> list[str]:
    path = memory_path(target)
    try:
        content = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return []
    if not content:
        return []
    return [p.strip() for p in content.split("§") if p.strip()]


def write_entries(target: MemoryTarget, entries: list[str]) -> None:
    path = memory_path(target)
    content = ENTRY_DELIMITER.join(entries) + "\n" if entries else ""
    atomic_write_text(path, content, ".memory_")


def with_memory_lock(target: MemoryFileTarget, fn):
    lock = lock_path(target)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch(exist_ok=True)
    with open(lock, "r") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        return fn()


def file_stats(target: MemoryFileTarget, content: str) -> dict[str, Any]:
    path = memory_path(target)
    exists = path.exists()
    modified_at = ""
    if exists:
        try:
            modified_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        except OSError:
            modified_at = ""
    info = MEMORY_FILE_DEFS[target]
    entries = _parse_entries(content, target)
    max_chars = int(info["max_chars"])
    return {
        "target": target,
        "label": info["label"],
        "path": str(path),
        "exists": exists,
        "editable": bool(info["editable"]),
        "content": content,
        "total_chars": len(content),
        "max_chars": max_chars,
        "capacity_pct": (len(content) / max_chars * 100) if max_chars > 0 else 0,
        "entry_count": len(entries),
        "entries": [
            {"text": entry.text, "category": entry.category, "char_count": entry.char_count}
            for entry in entries
        ],
        "count_by_category": {entry.category: sum(1 for item in entries if item.category == entry.category) for entry in entries},
        "modified_at": modified_at,
    }


def read_memory_file(target: MemoryFileTarget) -> dict[str, Any]:
    path = memory_path(target)
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        content = ""
    except OSError:
        raise HTTPException(500, f"failed to read {MEMORY_FILE_DEFS[target]['label']}") from None
    return file_stats(target, content)


def memory_files_payload() -> dict[str, Any]:
    return {
        "files": {
            target: read_memory_file(target)
            for target in ("memory", "user")
        },
        "settings": memory_settings_payload(),
    }


def save_memory_file(target: MemoryFileTarget, content: str) -> dict[str, Any]:
    if target not in MEMORY_FILE_DEFS:
        raise HTTPException(400, "unknown memory file")
    if "\x00" in content:
        raise HTTPException(400, "content cannot contain NUL bytes")

    def _write():
        atomic_write_text(memory_path(target), content, f".{target}_")
        return read_memory_file(target)

    try:
        return with_memory_lock(target, _write)
    except OSError as exc:
        raise HTTPException(500, f"failed to write {MEMORY_FILE_DEFS[target]['label']}: {exc}") from exc


def pending_record_path(pending_id: str) -> Path:
    safe_id = pending_id.strip()
    if not safe_id or "/" in safe_id or "\\" in safe_id or safe_id in {".", ".."}:
        raise HTTPException(400, "invalid pending id")
    return pending_memory_dir() / f"{safe_id}.json"


def list_pending_memory_writes() -> list[dict[str, Any]]:
    directory = pending_memory_dir()
    if not directory.exists():
        return []
    records: list[dict[str, Any]] = []
    for path in directory.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
            records.append(
                {
                    "id": str(data.get("id") or path.stem),
                    "subsystem": str(data.get("subsystem") or "memory"),
                    "action": str(data.get("action") or payload.get("action") or ""),
                    "summary": str(data.get("summary") or ""),
                    "origin": str(data.get("origin") or "foreground"),
                    "created_at": data.get("created_at", 0),
                    "payload": payload,
                }
            )
    records.sort(key=lambda record: record.get("created_at", 0))
    return records


def pending_payload() -> dict[str, Any]:
    records = list_pending_memory_writes()
    return {
        "pending": records,
        "count": len(records),
        "write_approval": memory_settings_payload()["write_approval"],
    }


def stage_pending_memory_write(
    target: MemoryTarget,
    content: str,
    *,
    origin: str = "foreground",
    summary: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if target not in {"memory", "user"}:
        raise HTTPException(400, "target must be memory or user")
    value = content.strip()
    if not value:
        raise HTTPException(400, "content cannot be empty")

    now = datetime.now(timezone.utc)
    pending_id = f"history-{now.strftime('%Y%m%d%H%M%S%f')}"
    payload: dict[str, Any] = {
        "action": "add",
        "target": target,
        "content": value,
    }
    if metadata:
        payload.update({key: item for key, item in metadata.items() if item not in (None, "")})

    record = {
        "id": pending_id,
        "subsystem": "memory",
        "action": "add",
        "summary": summary.strip() or value[:160],
        "origin": origin,
        "created_at": now.timestamp(),
        "payload": payload,
    }
    text = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    try:
        atomic_write_text(pending_record_path(pending_id), text, ".pending_memory_")
    except OSError as exc:
        raise HTTPException(500, f"failed to stage pending memory write: {exc}") from exc
    return record


def _find_entry_index(entries: list[str], old_text: str) -> int:
    matches = [i for i, entry in enumerate(entries) if old_text in entry]
    if not matches:
        raise HTTPException(404, "entry not found")
    if len(matches) > 1:
        raise HTTPException(409, "old_text matches multiple entries")
    return matches[0]


def apply_memory_operation(action: str, target: MemoryTarget, content: str = "", old_text: str = "") -> dict[str, Any]:
    if target not in {"memory", "user"}:
        raise HTTPException(400, "target must be memory or user")
    action = action.strip().lower()

    def _apply():
        entries = read_entries(target)
        if action == "add":
            value = content.strip()
            if not value:
                raise HTTPException(400, "content cannot be empty")
            if value in entries:
                raise HTTPException(409, "duplicate memory entry")
            entries.append(value)
        elif action in {"replace", "remove"}:
            needle = old_text.strip()
            if not needle:
                raise HTTPException(400, "old_text cannot be empty")
            index = _find_entry_index(entries, needle)
            if action == "replace":
                value = content.strip()
                if not value:
                    raise HTTPException(400, "content cannot be empty")
                entries[index] = value
            else:
                entries.pop(index)
        else:
            raise HTTPException(400, f"unknown staged action '{action}'")
        write_entries(target, entries)
        return {"ok": True, "entry_count": len(entries)}

    return with_memory_lock(target, _apply)


def apply_pending_memory_write(pending_id: str) -> dict[str, Any]:
    path = pending_record_path(pending_id)
    if not path.exists():
        raise HTTPException(404, "pending memory write not found")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(400, "pending memory write is unreadable") from None
    payload = record.get("payload") if isinstance(record, dict) else None
    if not isinstance(payload, dict):
        raise HTTPException(400, "pending memory write has no payload")
    action = str(payload.get("action") or "")
    target = str(payload.get("target") or "memory")
    if action == "batch":
        operations = payload.get("operations") if isinstance(payload.get("operations"), list) else []
        result: dict[str, Any] = {"ok": True, "entry_count": 0}
        for operation in operations:
            if not isinstance(operation, dict):
                continue
            result = apply_memory_operation(
                str(operation.get("action") or ""),
                target,  # type: ignore[arg-type]
                str(operation.get("content") or ""),
                str(operation.get("old_text") or ""),
            )
    else:
        result = apply_memory_operation(
            action,
            target,  # type: ignore[arg-type]
            str(payload.get("content") or ""),
            str(payload.get("old_text") or ""),
        )
    try:
        path.unlink()
    except OSError as exc:
        raise HTTPException(500, f"applied but failed to discard pending record: {exc}") from exc
    return {**result, "approved": True, "pending_id": pending_id}


def reject_pending_memory_write(pending_id: str) -> dict[str, Any]:
    if pending_id.strip().lower() == "all":
        count = 0
        for record in list_pending_memory_writes():
            path = pending_record_path(record["id"])
            try:
                path.unlink()
                count += 1
            except OSError:
                continue
        return {"ok": True, "rejected": count}

    path = pending_record_path(pending_id)
    if not path.exists():
        raise HTTPException(404, "pending memory write not found")
    try:
        path.unlink()
    except OSError as exc:
        raise HTTPException(500, f"failed to reject pending record: {exc}") from exc
    return {"ok": True, "rejected": 1, "pending_id": pending_id}
