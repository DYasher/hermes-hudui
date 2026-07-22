"""Safe write operations for Hermes skills."""

from __future__ import annotations

import errno
import hashlib
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
from urllib.parse import unquote, urlsplit

import yaml

from backend.cache import clear_cache
from backend.collectors.skills import collect_skills, read_skill_detail
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
_SKILL_SCAN_EXCLUDED_DIRS = {
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
_MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")


def _hermes_path(hermes_dir: str | None = None) -> Path:
    return Path(default_hermes_dir(hermes_dir)).expanduser().resolve()


def _skills_dir(hermes_dir: str | None = None) -> Path:
    return _hermes_path(hermes_dir) / "skills"


def _source_skills_dir(hermes_dir: str | None = None) -> Path:
    return Path(default_hermes_dir(hermes_dir)).expanduser().absolute() / "skills"


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


def _validation_issue(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _markdown_link_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0] if target else ""
    return unquote(target).split("#", 1)[0]


def validate_skill_content(
    content: str,
    path: str | None = None,
    hermes_dir: str | None = None,
    available_files: set[str] | None = None,
    check_duplicates: bool = True,
) -> dict[str, Any]:
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    metadata: dict[str, str] = {}
    text = str(content or "")

    if not text.strip():
        errors.append(_validation_issue("empty_content", "SKILL.md content is required"))
    elif text.startswith("---"):
        match = re.match(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|$)", text, re.DOTALL)
        if not match:
            errors.append(
                _validation_issue(
                    "invalid_frontmatter",
                    "YAML frontmatter is missing its closing delimiter",
                )
            )
        else:
            try:
                parsed = yaml.safe_load(match.group(1)) or {}
            except yaml.YAMLError:
                parsed = None
            if not isinstance(parsed, dict):
                errors.append(
                    _validation_issue(
                        "invalid_frontmatter",
                        "YAML frontmatter must be a valid mapping",
                    )
                )
            else:
                for field in ("name", "description"):
                    value = str(parsed.get(field) or "").strip()
                    if value:
                        metadata[field] = value
    else:
        warnings.append(
            _validation_issue(
                "missing_frontmatter",
                "SKILL.md does not contain YAML frontmatter",
            )
        )

    name = metadata.get("name", "")
    if not name:
        warnings.append(_validation_issue("missing_name", "frontmatter name is missing"))
    if not metadata.get("description"):
        warnings.append(
            _validation_issue(
                "missing_description",
                "frontmatter description is missing",
            )
        )

    current_path = Path(path).expanduser().resolve() if path else None
    if name and check_duplicates:
        for skill in collect_skills(hermes_dir).skills:
            other_path = Path(skill.path).expanduser().resolve()
            if current_path is not None and other_path == current_path:
                continue
            if skill.name.strip().casefold() == name.casefold():
                errors.append(
                    _validation_issue(
                        "duplicate_name",
                        f"another Skill already uses the name '{name}'",
                    )
                )
                break

    seen_references: set[str] = set()
    for match in _MARKDOWN_LINK.finditer(text):
        target = _markdown_link_target(match.group(1))
        if not target or target in seen_references:
            continue
        seen_references.add(target)
        parsed_target = urlsplit(target)
        if parsed_target.scheme or parsed_target.netloc:
            continue
        pure_target = PurePosixPath(target.replace("\\", "/"))
        if pure_target.is_absolute() or ".." in pure_target.parts:
            errors.append(
                _validation_issue(
                    "unsafe_reference",
                    f"reference escapes the Skill directory: {target}",
                )
            )
            continue

        normalized_target = pure_target.as_posix()
        exists = False
        if available_files is not None:
            exists = normalized_target in available_files
        elif current_path is not None:
            skill_root = current_path.parent.resolve()
            candidate = (skill_root / Path(*pure_target.parts)).resolve()
            if not _path_is_under(candidate, skill_root):
                errors.append(
                    _validation_issue(
                        "unsafe_reference",
                        f"reference escapes the Skill directory: {target}",
                    )
                )
                continue
            exists = candidate.is_file()
        else:
            continue

        if not exists:
            warnings.append(
                _validation_issue(
                    "missing_reference",
                    f"referenced file does not exist: {target}",
                )
            )

    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
        "metadata": metadata,
    }


def save_skill_content(
    path: str,
    content: str,
    hermes_dir: str | None = None,
) -> dict[str, Any]:
    if not str(content or "").strip():
        raise ValueError("content is required")
    skill_path, skills_dir = _resolve_skill_md(path, hermes_dir)
    validation = validate_skill_content(
        content,
        path=str(skill_path),
        hermes_dir=hermes_dir,
    )
    if not validation["valid"]:
        messages = "; ".join(item["message"] for item in validation["errors"])
        raise ValueError(f"skill validation failed: {messages}")
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


def _path_is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _path_contains_symlink(path: Path, root: Path) -> bool:
    """Reject a skill file whose directory tree escapes through a symlink."""
    if root.is_symlink():
        return True
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        return True
    current = root
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            return True
    return False


def _indexed_skill_roots(
    skills_dir: Path,
    hermes_dir: str | None = None,
) -> list[Path]:
    source_skills_dir = _source_skills_dir(hermes_dir)
    seen_roots: set[Path] = set()
    skill_roots: list[Path] = []

    for skill in collect_skills(hermes_dir).skills:
        source_path = Path(skill.path).expanduser().absolute()
        if _path_contains_symlink(source_path, source_skills_dir):
            continue
        skill_path = source_path.resolve()
        if not _path_is_under(skill_path, skills_dir) or not skill_path.is_file():
            continue
        skill_root = skill_path.parent
        if skill_root in seen_roots:
            continue
        seen_roots.add(skill_root)
        skill_roots.append(skill_root)

    return skill_roots


def _discover_skill_roots(skills_dir: Path) -> list[Path]:
    """Find every non-symlink Skill root, including filtered nested Skills."""
    skill_roots: list[Path] = []
    if not skills_dir.is_dir():
        return skill_roots

    for root, dirs, files in os.walk(skills_dir, followlinks=False):
        root_path = Path(root)
        has_skill_md = "SKILL.md" in files
        dirs[:] = sorted(
            dirname
            for dirname in dirs
            if dirname not in _SKILL_SCAN_EXCLUDED_DIRS
            and not (root_path / dirname).is_symlink()
            and not (has_skill_md and dirname in _SKILL_SUPPORT_DIRS)
        )
        skill_path = root_path / "SKILL.md"
        if (
            has_skill_md
            and not skill_path.is_symlink()
            and skill_path.is_file()
        ):
            skill_roots.append(root_path.resolve())

    return skill_roots


def _archive_roots_for_skills(
    skill_roots: list[Path],
    skills_dir: Path,
) -> dict[Path, PurePosixPath]:
    locations: dict[Path, tuple[str, str, Path]] = {}
    reserved: set[tuple[str, str]] = set()
    for skill_root in skill_roots:
        relative_root = skill_root.relative_to(skills_dir)
        if len(relative_root.parts) == 1:
            category, name = "uncategorized", relative_root.parts[0]
        else:
            category, name = relative_root.parts[0], relative_root.parts[-1]
        locations[skill_root] = (category, name, relative_root)
        reserved.add((category, name))

    archive_roots: dict[Path, PurePosixPath] = {}
    used: set[tuple[str, str]] = set()
    sorted_roots = sorted(
        skill_roots,
        key=lambda item: str(item.relative_to(skills_dir)),
    )
    for skill_root in sorted_roots:
        category, preferred_name, relative_root = locations[skill_root]
        archive_name = preferred_name
        if (category, archive_name) in used:
            for attempt in range(100):
                digest = hashlib.sha256(
                    f"{relative_root.as_posix()}:{attempt}".encode("utf-8")
                ).hexdigest()[:8]
                archive_name = f"{preferred_name[:71]}-{digest}"
                if (
                    (category, archive_name) not in used
                    and (category, archive_name) not in reserved
                ):
                    break
            else:
                raise ValueError("could not create a unique skill archive path")

        used.add((category, archive_name))
        archive_roots[skill_root] = PurePosixPath(
            "hermes-skills-backup", "skills", category, archive_name
        )

    return archive_roots


def _read_archive_file(file_path: Path, skills_dir: Path) -> bytes | None:
    """Read a regular file without following symlinks inside the Skills tree."""
    try:
        relative = file_path.relative_to(skills_dir)
    except ValueError:
        return None
    if not relative.parts:
        return None

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    if nofollow and os.open in os.supports_dir_fd:
        directory_fds: list[int] = []
        file_fd: int | None = None
        try:
            current_fd = os.open(
                skills_dir,
                os.O_RDONLY | directory | nofollow,
            )
            directory_fds.append(current_fd)
            for part in relative.parts[:-1]:
                current_fd = os.open(
                    part,
                    os.O_RDONLY | directory | nofollow,
                    dir_fd=current_fd,
                )
                directory_fds.append(current_fd)

            file_fd = os.open(
                relative.parts[-1],
                os.O_RDONLY | nofollow,
                dir_fd=current_fd,
            )
            if not stat.S_ISREG(os.fstat(file_fd).st_mode):
                return None
            with os.fdopen(file_fd, "rb") as handle:
                file_fd = None
                return handle.read()
        except OSError as exc:
            if getattr(exc, "errno", None) == errno.ELOOP:
                return None
            raise
        finally:
            if file_fd is not None:
                os.close(file_fd)
            for directory_fd in reversed(directory_fds):
                os.close(directory_fd)

    try:
        resolved = file_path.resolve(strict=True)
        if file_path.is_symlink() or not _path_is_under(resolved, skills_dir):
            return None
        with file_path.open("rb") as handle:
            if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
                return None
            return handle.read()
    except OSError:
        raise


def _build_skills_zip(
    skill_roots: list[Path],
    indexed_roots: list[Path],
    skills_dir: Path,
) -> bytes:
    archive_entries: set[str] = set()
    archive_roots = _archive_roots_for_skills(skill_roots, skills_dir)

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for skill_root in skill_roots:
            archive_root = archive_roots[skill_root]
            nested_roots = [
                other_root
                for other_root in indexed_roots
                if other_root != skill_root
                and _path_is_under(other_root, skill_root)
            ]

            for root, dirs, files in os.walk(skill_root, followlinks=False):
                root_path = Path(root)
                dirs[:] = sorted(
                    dirname
                    for dirname in dirs
                    if not (root_path / dirname).is_symlink()
                    and (root_path / dirname).resolve() not in nested_roots
                )
                for filename in sorted(files):
                    file_path = root_path / filename
                    if file_path.is_symlink() or not file_path.is_file():
                        continue
                    relative_file = file_path.relative_to(skill_root)
                    archive_path = (
                        archive_root / PurePosixPath(*relative_file.parts)
                    ).as_posix()
                    if archive_path in archive_entries:
                        raise ValueError("skills have conflicting archive paths")
                    archive_entries.add(archive_path)
                    file_data = _read_archive_file(file_path, skills_dir)
                    if file_data is not None:
                        archive.writestr(archive_path, file_data)
    return output.getvalue()


def backup_skills_bytes(hermes_dir: str | None = None) -> bytes:
    """Create an in-memory ZIP of the indexed Skills without touching Hermes home."""
    skills_dir = _skills_dir(hermes_dir).resolve()
    skill_roots = _indexed_skill_roots(skills_dir, hermes_dir)
    discovered_roots = _discover_skill_roots(skills_dir)
    return _build_skills_zip(skill_roots, discovered_roots, skills_dir)


def export_skills_bytes(
    paths: list[str],
    hermes_dir: str | None = None,
) -> bytes:
    """Create an import-compatible ZIP containing only the requested Skills."""
    if not paths:
        raise ValueError("at least one skill path is required")

    skills_dir = _skills_dir(hermes_dir).resolve()
    source_skills_dir = _source_skills_dir(hermes_dir)
    selected_roots: list[Path] = []
    seen_roots: set[Path] = set()

    for path in paths:
        skill_path, resolved_skills_dir = _resolve_skill_md(path, hermes_dir)
        source_path = Path(path).expanduser().absolute()
        if _path_contains_symlink(source_path, source_skills_dir):
            continue
        skill_root = _skill_dir_for_path(skill_path, resolved_skills_dir)
        if skill_root in seen_roots:
            continue
        seen_roots.add(skill_root)
        selected_roots.append(skill_root)

    if not selected_roots:
        raise ValueError("no exportable skills were selected")

    discovered_roots = _discover_skill_roots(skills_dir)
    all_roots = list(dict.fromkeys([*discovered_roots, *selected_roots]))
    return _build_skills_zip(selected_roots, all_roots, skills_dir)


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
            roots.append(root)

    unique_roots: dict[tuple[str, ...], tuple[str, str]] = {}
    for root_parts, category, name in roots:
        if any(
            other_parts != root_parts
            and _is_under_parts(root_parts, other_parts)
            and root_parts[len(other_parts)] in _SKILL_SUPPORT_DIRS
            for other_parts, _, _ in roots
        ):
            continue
        _validate_slug(category, "category")
        _validate_slug(name, "name")
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


def _validate_zip_skill_contents(
    archive: zipfile.ZipFile,
    entries: list[tuple[zipfile.ZipInfo, tuple[str, ...]]],
    unique_roots: dict[tuple[str, ...], tuple[str, str]],
) -> dict[tuple[str, ...], dict[str, Any]]:
    info_by_parts = {parts: info for info, parts in entries}
    validations: dict[tuple[str, ...], dict[str, Any]] = {}
    names: dict[str, list[tuple[str, ...]]] = {}

    for root_parts in unique_roots:
        skill_parts = (*root_parts, "SKILL.md")
        info = info_by_parts[skill_parts]
        try:
            content = archive.read(info).decode("utf-8")
        except UnicodeDecodeError:
            validation = {
                "valid": False,
                "errors": [
                    _validation_issue(
                        "invalid_encoding",
                        "SKILL.md must use UTF-8 encoding",
                    )
                ],
                "warnings": [],
                "metadata": {},
            }
        else:
            available_files = {
                PurePosixPath(*parts[len(root_parts) :]).as_posix()
                for _, parts in entries
                if len(parts) > len(root_parts)
                and _is_under_parts(parts, root_parts)
            }
            validation = validate_skill_content(
                content,
                available_files=available_files,
                check_duplicates=False,
            )
        validations[root_parts] = validation
        name = validation["metadata"].get("name", "").casefold()
        if name:
            names.setdefault(name, []).append(root_parts)

    for duplicate_roots in names.values():
        if len(duplicate_roots) < 2:
            continue
        for root_parts in duplicate_roots:
            validations[root_parts]["errors"].append(
                _validation_issue(
                    "duplicate_name",
                    "multiple imported Skills use the same name",
                )
            )
            validations[root_parts]["valid"] = False

    return validations


def preview_skills_zip_bytes(
    data: bytes,
    filename: str = "skills.zip",
    overwrite: bool = False,
    hermes_dir: str | None = None,
) -> dict[str, Any]:
    _validate_zip_payload(data)
    skills_dir = _skills_dir(hermes_dir)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries, unique_roots = _scan_skill_zip(archive)
        validations = _validate_zip_skill_contents(archive, entries, unique_roots)

    planned = _plan_skill_imports(unique_roots, skills_dir, overwrite)
    items = [
        {
            "name": name,
            "category": category,
            "status": status,
            "path": str(dest_dir / "SKILL.md"),
            "validation": validation,
        }
        for root_parts, category, name, status, dest_dir in planned
        for validation in [validations[root_parts]]
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
        validations = _validate_zip_skill_contents(archive, entries, unique_roots)
        invalid = [
            validation
            for validation in validations.values()
            if not validation["valid"]
        ]
        if invalid:
            messages = "; ".join(
                issue["message"]
                for validation in invalid
                for issue in validation["errors"]
            )
            raise ValueError(f"skill validation failed: {messages}")
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


def _installed_skills_index(
    hermes_dir: str | None = None,
) -> dict[str, dict[str, str]]:
    index: dict[str, dict[str, str]] = {}
    for skill in collect_skills(hermes_dir).skills:
        installed = {
            "category": skill.category,
            "path": skill.path,
        }
        folder_name = Path(skill.path).parent.name
        for name in {skill.name, folder_name}:
            normalized = str(name or "").strip().casefold()
            if normalized:
                index.setdefault(normalized, installed)
    return index


def _mark_installed_market_items(
    items: list[dict[str, str]],
    hermes_dir: str | None = None,
) -> list[dict[str, Any]]:
    installed_index = _installed_skills_index(hermes_dir)
    marked: list[dict[str, Any]] = []
    for item in items:
        identifier_name = item["identifier"].rstrip("/").rsplit("/", 1)[-1]
        installed = None
        for candidate in (item["name"], identifier_name):
            installed = installed_index.get(candidate.strip().casefold())
            if installed:
                break
        marked.append(
            {
                **item,
                "installed": installed is not None,
                "installed_category": installed["category"] if installed else "",
                "installed_path": installed["path"] if installed else "",
            }
        )
    return marked


def search_skill_market(
    query: str,
    source: str = "official",
    limit: int = 20,
    hermes_dir: str | None = None,
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
    items = _mark_installed_market_items(
        _market_items_from_payload(payload)[:limit],
        hermes_dir,
    )
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
