"""Read-only health checks for memory providers."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any

from backend.services import memory_service
from backend.services import memory_provider_config
from backend.services.memory_provider_catalog import MEMORY_PROVIDER_OPTIONS


def utc_now_iso() -> str:
    return memory_service.utc_now_iso()


def dependency_checks(info: dict[str, Any]) -> list[dict[str, Any]]:
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


def config_file_checks(info: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    for relative_path in info.get("config_files", []):
        is_directory = str(relative_path).endswith("/")
        path = memory_provider_config.relative_config_path(str(relative_path).rstrip("/"))
        checks.append(
            {
                "path": relative_path,
                "kind": "directory" if is_directory else "file",
                "exists": path.is_dir() if is_directory else path.is_file(),
            }
        )
    return checks


def provider_health(
    provider: str,
    *,
    active: bool,
    configured: bool,
    missing_fields: list[str],
    missing_any: list[list[str]],
    dependency_checks: list[dict[str, Any]],
    status_command: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dependencies_ok = all(check["ok"] for check in dependency_checks)
    return {
        "provider": provider,
        "active": active,
        "checked_at": utc_now_iso(),
        "config_files": config_file_checks(MEMORY_PROVIDER_OPTIONS[provider]),
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


def hermes_status_command(hermes_home: Path | None = None) -> dict[str, Any]:
    hermes = shutil.which("hermes")
    status: dict[str, Any] = {
        "ok": False,
        "exit_code": None,
        "output": "",
        "error": "hermes CLI not found on PATH",
        "command": "hermes memory status",
    }
    if not hermes:
        return status

    try:
        completed = subprocess.run(
            [hermes, "memory", "status"],
            cwd=str(hermes_home or memory_service.hermes_home()),
            capture_output=True,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {
            "ok": False,
            "exit_code": None,
            "output": "",
            "error": str(exc),
            "command": "hermes memory status",
        }

    return {
        "ok": completed.returncode == 0,
        "exit_code": completed.returncode,
        "output": completed.stdout.strip(),
        "error": completed.stderr.strip(),
        "command": "hermes memory status",
    }
