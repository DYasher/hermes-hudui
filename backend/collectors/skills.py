"""Scan Hermes skills directory and extract metadata."""

from __future__ import annotations

import os
import re
import hashlib
import json
import shutil
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

from ..cache import get_cached_or_compute
from .models import SkillInfo, SkillsState
from .providers import (
    _available_key_names as _available_provider_key_names,
    _provider_has_key as _known_provider_has_key,
)
from .utils import default_hermes_dir, load_yaml


_TRANSLATION_PROVIDER_NAMES = {
    "nous": "Nous Portal",
    "openai-codex": "OpenAI Codex",
    "anthropic": "Anthropic Claude",
    "openrouter": "OpenRouter",
    "zai": "Z.AI",
    "google": "Google",
    "xai": "xAI Grok",
}

_EXCLUDED_SKILL_DIRS = {
    ".git",
    ".github",
    ".hub",
    ".archive",
    ".venv",
    "venv",
    "node_modules",
    "site-packages",
    "__pycache__",
    ".tox",
    ".nox",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
_SKILL_SUPPORT_DIRS = {"references", "templates", "assets", "scripts"}
_PLATFORM_MAP = {
    "macos": "darwin",
    "linux": "linux",
    "windows": "win32",
}
_KNOWN_ENVIRONMENTS = {"kanban", "docker", "s6"}


def _iter_skill_index_files(skills_dir: Path):
    """Yield active SKILL.md entrypoints, matching Hermes CLI's index walk."""
    matches: list[Path] = []
    if not skills_dir.exists():
        return
    for root, dirs, files in os.walk(skills_dir, followlinks=True):
        has_skill_md = "SKILL.md" in files
        dirs[:] = [
            dirname
            for dirname in dirs
            if dirname not in _EXCLUDED_SKILL_DIRS
            and not (has_skill_md and dirname in _SKILL_SUPPORT_DIRS)
        ]
        if "SKILL.md" in files:
            matches.append(Path(root) / "SKILL.md")

    for path in sorted(matches, key=lambda item: str(item.relative_to(skills_dir))):
        yield path


def _skill_category_and_name(skill_md: Path, skills_dir: Path) -> tuple[str, str] | None:
    rel = skill_md.relative_to(skills_dir)
    parts = rel.parts[:-1]  # remove SKILL.md
    if len(parts) >= 2:
        return parts[0], parts[-1]
    if len(parts) == 1:
        return "uncategorized", parts[0]
    return None


def _string_field(value) -> str:
    if value is None:
        return ""
    return str(value).strip().strip("'\"")


def _list_field(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, (list, tuple, set)):
        return [_string_field(item).lower() for item in value if _string_field(item)]
    return [_string_field(value).lower()]


def _running_in_termux() -> bool:
    prefix = os.environ.get("PREFIX", "")
    return bool(os.environ.get("TERMUX_VERSION") or "com.termux" in prefix)


def _skill_matches_platform(meta: dict) -> bool:
    platforms = _list_field(meta.get("platforms"))
    if not platforms:
        return True
    current = sys.platform
    is_termux = _running_in_termux()
    for platform in platforms:
        mapped = _PLATFORM_MAP.get(platform, platform)
        if current.startswith(mapped):
            return True
        if is_termux and mapped in {"linux", "termux", "android"}:
            return True
    return False


def _detect_environment(environment: str) -> bool:
    if environment == "kanban":
        return bool(os.environ.get("HERMES_KANBAN_TASK") or os.environ.get("HERMES_KANBAN_BOARD"))
    if environment == "docker":
        return Path("/.dockerenv").exists()
    if environment == "s6":
        return Path("/run/s6").is_dir() or Path("/package/admin/s6-overlay").is_dir()
    return True


def _skill_matches_environment(meta: dict) -> bool:
    environments = _list_field(meta.get("environments"))
    if not environments:
        return True
    for environment in environments:
        if environment not in _KNOWN_ENVIRONMENTS:
            return True
        if _detect_environment(environment):
            return True
    return False


def _parse_skill_md(path: Path) -> dict:
    """Extract frontmatter fields from a SKILL.md file."""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return {}

    info = {}
    body = content

    # Extract YAML frontmatter between --- markers
    fm_match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
    if fm_match:
        frontmatter = load_yaml(fm_match.group(1)) or {}
        body = content[fm_match.end():]
        if isinstance(frontmatter, dict):
            for key in ("name", "description", "version", "author"):
                value = _string_field(frontmatter.get(key))
                if value:
                    info[key] = value
            for key in ("platforms", "environments"):
                if key in frontmatter:
                    info[key] = frontmatter[key]

    # Fallback: extract description from first markdown paragraph
    if "description" not in info:
        lines = body.split("\n")
        for line in lines:
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("#")
                and not stripped.startswith("---")
            ):
                info["description"] = stripped[:120]
                break

    return info


def read_skill_detail(path: str, hermes_dir: str | None = None) -> dict | None:
    """Read a single SKILL.md file if it belongs to the configured skills dir."""
    if hermes_dir is None:
        hermes_dir = default_hermes_dir(hermes_dir)

    skills_dir = (Path(hermes_dir) / "skills").resolve()
    skill_path = Path(path).expanduser().resolve()

    if skill_path.name != "SKILL.md":
        return None
    try:
        skill_path.relative_to(skills_dir)
    except ValueError:
        return None
    if not skill_path.is_file():
        return None

    stat = skill_path.stat()
    rel = skill_path.relative_to(skills_dir)
    parts = rel.parts[:-1]
    if len(parts) >= 2:
        category = parts[0]
        fallback_name = parts[-1]
    elif len(parts) == 1:
        category = "uncategorized"
        fallback_name = parts[0]
    else:
        return None

    content = skill_path.read_text(encoding="utf-8", errors="replace")
    meta = _parse_skill_md(skill_path)

    return {
        "name": meta.get("name", fallback_name),
        "category": category,
        "description": meta.get("description", ""),
        "path": str(skill_path),
        "content": content,
        "modified_at": datetime.fromtimestamp(stat.st_mtime),
        "file_size": stat.st_size,
    }


def _translation_cache_root() -> Path:
    """Return the HUD-owned translation cache root, outside Hermes skills."""
    override = os.environ.get("HERMES_HUD_TRANSLATION_CACHE_DIR")
    if override:
        return Path(override).expanduser()
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg_cache_home).expanduser() if xdg_cache_home else Path.home() / ".cache"
    return base / "hermes-hudui" / "skill-translations"


def _translation_cache_key(
    source_hash: str,
    target_lang: str,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    identity = json.dumps(
        {
            "version": 2,
            "source_hash": source_hash,
            "target_lang": target_lang,
            "provider": (provider or "").strip(),
            "model": (model or "").strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def _translation_cache_path(
    source_hash: str,
    target_lang: str,
    hermes_dir: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> Path:
    """Return the cache file path for a translated skill body."""
    cache_key = _translation_cache_key(source_hash, target_lang, provider, model)
    return _translation_cache_root() / f"{cache_key}.{target_lang}.md"


def _language_detection_text(content: str) -> str:
    """Return prose-ish text for coarse source-language detection."""
    lines: list[str] = []
    in_fence = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith(("```", "~~~")):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not stripped or stripped in {"---", "..."}:
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _detect_skill_source_lang(content: str) -> str:
    """Coarsely detect whether a SKILL.md is primarily Chinese or English."""
    text = _language_detection_text(content)
    cjk_chars = len(re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]", text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    if cjk_chars >= 8 and cjk_chars >= latin_chars * 0.2:
        return "zh"
    return "en"


def _resolve_translation_target(content: str, target_lang: str) -> tuple[str, str]:
    """Resolve requested target into ``(source_lang, target_lang)``."""
    if target_lang not in {"auto", "zh", "en"}:
        raise ValueError("unsupported target language")
    source_lang = _detect_skill_source_lang(content)
    if target_lang == "auto":
        return source_lang, "en" if source_lang == "zh" else "zh"
    return source_lang, target_lang


def _strip_hermes_cli_output(text: str) -> str:
    """Remove common Hermes CLI decoration from quiet-mode output."""
    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if stripped.startswith("session_id:"):
            continue
        if re.match(r"^[╭╮╰╯│─┌┐└┘├┤┬┴┼\s]+$", stripped):
            continue
        if stripped.startswith("│") and stripped.endswith("│"):
            stripped = stripped.strip("│").strip()
        lines.append(stripped)
    return "\n".join(lines).strip()


def _translation_timeout_seconds() -> int | None:
    raw = os.environ.get("HERMES_HUD_TRANSLATE_TIMEOUT", "900")
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        seconds = 900
    return None if seconds <= 0 else seconds


def _translate_markdown_with_hermes(
    content: str,
    target_lang: str,
    provider: str | None = None,
    model: str | None = None,
) -> str:
    """Translate Markdown using the local Hermes CLI."""
    hermes_path = shutil.which("hermes")
    if not hermes_path:
        raise RuntimeError("Hermes CLI not available")

    language = "Simplified Chinese" if target_lang == "zh" else "English"
    readability = (
        "clear, natural Chinese for a Chinese native reader"
        if target_lang == "zh"
        else "clear, natural English for an English reader"
    )
    prompt = f"""Translate this SKILL.md document into {language}.

Return only Markdown. Preserve the original heading structure, lists, tables,
code fences, shell commands, environment variable names, file paths, API names,
and product names. Translate explanatory prose into {readability}. Do not
summarize or omit content.

--- SKILL.md ---
{content}
"""
    cmd = [hermes_path, "chat", "-q", prompt, "-Q", "--source", "tool"]
    provider = (provider or "").strip()
    model = (model or "").strip()
    if provider:
        cmd.extend(["--provider", provider])
    if model:
        cmd.extend(["-m", model])

    timeout = _translation_timeout_seconds()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"translation timed out after {timeout} seconds")
    if result.returncode != 0:
        error = result.stderr.strip() or result.stdout.strip() or "translation failed"
        raise RuntimeError(error)
    translated = _strip_hermes_cli_output(result.stdout)
    if not translated:
        raise RuntimeError("translation produced no content")
    return translated


def translate_skill_detail(
    detail: dict,
    target_lang: str = "auto",
    provider: str | None = None,
    model: str | None = None,
    force: bool = False,
    cache_only: bool = False,
) -> dict:
    """Translate a skill detail payload and cache by content hash."""
    content = str(detail.get("content") or "")
    path = str(detail.get("path") or "")
    source_lang, resolved_target_lang = _resolve_translation_target(content, target_lang)
    provider = (provider or "").strip() or None
    model = (model or "").strip() or None

    source_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    cache_path = _translation_cache_path(
        source_hash,
        resolved_target_lang,
        provider=provider,
        model=model,
    )
    cache_key = _translation_cache_key(
        source_hash, resolved_target_lang, provider, model
    )
    if cache_path.is_file() and not force:
        return {
            "path": path,
            "source_lang": source_lang,
            "target_lang": resolved_target_lang,
            "translation": cache_path.read_text(encoding="utf-8", errors="replace"),
            "cached": True,
            "source_hash": source_hash,
            "provider": provider or "",
            "model": model or "",
            "cache_key": cache_key,
            "cache_miss": False,
            "forced": False,
        }
    if cache_only and not force:
        return {
            "path": path,
            "source_lang": source_lang,
            "target_lang": resolved_target_lang,
            "translation": "",
            "cached": False,
            "source_hash": source_hash,
            "provider": provider or "",
            "model": model or "",
            "cache_key": cache_key,
            "cache_miss": True,
            "forced": False,
        }

    translation = _translate_markdown_with_hermes(
        content,
        resolved_target_lang,
        provider=provider,
        model=model,
    )
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(translation, encoding="utf-8")
    return {
        "path": path,
        "source_lang": source_lang,
        "target_lang": resolved_target_lang,
        "translation": translation,
        "cached": False,
        "source_hash": source_hash,
        "provider": provider or "",
        "model": model or "",
        "cache_key": cache_key,
        "cache_miss": False,
        "forced": bool(force),
    }


def _read_translation_config(hermes_path: Path) -> dict:
    config_path = hermes_path / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        data = load_yaml(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_translation_model_config(hermes_path: Path) -> tuple[str, str]:
    data = _read_translation_config(hermes_path)
    if not isinstance(data, dict):
        return "", ""
    model_cfg = data.get("model")
    if isinstance(model_cfg, str):
        return "", model_cfg.strip()
    if not isinstance(model_cfg, dict):
        return "", ""
    provider = str(model_cfg.get("provider") or "").strip()
    model = str(model_cfg.get("default") or model_cfg.get("model") or "").strip()
    return provider, model


def _read_translation_models_cache(hermes_path: Path) -> dict:
    path = hermes_path / "models_dev_cache.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _model_name(value) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, dict):
        for key in ("id", "model", "name"):
            name = value.get(key)
            if isinstance(name, str) and name.strip():
                return name.strip()
    return ""


def _model_names(entry: dict) -> list[str]:
    models = entry.get("models")
    if isinstance(models, dict):
        return sorted(str(name) for name in models if str(name).strip())
    if isinstance(models, list):
        names = [_model_name(model) for model in models]
        return sorted(name for name in names if name)
    return []


def _configured_translation_providers(config: dict) -> dict[str, dict]:
    providers: dict[str, dict] = {}
    raw_providers = config.get("providers")
    if isinstance(raw_providers, dict):
        for provider_id, entry in raw_providers.items():
            if not isinstance(entry, dict):
                continue
            provider = str(provider_id).strip()
            if provider:
                providers[provider] = entry

    raw_custom = config.get("custom_providers")
    if isinstance(raw_custom, list):
        for entry in raw_custom:
            if not isinstance(entry, dict):
                continue
            provider = str(entry.get("name") or entry.get("id") or "").strip()
            if provider and provider not in providers:
                providers[provider] = entry
    return providers


def _config_entry_has_api_key(entry: dict | None, available_keys: set[str]) -> bool:
    if not isinstance(entry, dict):
        return False
    for key in ("api_key", "apiKey", "key", "token", "access_token"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return True
    for key in ("key_env", "api_key_env", "apiKeyEnv", "env", "token_env"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip() in available_keys:
            return True
    return False


def _auth_entry_has_token(entry, available_keys: set[str]) -> bool:
    if isinstance(entry, str):
        return bool(entry.strip())
    if not isinstance(entry, dict):
        return False
    token = (
        entry.get("access_token")
        or entry.get("api_key")
        or entry.get("token")
        or (entry.get("tokens", {}) or {}).get("access_token")
        or entry.get("agent_key")
    )
    if isinstance(token, str) and token.strip():
        return True
    source = entry.get("source")
    if isinstance(source, str) and source.startswith("env:"):
        return source.split(":", 1)[1] in available_keys
    return False


def _read_translation_auth_provider_ids(
    hermes_path: Path, available_keys: set[str]
) -> set[str]:
    path = hermes_path / "auth.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if not isinstance(data, dict):
        return set()

    provider_ids: set[str] = set()
    for section in ("providers", "credential_pool"):
        raw = data.get(section)
        if not isinstance(raw, dict):
            continue
        for raw_provider, entry in raw.items():
            provider = str(raw_provider).removeprefix("custom:").strip()
            if not provider:
                continue
            if isinstance(entry, list):
                if any(_auth_entry_has_token(item, available_keys) for item in entry):
                    provider_ids.add(provider)
            elif _auth_entry_has_token(entry, available_keys):
                provider_ids.add(provider)
    return provider_ids


def _translation_provider_has_credentials(
    provider_id: str,
    config_entry: dict | None,
    available_keys: set[str],
    auth_provider_ids: set[str],
) -> bool:
    return (
        _config_entry_has_api_key(config_entry, available_keys)
        or provider_id in auth_provider_ids
        or _known_provider_has_key(provider_id, available_keys)
    )


def _provider_models(*entries: dict | None) -> list[str]:
    models: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        models.update(_model_names(entry))
        default_model = entry.get("default_model") or entry.get("default") or entry.get("model")
        if isinstance(default_model, str) and default_model.strip():
            models.add(default_model.strip())
    return sorted(models)


def _provider_display_name(provider_id: str, entry: dict | None = None) -> str:
    if entry:
        name = entry.get("name") or entry.get("display_name") or entry.get("title")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return _TRANSLATION_PROVIDER_NAMES.get(
        provider_id, provider_id.replace("-", " ").title()
    )


def _collect_skill_translation_options(hermes_path: Path) -> dict:
    config = _read_translation_config(hermes_path)
    default_provider, default_model = _read_translation_model_config(hermes_path)
    cache = _read_translation_models_cache(hermes_path)
    configured_providers = _configured_translation_providers(config)
    available_keys = _available_provider_key_names(hermes_path)
    auth_provider_ids = _read_translation_auth_provider_ids(hermes_path, available_keys)

    providers: dict[str, dict] = {}
    provider_ids = set(cache.keys()) | set(configured_providers.keys())
    if default_provider:
        provider_ids.add(default_provider)
    for provider_id in provider_ids:
        entry = cache.get(provider_id)
        config_entry = configured_providers.get(provider_id)
        if entry is not None and not isinstance(entry, dict):
            entry = None
        if config_entry is not None and not isinstance(config_entry, dict):
            config_entry = None
        provider = str(provider_id).strip()
        if not provider:
            continue
        if not _translation_provider_has_credentials(
            provider, config_entry, available_keys, auth_provider_ids
        ):
            continue
        providers[provider] = {
            "id": provider,
            "name": _provider_display_name(provider, config_entry or entry),
            "models": _provider_models(entry, config_entry),
            "is_default": provider == default_provider,
        }

    if default_provider and default_provider in providers:
        provider = providers.setdefault(
            default_provider,
            {
                "id": default_provider,
                "name": _provider_display_name(
                    default_provider, configured_providers.get(default_provider)
                ),
                "models": [],
                "is_default": True,
            },
        )
        provider["is_default"] = True
        if default_model and default_model not in provider["models"]:
            provider["models"] = sorted([*provider["models"], default_model])

    ordered = sorted(
        providers.values(),
        key=lambda provider: (not provider.get("is_default"), provider["name"].lower()),
    )

    return {
        "default_provider": default_provider,
        "default_model": default_model,
        "providers": ordered,
        "cache_dir": str(_translation_cache_root()),
    }


def collect_skill_translation_options(hermes_dir: str | None = None) -> dict:
    hermes_path = Path(default_hermes_dir(hermes_dir))
    return get_cached_or_compute(
        cache_key=f"skill_translation_options:{hermes_path}",
        compute_fn=lambda: _collect_skill_translation_options(hermes_path),
        file_paths=[hermes_path / "config.yaml", hermes_path / "models_dev_cache.json"],
        ttl=60,
    )


def _detect_custom(skill: SkillInfo, bulk_timestamps: set[int]) -> bool:
    """Heuristic: a skill is 'custom' if its mtime doesn't match a bulk install timestamp."""
    # Round to nearest minute for comparison
    skill_minute = int(skill.modified_at.timestamp()) // 60
    return skill_minute not in bulk_timestamps


def _read_disabled_skill_names(hermes_path: Path) -> set[str]:
    config = _read_translation_config(hermes_path)
    skills_cfg = config.get("skills")
    if not isinstance(skills_cfg, dict):
        return set()
    disabled = skills_cfg.get("disabled")
    if isinstance(disabled, str):
        return {disabled}
    if isinstance(disabled, list):
        return {str(name) for name in disabled if str(name).strip()}
    return set()


def _do_collect_skills(skills_dir: Path, disabled_names: set[str] | None = None) -> SkillsState:
    """Actually scan skills directory (internal, uncached)."""
    skills: list[SkillInfo] = []
    mtimes: list[int] = []
    seen_names: set[str] = set()
    disabled_names = disabled_names or set()

    for skill_md in _iter_skill_index_files(skills_dir):
        category_and_name = _skill_category_and_name(skill_md, skills_dir)
        if not category_and_name:
            continue
        category, fallback_name = category_and_name
        stat = skill_md.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime)
        mtime_minute = int(stat.st_mtime) // 60

        meta = _parse_skill_md(skill_md)
        if not _skill_matches_platform(meta):
            continue
        if not _skill_matches_environment(meta):
            continue

        name = meta.get("name", fallback_name)
        if name in seen_names:
            continue
        seen_names.add(name)

        skills.append(
            SkillInfo(
                name=name,
                category=category,
                description=meta.get("description", ""),
                path=str(skill_md),
                modified_at=mtime,
                file_size=stat.st_size,
                enabled=name not in disabled_names,
                version=meta.get("version", ""),
                author=meta.get("author", ""),
            )
        )
        mtimes.append(mtime_minute)

    # Detect bulk install timestamps (most common minute-rounded mtimes)
    if mtimes:
        counter = Counter(mtimes)
        # Any timestamp shared by 5+ skills is likely a bulk install
        bulk_timestamps = {t for t, count in counter.items() if count >= 5}

        for skill in skills:
            skill.is_custom = _detect_custom(skill, bulk_timestamps)

    return SkillsState(skills=skills)


def collect_skills(hermes_dir: str | None = None) -> SkillsState:
    """Collect all skills metadata (cached, invalidates on directory changes)."""
    if hermes_dir is None:
        hermes_dir = default_hermes_dir(hermes_dir)

    hermes_path = Path(hermes_dir)
    skills_dir = hermes_path / "skills"
    if not skills_dir.exists():
        return SkillsState()

    return get_cached_or_compute(
        cache_key=f"skills:{hermes_dir}",
        compute_fn=lambda: _do_collect_skills(
            skills_dir,
            _read_disabled_skill_names(hermes_path),
        ),
        file_paths=[hermes_path / "config.yaml"],
        dir_paths=[skills_dir],
        ttl=60,  # 60 second cache even if unchanged
    )
