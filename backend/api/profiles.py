"""Profiles endpoints."""

from __future__ import annotations

import fcntl
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Body, HTTPException
from pydantic import BaseModel, Field

from backend.cache import clear_cache
from backend.collectors.profiles import collect_profiles
from backend.collectors.utils import default_hermes_dir, load_yaml
from .serialize import to_dict

router = APIRouter()

PROFILE_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
RESERVED_PROFILE_NAMES = {"hermes", "test", "tmp", "root", "sudo"}
HERMES_SUBCOMMAND_NAMES = {
    "chat",
    "model",
    "gateway",
    "setup",
    "whatsapp",
    "login",
    "logout",
    "status",
    "cron",
    "doctor",
    "dump",
    "config",
    "pairing",
    "skills",
    "tools",
    "mcp",
    "sessions",
    "insights",
    "version",
    "update",
    "uninstall",
    "profile",
    "plugins",
    "honcho",
    "acp",
}

PROVIDER_OPTIONS = [
    "openai-codex",
    "anthropic",
    "openrouter",
    "zai",
    "google",
    "xai",
    "custom",
]

TOOLSET_OPTIONS = [
    "hermes-cli",
    "web",
    "browser",
    "terminal",
    "file",
    "code_execution",
    "vision",
    "image_gen",
    "skills",
    "todo",
    "memory",
    "session_search",
    "clarify",
    "delegation",
    "cronjob",
    "messaging",
]


class ProfileModelEdit(BaseModel):
    provider: str = ""
    default: str = ""
    base_url: str = ""
    api_mode: str = ""
    context_length: int | None = None


class ProfileCompressionEdit(BaseModel):
    enabled: bool = False
    summary_provider: str = ""
    summary_model: str = ""


class ProfileEditBody(BaseModel):
    model: ProfileModelEdit = Field(default_factory=ProfileModelEdit)
    toolsets: list[str] = Field(default_factory=list)
    skin: str = ""
    compression: ProfileCompressionEdit = Field(default_factory=ProfileCompressionEdit)
    soul: str = ""


class ProfileCreateBody(BaseModel):
    name: str
    use_default_template: bool = True


class ProfileImportBody(BaseModel):
    name: str
    config_yaml: str
    soul: str = ""


class ProfileDeleteBody(BaseModel):
    confirm_name: str


def _normalize_profile_name(profile_name: str) -> str:
    name = str(profile_name).strip().lower()
    if not name:
        raise HTTPException(status_code=400, detail="profile name cannot be empty")
    return name


def _validate_existing_profile_name(profile_name: str) -> str:
    name = _normalize_profile_name(profile_name)
    if name == "default":
        return name
    if not PROFILE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="invalid profile name")
    if name in RESERVED_PROFILE_NAMES or name in HERMES_SUBCOMMAND_NAMES:
        raise HTTPException(status_code=400, detail="reserved profile name")
    return name


def _profile_dir(profile_name: str) -> Path:
    profile_name = _validate_existing_profile_name(profile_name)
    hermes_dir = Path(default_hermes_dir())
    if profile_name == "default":
        return hermes_dir
    root = hermes_dir / "profiles"
    path = root / profile_name
    try:
        path.relative_to(root)
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except (OSError, ValueError):
        raise HTTPException(status_code=400, detail="invalid profile name") from None
    if path.is_symlink():
        raise HTTPException(status_code=400, detail="profile symlinks are not manageable")
    if not path.is_dir():
        raise HTTPException(status_code=404, detail="profile not found")
    return path


def _hermes_dir() -> Path:
    return Path(default_hermes_dir())


def _profiles_root() -> Path:
    return _hermes_dir() / "profiles"


def _active_profile_path() -> Path:
    return _hermes_dir() / "active_profile"


def _validate_new_profile_name(profile_name: str) -> str:
    name = _normalize_profile_name(profile_name)
    if name == "default":
        raise HTTPException(status_code=409, detail="default profile already exists")
    if not PROFILE_NAME_RE.match(name):
        raise HTTPException(status_code=400, detail="invalid profile name")
    if name in RESERVED_PROFILE_NAMES or name in HERMES_SUBCOMMAND_NAMES:
        raise HTTPException(status_code=400, detail="reserved profile name")
    return name


def _new_profile_dir(profile_name: str) -> Path:
    name = _validate_new_profile_name(profile_name)
    root = _profiles_root()
    path = root / name
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid profile name") from None
    if path.exists():
        raise HTTPException(status_code=409, detail="profile already exists")
    return path


def _read_config(profile_dir: Path) -> dict[str, Any]:
    config_path = profile_dir / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        data = load_yaml(config_path.read_text(encoding="utf-8")) or {}
        return data if isinstance(data, dict) else {}
    except OSError:
        raise HTTPException(status_code=500, detail="failed to read config.yaml") from None


def _read_soul(profile_dir: Path) -> str:
    soul_path = profile_dir / "SOUL.md"
    if not soul_path.exists():
        return ""
    try:
        return soul_path.read_text(encoding="utf-8")
    except OSError:
        raise HTTPException(status_code=500, detail="failed to read SOUL.md") from None


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode if path.exists() else None
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=f".{path.name}_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _with_profile_lock(profile_dir: Path, fn):
    lock_path = profile_dir / ".hud-profile-edit.lock"
    lock_path.touch(exist_ok=True)
    with open(lock_path, "r", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        return fn()


def _with_profiles_lock(fn):
    hermes_dir = _hermes_dir()
    hermes_dir.mkdir(parents=True, exist_ok=True)
    return _with_profile_lock(hermes_dir, fn)


def _read_active_profile_name() -> str:
    try:
        name = _active_profile_path().read_text(encoding="utf-8").strip()
    except (FileNotFoundError, UnicodeDecodeError, OSError):
        return "default"
    if not name:
        return "default"
    return name or "default"


def _clean_list(values: list[str]) -> list[str]:
    seen = set()
    cleaned = []
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        cleaned.append(item)
    return cleaned


def _clean_model(body: ProfileModelEdit) -> dict[str, Any]:
    model: dict[str, Any] = {}
    provider = body.provider.strip()
    default = body.default.strip()
    base_url = body.base_url.strip()
    api_mode = body.api_mode.strip()

    if base_url and not (base_url.startswith("http://") or base_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="base_url must start with http:// or https://")
    if body.context_length is not None and body.context_length < 1:
        raise HTTPException(status_code=400, detail="context_length must be a positive integer")

    if provider:
        model["provider"] = provider
    if default:
        model["default"] = default
    if base_url:
        model["base_url"] = base_url
    if api_mode:
        model["api_mode"] = api_mode
    if body.context_length is not None:
        model["context_length"] = body.context_length

    return model


def _profile_edit_payload(profile_name: str, profile_dir: Path) -> dict[str, Any]:
    config = _read_config(profile_dir)
    model_cfg = config.get("model", {})
    if isinstance(model_cfg, str):
        model_cfg = {"default": model_cfg}
    if not isinstance(model_cfg, dict):
        model_cfg = {}

    display_cfg = config.get("display", {})
    if not isinstance(display_cfg, dict):
        display_cfg = {}

    compression_cfg = config.get("compression", {})
    if not isinstance(compression_cfg, dict):
        compression_cfg = {}

    toolsets = config.get("toolsets", [])
    if isinstance(toolsets, str):
        toolsets = [toolsets]
    if not isinstance(toolsets, list):
        toolsets = []

    return {
        "name": profile_name,
        "model": {
            "provider": str(model_cfg.get("provider") or ""),
            "default": str(model_cfg.get("default") or model_cfg.get("model") or ""),
            "base_url": str(model_cfg.get("base_url") or ""),
            "api_mode": str(model_cfg.get("api_mode") or ""),
            "context_length": model_cfg.get("context_length"),
        },
        "toolsets": [str(t) for t in toolsets],
        "skin": str(display_cfg.get("skin") or ""),
        "compression": {
            "enabled": bool(compression_cfg.get("enabled", False)),
            "summary_provider": str(compression_cfg.get("summary_provider") or ""),
            "summary_model": str(compression_cfg.get("summary_model") or ""),
        },
        "soul": _read_soul(profile_dir),
    }


def _fallback_template_config() -> str:
    return yaml.safe_dump(
        {
            "model": {},
            "toolsets": [],
            "display": {},
            "compression": {"enabled": False},
        },
        sort_keys=False,
        allow_unicode=True,
    )


def _template_files(use_default_template: bool) -> tuple[str, str]:
    if not use_default_template:
        return _fallback_template_config(), ""

    hermes_dir = _hermes_dir()
    config_path = hermes_dir / "config.yaml"
    soul_path = hermes_dir / "SOUL.md"
    config_text = (
        config_path.read_text(encoding="utf-8")
        if config_path.exists()
        else _fallback_template_config()
    )
    soul_text = soul_path.read_text(encoding="utf-8") if soul_path.exists() else ""
    return config_text, soul_text


def _normalize_import_config(text: str) -> str:
    if not text.strip():
        raise HTTPException(status_code=400, detail="config_yaml is required")
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"invalid config_yaml: {exc}") from None
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="config_yaml must contain a mapping")
    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)


def _create_profile_dir(profile_name: str) -> Path:
    profile_dir = _new_profile_dir(profile_name)
    try:
        profile_dir.parent.mkdir(parents=True, exist_ok=True)
        profile_dir.mkdir()
    except FileExistsError:
        raise HTTPException(status_code=409, detail="profile already exists") from None
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"failed to create profile: {exc}") from exc
    return profile_dir


@router.get("/profiles")
async def get_profiles():
    return to_dict(collect_profiles())


@router.get("/profiles/options")
async def profile_options():
    return {
        "providers": PROVIDER_OPTIONS,
        "toolsets": TOOLSET_OPTIONS,
    }


@router.get("/profiles/active")
def get_active_profile():
    return {"active_profile": _read_active_profile_name()}


@router.post("/profiles")
def create_profile(body: ProfileCreateBody):
    profile_name = _validate_new_profile_name(body.name)

    def do_create():
        profile_dir = _create_profile_dir(profile_name)
        try:
            config_text, soul_text = _template_files(body.use_default_template)
            _atomic_write(profile_dir / "config.yaml", config_text)
            _atomic_write(profile_dir / "SOUL.md", soul_text)
            clear_cache()
            return _profile_edit_payload(profile_name, profile_dir)
        except Exception:
            shutil.rmtree(profile_dir, ignore_errors=True)
            raise

    try:
        return _with_profiles_lock(do_create)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"failed to create profile: {exc}") from exc


@router.post("/profiles/import")
def import_profile(body: ProfileImportBody):
    profile_name = _validate_new_profile_name(body.name)

    def do_import():
        profile_dir = _create_profile_dir(profile_name)
        try:
            config_text = _normalize_import_config(body.config_yaml)
            soul = body.soul
            if soul and not soul.endswith("\n"):
                soul += "\n"
            _atomic_write(profile_dir / "config.yaml", config_text)
            _atomic_write(profile_dir / "SOUL.md", soul)
            clear_cache()
            return _profile_edit_payload(profile_name, profile_dir)
        except Exception:
            shutil.rmtree(profile_dir, ignore_errors=True)
            raise

    try:
        return _with_profiles_lock(do_import)
    except HTTPException:
        raise
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"failed to import profile: {exc}") from exc


@router.get("/profiles/{profile_name}/edit")
def get_profile_edit(profile_name: str):
    profile_name = _validate_existing_profile_name(profile_name)
    profile_dir = _profile_dir(profile_name)
    return _profile_edit_payload(profile_name, profile_dir)


@router.put("/profiles/{profile_name}/edit")
def update_profile_edit(profile_name: str, body: ProfileEditBody):
    profile_name = _validate_existing_profile_name(profile_name)
    profile_dir = _profile_dir(profile_name)

    def do_update():
        config = _read_config(profile_dir)
        existing = _profile_edit_payload(profile_name, profile_dir)

        model = _clean_model(body.model)
        if existing["model"].get("default") and not body.model.default.strip():
            raise HTTPException(status_code=400, detail="model cannot be cleared")
        if existing["model"].get("provider") and not body.model.provider.strip():
            raise HTTPException(status_code=400, detail="provider cannot be cleared")
        config["model"] = model
        config["toolsets"] = _clean_list(body.toolsets)

        display = config.get("display", {})
        if not isinstance(display, dict):
            display = {}
        skin = body.skin.strip()
        if skin:
            display["skin"] = skin
        else:
            display.pop("skin", None)
        config["display"] = display

        compression = config.get("compression", {})
        if not isinstance(compression, dict):
            compression = {}
        compression["enabled"] = body.compression.enabled
        summary_provider = body.compression.summary_provider.strip()
        summary_model = body.compression.summary_model.strip()
        if summary_provider:
            compression["summary_provider"] = summary_provider
        else:
            compression.pop("summary_provider", None)
        if summary_model:
            compression["summary_model"] = summary_model
        else:
            compression.pop("summary_model", None)
        config["compression"] = compression

        yaml_text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
        _atomic_write(profile_dir / "config.yaml", yaml_text)
        soul = body.soul
        if soul and not soul.endswith("\n"):
            soul += "\n"
        _atomic_write(profile_dir / "SOUL.md", soul)
        clear_cache()
        return _profile_edit_payload(profile_name, profile_dir)

    try:
        if profile_name == "default":
            return _with_profiles_lock(do_update)
        return _with_profiles_lock(lambda: _with_profile_lock(profile_dir, do_update))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"failed to update profile: {exc}") from exc


@router.post("/profiles/{profile_name}/use")
def use_profile(profile_name: str):
    profile_name = _validate_existing_profile_name(profile_name)
    _profile_dir(profile_name)

    def do_use():
        path = _active_profile_path()
        if profile_name == "default":
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"failed to set active profile: {exc}") from exc
        else:
            _atomic_write(path, f"{profile_name}\n")
        clear_cache()
        return {"active_profile": profile_name}

    return _with_profiles_lock(do_use)


@router.delete("/profiles/{profile_name}")
def delete_profile(profile_name: str, body: ProfileDeleteBody = Body(...)):
    profile_name = _validate_existing_profile_name(profile_name)
    if profile_name == "default":
        raise HTTPException(status_code=400, detail="default profile cannot be deleted")
    if _normalize_profile_name(body.confirm_name) != profile_name:
        raise HTTPException(status_code=400, detail="confirm_name must match profile name")
    profile_dir = _profile_dir(profile_name)

    def do_delete():
        try:
            shutil.rmtree(profile_dir)
        except OSError as exc:
            raise HTTPException(status_code=500, detail=f"failed to delete profile: {exc}") from exc
        if _read_active_profile_name() == profile_name:
            try:
                _active_profile_path().unlink(missing_ok=True)
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"failed to reset active profile: {exc}") from exc
        clear_cache()
        return {"ok": True, "name": profile_name}

    return _with_profiles_lock(do_delete)
