"""Memory provider payload assembly."""

from __future__ import annotations

from typing import Any

from backend.services import memory_provider_config
from backend.services import memory_provider_health
from backend.services.memory_provider_catalog import (
    MEMORY_PROVIDER_CAPABILITIES,
    MEMORY_PROVIDER_OPTIONS,
    OFFICIAL_SCHEMA_PROVIDERS,
    provider_group,
)


def provider_capabilities(provider: str) -> dict[str, Any]:
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


def provider_schema_source(provider: str) -> dict[str, Any]:
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


def provider_external_view_info(provider: str) -> dict[str, Any]:
    if provider == "holographic":
        return {
            "available": True,
            "readonly": True,
            "endpoint": "/api/memory/providers/holographic/external",
            "view_type": "facts",
            "reason": "",
        }
    if provider_capabilities(provider).get("external_read_mode") == "provider_summary":
        return {
            "available": True,
            "readonly": True,
            "endpoint": f"/api/memory/providers/{provider}/external",
            "view_type": "summary",
            "reason": "provider_summary",
        }
    return {
        "available": False,
        "readonly": True,
        "endpoint": "",
        "view_type": "",
        "reason": "provider_specific_api_not_configured",
    }


def provider_payload() -> dict[str, Any]:
    active_provider = memory_provider_config.active_memory_provider(
        memory_provider_config.read_config()
    )
    providers: dict[str, Any] = {}
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
            "capabilities": provider_capabilities(key),
            "schema_source": provider_schema_source(key),
            "external_view": provider_external_view_info(key),
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


def provider_export_payload() -> dict[str, Any]:
    payload = provider_payload()
    active_provider = payload["active_provider"]
    redactions: list[str] = []
    providers: dict[str, Any] = {}

    for provider_id, provider in payload["providers"].items():
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
