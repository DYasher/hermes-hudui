"""Read-only health checks for memory providers."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

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
        "runtime": {
            "ok": None,
            "mode": "",
            "reason": "not_run",
            "checks": [],
        },
        "status_command": status_command,
    }


RUNTIME_PROBE_FIELDS: dict[tuple[str, str], dict[str, Any]] = {
    ("cognee", "docker_api"): {
        "field": "COGNEE_API_URL",
        "label": "Cognee API",
        "paths": ["/health", "/"],
    },
    ("cognee", "mcp_http"): {
        "field": "COGNEE_MCP_URL",
        "label": "Cognee MCP",
        "paths": ["/health", "/"],
    },
    ("agentmemory", "rest_server"): {
        "field": "AGENTMEMORY_URL",
        "label": "agentmemory REST",
        "paths": ["/agentmemory/health", "/health", "/"],
    },
    ("memos", "self_hosted"): {
        "field": "MEMOS_BASE_URL",
        "label": "MemOS API",
        "paths": ["/health", "/"],
    },
}


def _join_probe_url(base_url: str, path: str) -> str:
    suffix = path if path.startswith("/") else f"/{path}"
    return base_url.rstrip("/") + suffix


def _http_probe(label: str, base_url: str, paths: list[str]) -> dict[str, Any]:
    last_result: dict[str, Any] | None = None
    for path in paths:
        url = _join_probe_url(base_url, path)
        result: dict[str, Any] = {
            "kind": "http",
            "name": label,
            "url": url,
            "ok": False,
            "status_code": None,
            "error": "",
        }
        response = None
        try:
            request = Request(
                url,
                method="GET",
                headers={"User-Agent": "Hermes-HUD/read-only-memory-probe"},
            )
            response = urlopen(request, timeout=2)
            status_code = int(response.getcode() or 0)
            result["status_code"] = status_code
            result["ok"] = 200 <= status_code < 400
        except HTTPError as exc:
            result["status_code"] = exc.code
            result["error"] = f"HTTP {exc.code}"
        except URLError as exc:
            result["error"] = str(exc.reason)
        except (OSError, TimeoutError, ValueError) as exc:
            result["error"] = str(exc)
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:
                    pass

        if result["ok"]:
            return result
        last_result = result
    return last_result or {
        "kind": "http",
        "name": label,
        "url": base_url,
        "ok": False,
        "status_code": None,
        "error": "no probe paths configured",
    }


def provider_runtime_checks(provider: str) -> dict[str, Any]:
    info = MEMORY_PROVIDER_OPTIONS[provider]
    values = memory_provider_config.provider_config_values(provider)
    mode = memory_provider_config.current_config_mode(info, values)
    probe = RUNTIME_PROBE_FIELDS.get((provider, mode))
    if not probe:
        return {
            "ok": None,
            "mode": mode,
            "reason": "no_read_only_probe_for_mode",
            "checks": [],
        }

    field = str(probe["field"])
    endpoint = str(values.get(field, {}).get("value") or "").strip()
    if not endpoint:
        return {
            "ok": None,
            "mode": mode,
            "reason": "missing_probe_endpoint",
            "checks": [],
        }

    check = _http_probe(str(probe["label"]), endpoint, list(probe.get("paths") or ["/"]))
    return {
        "ok": bool(check["ok"]),
        "mode": mode,
        "reason": "" if check["ok"] else "probe_failed",
        "checks": [check],
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
