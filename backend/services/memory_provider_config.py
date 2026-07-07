"""Memory provider configuration helpers."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.services import memory_service
from backend.services.memory_provider_catalog import MEMORY_PROVIDER_OPTIONS

HOST_KEY = "hermes"


def env_path() -> Path:
    return memory_service.hermes_home() / ".env"


def relative_config_path(relative_path: str) -> Path:
    return memory_service.hermes_home() / relative_path


def read_config() -> dict[str, Any]:
    return memory_service.read_config()


def write_config(config: dict[str, Any]) -> None:
    memory_service.write_config(config)


def read_env_values() -> dict[str, str]:
    path = env_path()
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


def write_env_values(updates: dict[str, str]) -> None:
    path = env_path()
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

    memory_service.atomic_write_text(path, "\n".join(next_lines).rstrip() + "\n", ".env_")


def read_json_file(relative_path: str) -> dict[str, Any]:
    path = relative_config_path(relative_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        raise HTTPException(400, f"invalid JSON in {relative_path}: {exc.msg}") from exc
    except OSError:
        raise HTTPException(500, f"failed to read {relative_path}") from None
    return data if isinstance(data, dict) else {}


def write_json_file(relative_path: str, data: dict[str, Any]) -> None:
    path = relative_config_path(relative_path)
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    memory_service.atomic_write_text(path, text, f".{Path(relative_path).name}_")


def json_field_value(provider: str, data: dict[str, Any], field: dict[str, Any]) -> Any:
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


def config_section(config: dict[str, Any], parts: list[str]) -> dict[str, Any]:
    current = config
    for part in parts:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    return current


def yaml_field_value(config: dict[str, Any], field: dict[str, Any]) -> Any:
    current: Any = config
    for part in field.get("section", []):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    if not isinstance(current, dict):
        return None
    return current.get(field["name"])


def coerce_config_value(value: str) -> str | bool | int | float:
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


def validate_config_value(name: str, value: str) -> str:
    value = value.strip()
    if "\n" in value or "\r" in value:
        raise HTTPException(400, f"{name} cannot contain newlines")
    return value


def field_requirement(info: dict[str, Any], field_name: str) -> tuple[str, list[str]]:
    if field_name in info.get("required_fields", []):
        return "required", []
    for group in info.get("required_any", []):
        if field_name in group:
            return "required_any", group
    for mode in info.get("modes", []):
        if field_name in mode.get("required_fields", []):
            return "required", []
        for group in mode.get("required_any", []):
            if field_name in group:
                return "required_any", group
    return "optional", []


def mode_specs(info: dict[str, Any]) -> list[dict[str, Any]]:
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


def default_mode(info: dict[str, Any]) -> str:
    modes = mode_specs(info)
    return modes[0]["id"] if modes else ""


def mode_by_id(info: dict[str, Any], mode_id: str) -> dict[str, Any] | None:
    for mode in mode_specs(info):
        if mode["id"] == mode_id:
            return mode
    return None


def field_mode_ids(info: dict[str, Any], field_name: str) -> list[str]:
    mode_ids = [
        mode["id"]
        for mode in mode_specs(info)
        if field_name in mode.get("fields", [])
    ]
    if mode_ids:
        return mode_ids
    modes = mode_specs(info)
    return [mode["id"] for mode in modes]


def field_specs(info: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []
    for field in info.get("fields", []):
        requirement, required_group = field_requirement(info, field["name"])
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
                "mode_ids": field_mode_ids(info, field["name"]),
            }
        )
    return fields


def provider_config_values(provider: str) -> dict[str, dict[str, Any]]:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    env_values = read_env_values()
    config = read_config()
    json_cache: dict[str, dict[str, Any]] = {}
    values: dict[str, dict[str, Any]] = {}

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
                json_cache[relative_path] = read_json_file(relative_path)
            raw = json_field_value(provider, json_cache[relative_path], field)
            source = relative_path
        elif source == "yaml":
            raw = yaml_field_value(config, field)
            source = "config.yaml"

        configured = raw not in (None, "")
        values[name] = {
            "configured": configured,
            "secret": bool(field.get("secret", False)),
            "source": source,
            "value": "" if field.get("secret") else ("" if raw is None else str(raw)),
        }
    return values


def required_state(
    info: dict[str, Any],
    values: dict[str, dict[str, Any]],
) -> tuple[bool, list[str], list[list[str]]]:
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


def required_state_for_mode(
    info: dict[str, Any],
    values: dict[str, dict[str, Any]],
    mode_id: str,
) -> tuple[bool, list[str], list[list[str]]]:
    mode = mode_by_id(info, mode_id)
    if not mode:
        return required_state(info, values)

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


def current_config_mode(info: dict[str, Any], values: dict[str, dict[str, Any]]) -> str:
    fallback_mode = default_mode(info)
    modes = mode_specs(info)
    if not modes:
        return ""

    configured_mode = values.get("mode", {}).get("value")
    if isinstance(configured_mode, str) and mode_by_id(info, configured_mode):
        return configured_mode

    for field in info.get("fields", []):
        name = field["name"]
        if not values.get(name, {}).get("configured", False):
            continue
        mode_ids = field_mode_ids(info, name)
        if len(mode_ids) == 1:
            return mode_ids[0]

    return fallback_mode


def validate_config_mode(info: dict[str, Any], mode: str) -> str:
    mode = mode.strip()
    if not mode:
        return ""
    if not mode_by_id(info, mode):
        raise HTTPException(400, f"unknown provider config mode: {mode}")
    return mode


def validate_required_provider_config(
    provider: str,
    fields: dict[str, str],
    mode: str = "",
) -> None:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    mode = validate_config_mode(info, mode)
    values = provider_config_values(provider)
    for name, raw_value in fields.items():
        value = str(raw_value).strip()
        if value and name in values:
            values[name] = {
                **values[name],
                "configured": True,
                "value": "" if values[name].get("secret") else value,
            }

    configured, missing_fields, missing_any = (
        required_state_for_mode(info, values, mode) if mode else required_state(info, values)
    )
    if configured:
        return

    missing = [*missing_fields, *[" / ".join(group) for group in missing_any]]
    raise HTTPException(
        400,
        "missing required provider config: " + ", ".join(missing),
    )


def active_memory_provider(config: dict[str, Any]) -> str:
    memory_cfg = config.get("memory", {})
    if not isinstance(memory_cfg, dict):
        return ""
    provider = str(memory_cfg.get("provider") or "").strip()
    return provider if provider in MEMORY_PROVIDER_OPTIONS else ""


def write_honcho_config(updates: dict[str, str]) -> None:
    data = read_json_file("honcho.json")
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
        data[name] = coerce_config_value(value)
        if name in host_fields:
            host[name] = coerce_config_value(value)

    write_json_file("honcho.json", data)


def save_provider_fields(provider: str, fields: dict[str, str], mode: str = "") -> None:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    mode = validate_config_mode(info, mode)
    fields = {name: value for name, value in fields.items()}
    if mode and "mode" in {field["name"] for field in info.get("fields", [])}:
        fields.setdefault("mode", mode)

    specs = {field["name"]: field for field in info.get("fields", [])}
    unknown = [name for name in fields if name not in specs]
    if unknown:
        raise HTTPException(400, f"unknown config field: {unknown[0]}")
    validate_required_provider_config(provider, fields, mode)

    env_updates: dict[str, str] = {}
    json_updates: dict[str, dict[str, str]] = {}
    yaml_updates: list[tuple[dict[str, Any], str]] = []

    for name, raw_value in fields.items():
        spec = specs[name]
        value = validate_config_value(name, str(raw_value))
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
        write_env_values(env_updates)

    for relative_path, updates in json_updates.items():
        if provider == "honcho" and relative_path == "honcho.json":
            write_honcho_config(updates)
            continue
        data = read_json_file(relative_path)
        for name, value in updates.items():
            data[name] = coerce_config_value(value)
        write_json_file(relative_path, data)

    if yaml_updates:
        config = read_config()
        for spec, value in yaml_updates:
            section = config_section(config, spec.get("section", []))
            section[spec["name"]] = coerce_config_value(value)
        write_config(config)
