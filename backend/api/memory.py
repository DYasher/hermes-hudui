"""Memory endpoints."""

from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Literal

import yaml
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.collectors.memory import collect_memory
from backend.collectors.config import collect_config
from backend.collectors.utils import default_hermes_dir, load_yaml
from .serialize import to_dict

router = APIRouter()

ENTRY_DELIMITER = "\n§\n"
HOST_KEY = "hermes"

MEMORY_PROVIDER_OPTIONS = {
    "honcho": {
        "label": "Honcho",
        "storage": "cloud/self-hosted",
        "dependencies": [{"kind": "python", "name": "honcho"}],
        "config_files": ["honcho.json"],
        "required_any": [["apiKey", "baseUrl"]],
        "required_fields": ["peerName", "workspace", "aiPeer"],
        "fields": [
            {
                "name": "apiKey",
                "label": "API key",
                "storage": "json",
                "path": "honcho.json",
                "secret": True,
                "help": "Honcho Cloud key from app.honcho.dev.",
            },
            {
                "name": "baseUrl",
                "label": "Self-hosted base URL",
                "storage": "json",
                "path": "honcho.json",
                "secret": False,
                "help": "Use this instead of an API key for a self-hosted Honcho instance.",
            },
            {
                "name": "peerName",
                "label": "User peer",
                "storage": "json",
                "path": "honcho.json",
                "secret": False,
                "help": "Human peer identity shared across Hermes profiles.",
            },
            {
                "name": "workspace",
                "label": "Workspace",
                "storage": "json",
                "path": "honcho.json",
                "secret": False,
                "help": "Shared Honcho workspace.",
            },
            {
                "name": "aiPeer",
                "label": "AI peer",
                "storage": "json",
                "path": "honcho.json",
                "secret": False,
                "help": "AI peer identity for this Hermes profile.",
            },
        ],
        "setup_command": "hermes memory setup",
        "config_command": "hermes config set memory.provider honcho",
    },
    "openviking": {
        "label": "OpenViking",
        "storage": "self-hosted",
        "dependencies": [
            {"kind": "python", "name": "openviking"},
            {"kind": "command", "name": "openviking-server"},
        ],
        "required_fields": ["OPENVIKING_ENDPOINT"],
        "required_env": ["OPENVIKING_ENDPOINT"],
        "config_files": [".env"],
        "fields": [
            {
                "name": "OPENVIKING_ENDPOINT",
                "label": "Endpoint",
                "storage": "env",
                "secret": False,
                "help": "Running OpenViking server, for example http://localhost:1933.",
            },
            {
                "name": "OPENVIKING_API_KEY",
                "label": "API key",
                "storage": "env",
                "secret": True,
                "help": "Only needed for authenticated OpenViking servers.",
            },
            {
                "name": "OPENVIKING_AGENT",
                "label": "Agent ID",
                "storage": "env",
                "secret": False,
                "help": "Hermes peer ID for peer-scoped memories.",
            },
            {
                "name": "OPENVIKING_ACCOUNT",
                "label": "Account",
                "storage": "env",
                "secret": False,
                "help": "Optional local/trusted-mode account.",
            },
            {
                "name": "OPENVIKING_USER",
                "label": "User",
                "storage": "env",
                "secret": False,
                "help": "Optional local/trusted-mode user.",
            },
        ],
        "setup_command": "hermes memory setup",
        "config_command": "hermes config set memory.provider openviking",
    },
    "mem0": {
        "label": "Mem0",
        "storage": "cloud/self-hosted",
        "dependencies": [{"kind": "python", "name": "mem0"}],
        "required_any": [["MEM0_API_KEY", "mode"]],
        "required_env": ["MEM0_API_KEY"],
        "config_files": [".env", "mem0.json"],
        "fields": [
            {
                "name": "MEM0_API_KEY",
                "label": "API key",
                "storage": "env",
                "secret": True,
                "help": "Mem0 Platform key. OSS mode can be configured through hermes memory setup.",
            },
            {
                "name": "mode",
                "label": "Mode",
                "storage": "json",
                "path": "mem0.json",
                "secret": False,
                "help": "platform or oss.",
            },
            {
                "name": "user_id",
                "label": "User ID",
                "storage": "json",
                "path": "mem0.json",
                "secret": False,
                "help": "Mem0 user identifier.",
            },
            {
                "name": "agent_id",
                "label": "Agent ID",
                "storage": "json",
                "path": "mem0.json",
                "secret": False,
                "help": "Mem0 agent identifier.",
            },
            {
                "name": "rerank",
                "label": "Rerank",
                "storage": "json",
                "path": "mem0.json",
                "secret": False,
                "help": "true or false; platform mode only.",
            },
        ],
        "setup_command": "hermes memory setup",
        "config_command": "hermes config set memory.provider mem0",
    },
    "hindsight": {
        "label": "Hindsight",
        "storage": "cloud/local",
        "dependencies": [{"kind": "python", "name": "hindsight"}],
        "required_any": [["HINDSIGHT_API_KEY", "mode"]],
        "required_env": ["HINDSIGHT_API_KEY"],
        "config_files": [".env", "hindsight/config.json"],
        "fields": [
            {
                "name": "HINDSIGHT_API_KEY",
                "label": "API key",
                "storage": "env",
                "secret": True,
                "help": "Hindsight Cloud key. Local mode can use provider-specific LLM keys.",
            },
            {
                "name": "mode",
                "label": "Mode",
                "storage": "json",
                "path": "hindsight/config.json",
                "secret": False,
                "help": "cloud or local.",
            },
            {
                "name": "bank_id",
                "label": "Bank ID",
                "storage": "json",
                "path": "hindsight/config.json",
                "secret": False,
                "help": "Memory bank identifier.",
            },
            {
                "name": "recall_budget",
                "label": "Recall budget",
                "storage": "json",
                "path": "hindsight/config.json",
                "secret": False,
                "help": "low, mid, or high.",
            },
            {
                "name": "memory_mode",
                "label": "Memory mode",
                "storage": "json",
                "path": "hindsight/config.json",
                "secret": False,
                "help": "hybrid, context, or tools.",
            },
        ],
        "setup_command": "hermes memory setup",
        "config_command": "hermes config set memory.provider hindsight",
    },
    "holographic": {
        "label": "Holographic",
        "storage": "local",
        "dependencies": [],
        "required_fields": [],
        "config_files": ["config.yaml"],
        "fields": [
            {
                "name": "db_path",
                "label": "SQLite DB path",
                "storage": "yaml",
                "section": ["plugins", "hermes-memory-store"],
                "secret": False,
                "help": "Defaults to $HERMES_HOME/memory_store.db.",
            },
            {
                "name": "auto_extract",
                "label": "Auto extract",
                "storage": "yaml",
                "section": ["plugins", "hermes-memory-store"],
                "secret": False,
                "help": "true or false.",
            },
            {
                "name": "default_trust",
                "label": "Default trust",
                "storage": "yaml",
                "section": ["plugins", "hermes-memory-store"],
                "secret": False,
                "help": "0.0 to 1.0.",
            },
        ],
        "setup_command": "hermes memory setup",
        "config_command": "hermes config set memory.provider holographic",
    },
    "retaindb": {
        "label": "RetainDB",
        "storage": "cloud",
        "dependencies": [{"kind": "python", "name": "requests"}],
        "required_fields": ["RETAINDB_API_KEY"],
        "required_env": ["RETAINDB_API_KEY"],
        "config_files": [".env"],
        "fields": [
            {
                "name": "RETAINDB_API_KEY",
                "label": "API key",
                "storage": "env",
                "secret": True,
                "help": "RetainDB account key.",
            },
        ],
        "setup_command": "hermes memory setup",
        "config_command": "hermes config set memory.provider retaindb",
    },
    "byterover": {
        "label": "ByteRover",
        "storage": "local/cloud",
        "dependencies": [{"kind": "command", "name": "brv"}],
        "required_fields": [],
        "config_files": ["byterover/"],
        "fields": [],
        "setup_command": "hermes memory setup",
        "config_command": "hermes config set memory.provider byterover",
    },
    "supermemory": {
        "label": "Supermemory",
        "storage": "cloud",
        "dependencies": [{"kind": "python", "name": "supermemory"}],
        "required_fields": ["SUPERMEMORY_API_KEY"],
        "required_env": ["SUPERMEMORY_API_KEY"],
        "config_files": [".env", "supermemory.json"],
        "fields": [
            {
                "name": "SUPERMEMORY_API_KEY",
                "label": "API key",
                "storage": "env",
                "secret": True,
                "help": "Supermemory Cloud API key.",
            },
            {
                "name": "SUPERMEMORY_CONTAINER_TAG",
                "label": "Container override",
                "storage": "env",
                "secret": False,
                "help": "Optional override for the configured container tag.",
            },
            {
                "name": "container_tag",
                "label": "Container tag",
                "storage": "json",
                "path": "supermemory.json",
                "secret": False,
                "help": "Supports {identity} for profile-scoped containers.",
            },
            {
                "name": "max_recall_results",
                "label": "Max recall results",
                "storage": "json",
                "path": "supermemory.json",
                "secret": False,
                "help": "Number of recalled items to format into context.",
            },
            {
                "name": "search_mode",
                "label": "Search mode",
                "storage": "json",
                "path": "supermemory.json",
                "secret": False,
                "help": "hybrid, memories, or documents.",
            },
        ],
        "setup_command": "hermes memory setup",
        "config_command": "hermes config set memory.provider supermemory",
    },
    "memori": {
        "label": "Memori",
        "storage": "cloud",
        "dependencies": [
            {"kind": "python", "name": "hermes_memori"},
            {"kind": "command", "name": "hermes-memori"},
        ],
        "required_fields": [],
        "config_files": [],
        "fields": [],
        "setup_command": "hermes memory setup",
        "config_command": "hermes config set memory.provider memori",
        "notes": [
            "Install with: pip install hermes-memori",
            "Run: hermes-memori install",
            "Then run: hermes memory setup",
        ],
    },
}

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


def _field_specs(info: dict) -> list[dict]:
    fields = []
    for field in info.get("fields", []):
        fields.append(
            {
                "name": field["name"],
                "label": field.get("label", field["name"]),
                "storage": field.get("storage", ""),
                "path": field.get("path", field.get("storage", "")),
                "secret": bool(field.get("secret", False)),
                "help": field.get("help", ""),
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


def _active_memory_provider(config: dict) -> str:
    memory_cfg = config.get("memory", {})
    if not isinstance(memory_cfg, dict):
        return ""
    provider = str(memory_cfg.get("provider") or "").strip()
    return provider if provider in MEMORY_PROVIDER_OPTIONS else ""


def _memory_provider_payload() -> dict:
    active_provider = _active_memory_provider(_read_config())
    providers = {}
    for key, info in MEMORY_PROVIDER_OPTIONS.items():
        config_values = _provider_config_values(key)
        configured, missing_fields, missing_any = _required_state(info, config_values)
        checks = _dependency_checks(info)
        dependency_ok = all(check["ok"] for check in checks)
        active = key == active_provider
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
            "active": active,
            "configured": configured,
            "readiness": readiness,
            "missing_fields": missing_fields,
            "missing_any": missing_any,
            "checks": checks,
            "config_fields": _field_specs(info),
            "config_values": config_values,
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
    path = _memory_path(target)
    try:
        content = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return []
    if not content:
        return []
    return [p.strip() for p in content.split("§") if p.strip()]


def _write_entries(target: MemoryTarget, entries: list[str]) -> None:
    """Atomically write entries back to a memory file."""
    path = _memory_path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = ENTRY_DELIMITER.join(entries) + "\n" if entries else ""
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        os.write(fd, content.encode("utf-8"))
        os.close(fd)
        fd = -1
        os.replace(tmp, str(path))
    except Exception:
        if fd >= 0:
            os.close(fd)
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _with_lock(target: MemoryTarget, fn):
    """Execute fn while holding the memory file lock."""
    lock = _lock_path(target)
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.touch(exist_ok=True)
    with open(lock, "r") as lf:
        fcntl.flock(lf, fcntl.LOCK_EX)
        return fn()


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


@router.get("/memory/providers")
def get_memory_providers():
    """External memory provider state.

    Built-in MEMORY.md / USER.md remains active regardless of external provider.
    """
    return _memory_provider_payload()


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
    fields: dict[str, str] = Field(default_factory=dict)


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


def _save_provider_fields(provider: str, fields: dict[str, str]) -> None:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    specs = {field["name"]: field for field in info.get("fields", [])}
    unknown = [name for name in fields if name not in specs]
    if unknown:
        raise HTTPException(400, f"unknown config field: {unknown[0]}")

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
        _save_provider_fields(provider, body.fields)
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

    return {
        "provider": provider,
        "active_provider": _memory_provider_payload()["active_provider"],
        "status_command": status,
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
