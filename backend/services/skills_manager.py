"""Safe write operations for Hermes skills."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from backend.cache import clear_cache
from backend.collectors.skills import read_skill_detail
from backend.collectors.utils import default_hermes_dir

_SAFE_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
_MARKET_SOURCES = {
    "all",
    "official",
    "skills-sh",
    "well-known",
    "github",
    "clawhub",
    "lobehub",
    "browse-sh",
}
_MAX_ZIP_BYTES = 100 * 1024 * 1024
_MAX_ZIP_FILES = 1000
_MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024


def _hermes_path(hermes_dir: str | None = None) -> Path:
    return Path(default_hermes_dir(hermes_dir)).expanduser().resolve()


def _skills_dir(hermes_dir: str | None = None) -> Path:
    return _hermes_path(hermes_dir) / "skills"


def _cache_base() -> Path:
    xdg_cache_home = os.environ.get("XDG_CACHE_HOME")
    return Path(xdg_cache_home).expanduser() if xdg_cache_home else Path.home() / ".cache"


def _backup_root() -> Path:
    override = os.environ.get("HERMES_HUD_SKILL_BACKUP_DIR")
    if override:
        return Path(override).expanduser()
    return _cache_base() / "hermes-hudui" / "skill-backups"


def _backup_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S-%f")


def _validate_slug(value: str, field: str) -> str:
    value = str(value or "").strip()
    if not _SAFE_SLUG.fullmatch(value):
        raise ValueError(f"{field} must be a safe slug")
    return value


def _validate_skill_name(value: str) -> str:
    value = str(value or "").strip()
    if (
        not value
        or len(value) > 160
        or "\x00" in value
        or "\n" in value
        or "/" in value
        or "\\" in value
        or value in {".", ".."}
    ):
        raise ValueError("skill name is invalid")
    return value


def _resolve_skill_md(path: str, hermes_dir: str | None = None) -> tuple[Path, Path]:
    skills_dir = _skills_dir(hermes_dir).resolve()
    skill_path = Path(path).expanduser().resolve()
    if skill_path.name != "SKILL.md":
        raise ValueError("path must point to a SKILL.md file")
    try:
        skill_path.relative_to(skills_dir)
    except ValueError:
        raise ValueError("skill path is outside the Hermes skills directory") from None
    if not skill_path.is_file():
        raise FileNotFoundError("skill not found")
    return skill_path, skills_dir


def _skill_dir_for_path(skill_path: Path, skills_dir: Path) -> Path:
    try:
        rel = skill_path.parent.resolve().relative_to(skills_dir)
    except ValueError:
        raise ValueError("skill path is outside the Hermes skills directory") from None
    if not rel.parts:
        raise ValueError("invalid skill path")
    return skill_path.parent


def _backup_file(path: Path, skills_dir: Path, operation: str) -> Path:
    rel = path.relative_to(skills_dir)
    backup_path = _backup_root() / operation / _backup_stamp() / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, backup_path)
    return backup_path


def _backup_directory(path: Path, skills_dir: Path, operation: str) -> Path:
    rel = path.relative_to(skills_dir)
    backup_path = _backup_root() / operation / _backup_stamp() / rel
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(path, backup_path)
    return backup_path


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        tmp_path = Path(handle.name)
        handle.write(content)
    tmp_path.replace(path)


def _read_config(config_path: Path) -> dict[str, Any]:
    if not config_path.exists():
        return {}
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError("config.yaml must contain a mapping")
    return data


def _write_config_atomic(config_path: Path, config: dict[str, Any]) -> None:
    text = yaml.safe_dump(config, sort_keys=False, allow_unicode=True)
    _write_text_atomic(config_path, text)


def _default_skill_content(name: str, description: str) -> str:
    frontmatter = yaml.safe_dump(
        {
            "name": name,
            "description": description,
        },
        sort_keys=False,
        allow_unicode=True,
    ).strip()
    body = f"# {name}\n"
    if description:
        body += f"\n{description}\n"
    return f"---\n{frontmatter}\n---\n\n{body}"


def save_skill_content(
    path: str,
    content: str,
    hermes_dir: str | None = None,
) -> dict[str, Any]:
    if not str(content or "").strip():
        raise ValueError("content is required")
    skill_path, skills_dir = _resolve_skill_md(path, hermes_dir)
    backup_path = _backup_file(skill_path, skills_dir, "save")
    _write_text_atomic(skill_path, content)
    clear_cache()
    detail = read_skill_detail(str(skill_path), str(_hermes_path(hermes_dir)))
    return {
        "saved": True,
        "path": str(skill_path),
        "backup_path": str(backup_path),
        "detail": detail,
    }


def create_skill(
    category: str,
    name: str,
    description: str = "",
    content: str = "",
    hermes_dir: str | None = None,
) -> dict[str, Any]:
    category = _validate_slug(category or "uncategorized", "category")
    name = _validate_slug(name, "name")
    description = str(description or "").strip()
    skill_path = _skills_dir(hermes_dir) / category / name / "SKILL.md"
    if skill_path.exists():
        raise FileExistsError("skill already exists")
    body = str(content or "").strip()
    if not body:
        body = _default_skill_content(name, description)
    _write_text_atomic(skill_path, body if body.endswith("\n") else f"{body}\n")
    clear_cache()
    detail = read_skill_detail(str(skill_path), str(_hermes_path(hermes_dir)))
    return {
        "created": True,
        "path": str(skill_path.resolve()),
        "detail": detail,
    }


def set_skill_enabled(
    name: str,
    enabled: bool,
    hermes_dir: str | None = None,
) -> dict[str, Any]:
    name = _validate_skill_name(name)
    hermes_path = _hermes_path(hermes_dir)
    config_path = hermes_path / "config.yaml"
    config = _read_config(config_path)
    skills_cfg = config.get("skills")
    if not isinstance(skills_cfg, dict):
        skills_cfg = {}
        config["skills"] = skills_cfg

    disabled = skills_cfg.get("disabled")
    if isinstance(disabled, str):
        disabled_names = [disabled]
    elif isinstance(disabled, list):
        disabled_names = [str(item) for item in disabled if str(item).strip()]
    else:
        disabled_names = []

    if enabled:
        disabled_names = [item for item in disabled_names if item != name]
    elif name not in disabled_names:
        disabled_names.append(name)

    skills_cfg["disabled"] = sorted(disabled_names)
    _write_config_atomic(config_path, config)
    clear_cache()
    return {
        "name": name,
        "enabled": bool(enabled),
        "disabled": name in skills_cfg["disabled"],
    }


def delete_skill(path: str, hermes_dir: str | None = None) -> dict[str, Any]:
    skill_path, skills_dir = _resolve_skill_md(path, hermes_dir)
    skill_dir = _skill_dir_for_path(skill_path, skills_dir)
    backup_path = _backup_directory(skill_dir, skills_dir, "delete")
    shutil.rmtree(skill_dir)
    clear_cache()
    return {
        "deleted": True,
        "path": str(skill_path),
        "backup_path": str(backup_path),
    }


def _zip_member_parts(name: str) -> tuple[str, ...]:
    pure = PurePosixPath(name)
    if pure.is_absolute():
        raise ValueError("unsafe zip path")
    parts = tuple(part for part in pure.parts if part and part != ".")
    if not parts or any(part == ".." for part in parts):
        raise ValueError("unsafe zip path")
    return parts


def _zip_info_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0o170000
    return mode == stat.S_IFLNK


def _skill_root_from_parts(parts: tuple[str, ...]) -> tuple[tuple[str, ...], str, str] | None:
    if not parts or parts[-1] != "SKILL.md":
        return None
    dirs = parts[:-1]
    if not dirs:
        return None
    if "skills" in dirs:
        idx = len(dirs) - 1 - list(reversed(dirs)).index("skills")
        after = dirs[idx + 1 :]
        if len(after) >= 2:
            category = after[0]
            name = after[-1]
            return dirs, category, name
    if len(dirs) >= 2:
        return dirs, dirs[-2], dirs[-1]
    return dirs, "imported", dirs[-1]


def _is_under_parts(parts: tuple[str, ...], root: tuple[str, ...]) -> bool:
    return len(parts) >= len(root) and parts[: len(root)] == root


def _validate_zip_payload(data: bytes) -> None:
    if len(data) > _MAX_ZIP_BYTES:
        raise ValueError("zip archive is too large")
    if not zipfile.is_zipfile(io.BytesIO(data)):
        raise ValueError("file must be a zip archive")


def _scan_skill_zip(
    archive: zipfile.ZipFile,
) -> tuple[
    list[tuple[zipfile.ZipInfo, tuple[str, ...]]],
    dict[tuple[str, ...], tuple[str, str]],
]:
    infos = archive.infolist()
    if len(infos) > _MAX_ZIP_FILES:
        raise ValueError("zip archive contains too many files")
    if sum(max(info.file_size, 0) for info in infos) > _MAX_UNCOMPRESSED_BYTES:
        raise ValueError("zip archive is too large after extraction")

    entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]] = []
    roots: list[tuple[tuple[str, ...], str, str]] = []
    for info in infos:
        parts = _zip_member_parts(info.filename)
        if _zip_info_is_symlink(info):
            raise ValueError("unsafe zip symlink")
        entries.append((info, parts))
        root = _skill_root_from_parts(parts)
        if root:
            _validate_slug(root[1], "category")
            _validate_slug(root[2], "name")
            roots.append(root)

    unique_roots: dict[tuple[str, ...], tuple[str, str]] = {}
    for root_parts, category, name in roots:
        unique_roots[root_parts] = (category, name)
    if not unique_roots:
        raise ValueError("zip archive does not contain any SKILL.md files")
    return entries, unique_roots


def _plan_skill_imports(
    unique_roots: dict[tuple[str, ...], tuple[str, str]],
    skills_dir: Path,
    overwrite: bool,
) -> list[tuple[tuple[str, ...], str, str, str, Path]]:
    planned = []
    for root_parts, (category, name) in sorted(unique_roots.items()):
        dest_dir = skills_dir / category / name
        if not dest_dir.exists():
            status = "add"
        elif overwrite:
            status = "overwrite"
        else:
            status = "skip"
        planned.append((root_parts, category, name, status, dest_dir))
    return planned


def preview_skills_zip_bytes(
    data: bytes,
    filename: str = "skills.zip",
    overwrite: bool = False,
    hermes_dir: str | None = None,
) -> dict[str, Any]:
    _validate_zip_payload(data)
    skills_dir = _skills_dir(hermes_dir)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        _, unique_roots = _scan_skill_zip(archive)

    planned = _plan_skill_imports(unique_roots, skills_dir, overwrite)
    items = [
        {
            "name": name,
            "category": category,
            "status": status,
            "path": str(dest_dir / "SKILL.md"),
        }
        for _, category, name, status, dest_dir in planned
    ]
    return {
        "preview": True,
        "filename": filename,
        "add_count": sum(1 for item in items if item["status"] == "add"),
        "overwrite_count": sum(
            1 for item in items if item["status"] == "overwrite"
        ),
        "skip_count": sum(1 for item in items if item["status"] == "skip"),
        "items": items,
    }


def import_skills_zip_bytes(
    data: bytes,
    filename: str = "skills.zip",
    overwrite: bool = False,
    hermes_dir: str | None = None,
) -> dict[str, Any]:
    _validate_zip_payload(data)
    skills_dir = _skills_dir(hermes_dir)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries, unique_roots = _scan_skill_zip(archive)
        planned = _plan_skill_imports(unique_roots, skills_dir, overwrite)

        items: list[dict[str, Any]] = []
        for root_parts, category, name, action, dest_dir in planned:
            if action == "skip":
                items.append(
                    {
                        "name": name,
                        "category": category,
                        "status": "skipped",
                        "reason": "exists",
                        "path": str(dest_dir / "SKILL.md"),
                    }
                )
                continue
            if action == "overwrite":
                _backup_directory(dest_dir, skills_dir.resolve(), "import-overwrite")
                shutil.rmtree(dest_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)

            copied = 0
            for info, parts in entries:
                if info.is_dir() or not _is_under_parts(parts, root_parts):
                    continue
                relative_parts = parts[len(root_parts) :]
                if not relative_parts:
                    continue
                target = (dest_dir / Path(*relative_parts)).resolve()
                try:
                    target.relative_to(dest_dir.resolve())
                except ValueError:
                    raise ValueError("unsafe zip path") from None
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                copied += 1

            items.append(
                {
                    "name": name,
                    "category": category,
                    "status": "overwritten" if action == "overwrite" else "installed",
                    "files": copied,
                    "path": str(dest_dir / "SKILL.md"),
                }
            )

    clear_cache()
    return {
        "filename": filename,
        "installed_count": sum(
            1 for item in items if item["status"] in {"installed", "overwritten"}
        ),
        "items": items,
    }


def _hermes_cli() -> str:
    hermes_path = shutil.which("hermes")
    if not hermes_path:
        raise RuntimeError("Hermes CLI not available")
    return hermes_path


def _market_timeout_seconds() -> int:
    raw = os.environ.get("HERMES_HUD_SKILL_MARKET_TIMEOUT", "300")
    try:
        timeout = int(raw)
    except (TypeError, ValueError):
        timeout = 300
    return max(timeout, 1)


def _run_hermes_skills_command(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_market_timeout_seconds(),
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Hermes skills command timed out") from None
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "Hermes skills command failed"
        raise RuntimeError(message)
    return result


def _normalize_market_item(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    identifier = str(
        item.get("identifier")
        or item.get("id")
        or item.get("slug")
        or item.get("name")
        or ""
    ).strip()
    name = str(item.get("name") or identifier).strip()
    if not identifier and not name:
        return None
    return {
        "identifier": identifier or name,
        "name": name or identifier,
        "description": str(item.get("description") or item.get("summary") or "").strip(),
        "source": str(item.get("source") or item.get("registry") or "").strip(),
        "category": str(item.get("category") or "").strip(),
        "version": str(item.get("version") or "").strip(),
    }


def _market_items_from_payload(payload: Any) -> list[dict[str, str]]:
    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = (
            payload.get("results")
            or payload.get("skills")
            or payload.get("items")
            or payload.get("data")
            or []
        )
    else:
        raw_items = []
    if not isinstance(raw_items, list):
        return []
    items = [_normalize_market_item(item) for item in raw_items]
    return [item for item in items if item is not None]


def search_skill_market(
    query: str,
    source: str = "official",
    limit: int = 20,
) -> dict[str, Any]:
    query = str(query or "").strip()
    if not query:
        query = " "
    source = str(source or "official").strip()
    if source not in _MARKET_SOURCES:
        raise ValueError("unsupported skill market source")
    limit = max(1, min(int(limit or 20), 100))

    cmd = [_hermes_cli(), "skills", "search", "--json"]
    if source:
        cmd.extend(["--source", source])
    cmd.append(query)
    result = _run_hermes_skills_command(cmd)
    try:
        payload = json.loads(result.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid Hermes skills search JSON: {exc}") from None
    items = _market_items_from_payload(payload)[:limit]
    return {
        "query": query.strip(),
        "source": source,
        "items": items,
    }


def install_market_skill(
    identifier: str,
    category: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    identifier = str(identifier or "").strip()
    if (
        not identifier
        or identifier.startswith("-")
        or "\x00" in identifier
        or "\n" in identifier
    ):
        raise ValueError("skill identifier is invalid")

    cmd = [_hermes_cli(), "skills", "install", identifier, "--yes"]
    if category:
        cmd.extend(["--category", _validate_slug(category, "category")])
    if force:
        cmd.append("--force")
    result = _run_hermes_skills_command(cmd)
    clear_cache()
    return {
        "installed": True,
        "identifier": identifier,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }
