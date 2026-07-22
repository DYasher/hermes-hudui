from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from fastapi import HTTPException

import backend.api.skills as skills_api
import backend.collectors.skills as skills_collector
from backend.cache import clear_cache
from backend.api.skills import get_skill_detail


@pytest.fixture
def hermes_home(tmp_path: Path, monkeypatch) -> Path:
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.delenv("HERMES_HUD_TRANSLATION_CACHE_DIR", raising=False)
    clear_cache()
    return hermes_home


def test_skill_detail_route_is_registered(registered_routes) -> None:
    assert ("GET", "/api/skills/detail") in registered_routes


def test_skill_translation_route_is_registered(registered_routes) -> None:
    assert ("POST", "/api/skills/translate") in registered_routes


def test_skill_translation_options_route_is_registered(registered_routes) -> None:
    assert ("GET", "/api/skills/translation-options") in registered_routes


def test_skill_management_routes_are_registered(registered_routes) -> None:
    assert ("POST", "/api/skills") in registered_routes
    assert ("PUT", "/api/skills/detail") in registered_routes
    assert ("POST", "/api/skills/toggle") in registered_routes
    assert ("DELETE", "/api/skills") in registered_routes
    assert ("GET", "/api/skills/backup") in registered_routes
    assert ("POST", "/api/skills/export") in registered_routes
    assert ("POST", "/api/skills/validate") in registered_routes
    assert ("POST", "/api/skills/move") in registered_routes
    assert ("POST", "/api/skills/duplicate") in registered_routes
    assert ("POST", "/api/skills/import-zip") in registered_routes
    assert ("GET", "/api/skills/market/search") in registered_routes
    assert ("POST", "/api/skills/market/install") in registered_routes


def test_skill_translation_endpoint_runs_blocking_work_off_event_loop() -> None:
    api = Path("backend/api/skills.py").read_text()

    assert "from fastapi.concurrency import run_in_threadpool" in api
    assert "await run_in_threadpool(" in api


def test_get_skill_detail_reads_skill_md_content(hermes_home: Path) -> None:
    skill_md = hermes_home / "skills" / "core" / "debug-helper" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "---\n"
        "name: Debug Helper\n"
        "description: Investigate failures from first principles\n"
        "---\n\n"
        "# Debug Helper\n\n"
        "Use logs, reproduction steps, and source tracing before patching.\n",
        encoding="utf-8",
    )

    detail = asyncio.run(get_skill_detail(path=str(skill_md)))

    assert detail["name"] == "Debug Helper"
    assert detail["category"] == "core"
    assert detail["description"] == "Investigate failures from first principles"
    assert detail["path"] == str(skill_md)
    assert "# Debug Helper" in detail["content"]
    assert detail["file_size"] == skill_md.stat().st_size


def test_get_skill_detail_rejects_paths_outside_skills_dir(hermes_home: Path) -> None:
    outside = hermes_home / "outside" / "SKILL.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("private", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(get_skill_detail(path=str(outside)))

    assert exc.value.status_code == 404


def test_collect_skills_matches_hermes_desktop_dedup_and_platform_rules(
    hermes_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(skills_collector.sys, "platform", "linux")

    local_openclaw = hermes_home / "skills" / "openclaw-imports"
    (local_openclaw / "dogfood").mkdir(parents=True)
    (local_openclaw / "dogfood" / "SKILL.md").write_text(
        "---\n"
        "name: dogfood\n"
        "description: Local duplicate imported from OpenClaw\n"
        "---\n",
        encoding="utf-8",
    )
    (local_openclaw / "create-yourself" / "selves" / "example_me").mkdir(
        parents=True
    )
    (local_openclaw / "create-yourself" / "SKILL.md").write_text(
        "---\n"
        "name: create-yourself\n"
        "description: Main imported skill\n"
        "---\n",
        encoding="utf-8",
    )
    (local_openclaw / "create-yourself" / "selves" / "example_me" / "SKILL.md").write_text(
        "---\n"
        "name: example_me\n"
        "description: Nested example, not a top-level installed skill\n"
        "---\n",
        encoding="utf-8",
    )
    (local_openclaw / "unique-import").mkdir()
    (local_openclaw / "unique-import" / "SKILL.md").write_text(
        "---\n"
        "name: unique-import\n"
        "description: Unique imported skill\n"
        "---\n",
        encoding="utf-8",
    )
    (local_openclaw / "mac-only-import").mkdir()
    (local_openclaw / "mac-only-import" / "SKILL.md").write_text(
        "---\n"
        "name: mac-only-import\n"
        "description: Not available on Linux\n"
        "platforms: [macos]\n"
        "---\n",
        encoding="utf-8",
    )
    (hermes_home / "skills" / "dogfood").mkdir(parents=True)
    (hermes_home / "skills" / "dogfood" / "SKILL.md").write_text(
        "---\n"
        "name: dogfood\n"
        "description: Local builtin-style dogfood skill\n"
        "---\n",
        encoding="utf-8",
    )

    (hermes_home / "skills" / "computer-use").mkdir(parents=True)
    (hermes_home / "skills" / "computer-use" / "SKILL.md").write_text(
        "---\n"
        "name: computer-use\n"
        "description: Root-level skill\n"
        "---\n",
        encoding="utf-8",
    )

    result = skills_collector.collect_skills(str(hermes_home))

    names_by_category = {
        category: sorted(skill.name for skill in skills)
        for category, skills in result.by_category().items()
    }
    assert result.total == 5
    assert names_by_category["uncategorized"] == ["computer-use", "dogfood"]
    assert names_by_category["openclaw-imports"] == [
        "create-yourself",
        "example_me",
        "unique-import",
    ]


def test_get_skill_translation_uses_secured_skill_detail(
    hermes_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert hasattr(skills_api, "SkillTranslationRequest")
    assert hasattr(skills_api, "get_skill_translation")

    skill_md = hermes_home / "skills" / "core" / "debug-helper" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "---\n"
        "name: Debug Helper\n"
        "description: Investigate failures from first principles\n"
        "---\n\n"
        "# Debug Helper\n\n"
        "Use logs before patching.\n",
        encoding="utf-8",
    )

    def fake_translate_skill_detail(
        detail, target_lang="auto", provider=None, model=None, force=False, cache_only=False
    ):
        assert detail["path"] == str(skill_md)
        assert detail["content"].startswith("---")
        assert target_lang == "auto"
        assert provider is None
        assert model is None
        assert force is False
        assert cache_only is False
        return {
            "path": detail["path"],
            "target_lang": "zh",
            "translation": "# 调试助手\n\n先查看日志，再修改代码。",
            "cached": False,
            "source_hash": "abc123",
        }

    async def fake_run_in_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(skills_api, "translate_skill_detail", fake_translate_skill_detail)
    monkeypatch.setattr(skills_api, "run_in_threadpool", fake_run_in_threadpool)

    request = skills_api.SkillTranslationRequest(path=str(skill_md))
    result = asyncio.run(skills_api.get_skill_translation(request))

    assert result["target_lang"] == "zh"
    assert result["translation"].startswith("# 调试助手")
    assert result["cached"] is False


def test_get_skill_translation_forwards_selected_provider_and_model(
    hermes_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    skill_md = hermes_home / "skills" / "core" / "debug-helper" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("# Debug Helper\n\nUse logs before patching.\n", encoding="utf-8")
    seen: dict[str, str | None] = {}

    def fake_translate_skill_detail(
        detail, target_lang="auto", provider=None, model=None, force=False, cache_only=False
    ):
        seen["provider"] = provider
        seen["model"] = model
        seen["force"] = force
        seen["cache_only"] = cache_only
        return {
            "path": detail["path"],
            "source_lang": "en",
            "target_lang": "zh",
            "translation": "# 调试助手\n",
            "cached": False,
            "source_hash": "abc123",
        }

    async def fake_run_in_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(skills_api, "translate_skill_detail", fake_translate_skill_detail)
    monkeypatch.setattr(skills_api, "run_in_threadpool", fake_run_in_threadpool)

    request = skills_api.SkillTranslationRequest(
        path=str(skill_md),
        provider="openrouter",
        model="qwen/qwen3-235b-a22b",
        force=True,
        cache_only=True,
    )
    result = asyncio.run(skills_api.get_skill_translation(request))

    assert result["target_lang"] == "zh"
    assert seen == {
        "provider": "openrouter",
        "model": "qwen/qwen3-235b-a22b",
        "force": True,
        "cache_only": True,
    }


def test_translate_skill_detail_auto_targets_english_for_chinese_content(
    hermes_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = {
        "path": str(hermes_home / "skills" / "core" / "cn-skill" / "SKILL.md"),
        "content": "# 中文技能\n\n这是一个用于读取中文说明的技能。\n",
    }
    calls: list[str] = []

    def fake_translate_markdown(
        content: str, target_lang: str, provider=None, model=None
    ) -> str:
        calls.append(target_lang)
        assert "中文技能" in content
        assert provider is None
        assert model is None
        return "# Chinese Skill\n\nThis is a skill for reading Chinese instructions.\n"

    monkeypatch.setattr(
        skills_collector,
        "_translate_markdown_with_hermes",
        fake_translate_markdown,
    )

    result = skills_collector.translate_skill_detail(detail, "auto")

    assert calls == ["en"]
    assert result["target_lang"] == "en"
    assert result["translation"].startswith("# Chinese Skill")


def test_translate_skill_detail_auto_targets_chinese_for_english_content(
    hermes_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = {
        "path": str(hermes_home / "skills" / "core" / "en-skill" / "SKILL.md"),
        "content": "# English Skill\n\nUse logs before patching code.\n",
    }
    calls: list[str] = []

    def fake_translate_markdown(
        content: str, target_lang: str, provider=None, model=None
    ) -> str:
        calls.append(target_lang)
        assert "English Skill" in content
        assert provider is None
        assert model is None
        return "# 英文技能\n\n修改代码前先查看日志。\n"

    monkeypatch.setattr(
        skills_collector,
        "_translate_markdown_with_hermes",
        fake_translate_markdown,
    )

    result = skills_collector.translate_skill_detail(detail, "auto")

    assert calls == ["zh"]
    assert result["target_lang"] == "zh"
    assert result["translation"].startswith("# 英文技能")


def test_translate_markdown_timeout_reports_readable_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=args[0], timeout=kwargs["timeout"])

    monkeypatch.setattr(skills_collector.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(skills_collector.subprocess, "run", fake_run)

    with pytest.raises(RuntimeError, match="timed out"):
        skills_collector._translate_markdown_with_hermes("# Slow Skill", "zh")


def test_translate_markdown_command_uses_selected_provider_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="# 译文\n", stderr="")

    monkeypatch.setattr(skills_collector.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(skills_collector.subprocess, "run", fake_run)

    result = skills_collector._translate_markdown_with_hermes(
        "# English Skill",
        "zh",
        provider="openrouter",
        model="qwen/qwen3-235b-a22b",
    )

    assert result == "# 译文"
    cmd = captured["cmd"]
    assert cmd[:2] == ["/usr/bin/hermes", "chat"]
    assert cmd[cmd.index("--provider") + 1] == "openrouter"
    assert cmd[cmd.index("-m") + 1] == "qwen/qwen3-235b-a22b"


def test_translation_cache_is_outside_hermes_home_and_model_specific(
    hermes_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = {
        "path": str(hermes_home / "skills" / "core" / "en-skill" / "SKILL.md"),
        "content": "# English Skill\n\nUse logs before patching code.\n",
    }
    calls: list[tuple[str | None, str | None]] = []

    def fake_translate_markdown(
        content: str, target_lang: str, provider=None, model=None
    ) -> str:
        calls.append((provider, model))
        return f"# 译文\n\nprovider={provider} model={model}\n"

    monkeypatch.setattr(
        skills_collector,
        "_translate_markdown_with_hermes",
        fake_translate_markdown,
    )

    first = skills_collector.translate_skill_detail(
        detail, "auto", provider="openrouter", model="cheap-model"
    )
    second = skills_collector.translate_skill_detail(
        detail, "auto", provider="openrouter", model="cheap-model"
    )
    third = skills_collector.translate_skill_detail(
        detail, "auto", provider="openrouter", model="better-model"
    )

    assert calls == [("openrouter", "cheap-model"), ("openrouter", "better-model")]
    assert first["cached"] is False
    assert second["cached"] is True
    assert third["cached"] is False
    source_hash = hashlib.sha256(detail["content"].encode("utf-8")).hexdigest()
    cache_path = skills_collector._translation_cache_path(
        source_hash, "zh", provider="openrouter", model="cheap-model"
    )
    assert cache_path.is_file()
    with pytest.raises(ValueError):
        cache_path.resolve().relative_to(hermes_home.resolve())
    assert "hermes-hudui" in cache_path.parts


def test_translate_skill_detail_cache_only_does_not_call_model(
    hermes_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = {
        "path": str(hermes_home / "skills" / "core" / "en-skill" / "SKILL.md"),
        "content": "# English Skill\n\nUse logs before patching code.\n",
    }

    def fail_translate(*args, **kwargs):
        raise AssertionError("cache-only requests must not call the model")

    monkeypatch.setattr(
        skills_collector,
        "_translate_markdown_with_hermes",
        fail_translate,
    )

    result = skills_collector.translate_skill_detail(
        detail,
        "auto",
        provider="openrouter",
        model="cheap-model",
        cache_only=True,
    )

    assert result["translation"] == ""
    assert result["cached"] is False
    assert result["cache_miss"] is True
    assert result["provider"] == "openrouter"
    assert result["model"] == "cheap-model"


def test_translate_skill_detail_force_overwrites_existing_cache(
    hermes_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = {
        "path": str(hermes_home / "skills" / "core" / "en-skill" / "SKILL.md"),
        "content": "# English Skill\n\nUse logs before patching code.\n",
    }
    source_hash = hashlib.sha256(detail["content"].encode("utf-8")).hexdigest()
    cache_path = skills_collector._translation_cache_path(
        source_hash, "zh", provider="openrouter", model="cheap-model"
    )
    cache_path.parent.mkdir(parents=True)
    cache_path.write_text("# 旧译文\n", encoding="utf-8")

    def fake_translate_markdown(
        content: str, target_lang: str, provider=None, model=None
    ) -> str:
        return "# 新译文\n"

    monkeypatch.setattr(
        skills_collector,
        "_translate_markdown_with_hermes",
        fake_translate_markdown,
    )

    result = skills_collector.translate_skill_detail(
        detail,
        "auto",
        provider="openrouter",
        model="cheap-model",
        force=True,
    )

    assert result["cached"] is False
    assert result["translation"] == "# 新译文\n"
    assert cache_path.read_text(encoding="utf-8") == "# 新译文\n"


def test_get_skill_translation_options_reads_keyed_config_and_models_cache(
    hermes_home: Path,
) -> None:
    (hermes_home / "config.yaml").write_text(
        "model:\n"
        "  provider: openrouter\n"
        "  default: qwen/qwen3-235b-a22b\n"
        "providers:\n"
        "  openrouter:\n"
        "    api_key: test-key\n"
        "    models:\n"
        "      qwen/qwen3-235b-a22b: {}\n"
        "      openrouter-config-model: {}\n"
        "  hahahu:\n"
        "    api_key: test-key\n"
        "    models:\n"
        "      gpt-5.5: {}\n"
        "      gpt-5.4: {}\n",
        encoding="utf-8",
    )
    (hermes_home / "models_dev_cache.json").write_text(
        json.dumps(
            {
                "openrouter": {
                    "name": "OpenRouter",
                    "models": {
                        "qwen/qwen3-235b-a22b": {},
                        "anthropic/claude-sonnet-4": {},
                    },
                },
                "anthropic": {
                    "name": "Anthropic",
                    "models": {"claude-sonnet-4": {}},
                },
                "unconfigured-provider": {
                    "name": "Unconfigured",
                    "models": {"small-model": {}},
                },
            }
        ),
        encoding="utf-8",
    )

    result = asyncio.run(skills_api.get_skill_translation_options())

    assert result["default_provider"] == "openrouter"
    assert result["default_model"] == "qwen/qwen3-235b-a22b"
    providers = {provider["id"]: provider for provider in result["providers"]}
    assert providers["openrouter"]["models"] == [
        "anthropic/claude-sonnet-4",
        "openrouter-config-model",
        "qwen/qwen3-235b-a22b",
    ]
    assert providers["hahahu"]["models"] == ["gpt-5.4", "gpt-5.5"]
    assert "anthropic" not in providers
    assert "unconfigured-provider" not in providers


def test_get_skill_translation_options_extracts_all_model_id_shapes(
    hermes_home: Path,
) -> None:
    (hermes_home / "config.yaml").write_text(
        "providers:\n  mixed-provider:\n    api_key: test-key\n",
        encoding="utf-8",
    )
    (hermes_home / "models_dev_cache.json").write_text(
        json.dumps(
            {
                "mixed-provider": {
                    "name": "Mixed Provider",
                    "models": [
                        "string-model",
                        {"id": "id-model", "name": "Display Model"},
                        {"model": "model-field"},
                        {"name": "name-only"},
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    result = asyncio.run(skills_api.get_skill_translation_options())

    providers = {provider["id"]: provider for provider in result["providers"]}
    assert providers["mixed-provider"]["models"] == [
        "id-model",
        "model-field",
        "name-only",
        "string-model",
    ]


def test_get_skill_translation_rejects_paths_outside_skills_dir(
    hermes_home: Path,
) -> None:
    assert hasattr(skills_api, "SkillTranslationRequest")
    assert hasattr(skills_api, "get_skill_translation")

    outside = hermes_home / "outside" / "SKILL.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("private", encoding="utf-8")

    request = skills_api.SkillTranslationRequest(path=str(outside))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(skills_api.get_skill_translation(request))

    assert exc.value.status_code == 404


def test_save_skill_content_updates_skill_md_and_rejects_outside_paths(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    skill_md = hermes_home / "skills" / "core" / "debug-helper" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("# Debug Helper\n\nOld content.\n", encoding="utf-8")

    result = skills_manager.save_skill_content(
        str(skill_md),
        "# Debug Helper\n\nUpdated content.\n",
    )

    assert skill_md.read_text(encoding="utf-8") == "# Debug Helper\n\nUpdated content.\n"
    assert result["detail"]["content"] == "# Debug Helper\n\nUpdated content.\n"
    backup_path = Path(result["backup_path"])
    assert backup_path.is_file()
    assert backup_path.read_text(encoding="utf-8") == "# Debug Helper\n\nOld content.\n"
    with pytest.raises(ValueError, match="outside"):
        skills_manager.save_skill_content(
            str(hermes_home / "outside" / "SKILL.md"),
            "# Private\n",
        )


def test_validate_skill_content_reports_metadata_references_and_duplicates(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    existing = hermes_home / "skills" / "core" / "existing" / "SKILL.md"
    existing.parent.mkdir(parents=True)
    existing.write_text(
        "---\nname: existing\ndescription: Existing skill\n---\n# Existing\n",
        encoding="utf-8",
    )
    current = hermes_home / "skills" / "core" / "current" / "SKILL.md"
    current.parent.mkdir(parents=True)
    (current.parent / "references").mkdir()
    (current.parent / "references" / "notes.md").write_text("notes", encoding="utf-8")
    current.write_text("# Current\n", encoding="utf-8")
    clear_cache()

    valid = skills_manager.validate_skill_content(
        "---\nname: current\ndescription: Current skill\n---\n"
        "# Current\n\n[Notes](references/notes.md)\n",
        path=str(current),
    )
    assert valid["valid"] is True
    assert valid["errors"] == []
    assert valid["metadata"] == {
        "name": "current",
        "description": "Current skill",
    }

    invalid = skills_manager.validate_skill_content(
        "---\nname: existing\n---\n# Duplicate\n"
        "[Missing](references/missing.md)\n"
        "[Outside](../outside.md)\n",
        path=str(current),
    )
    assert invalid["valid"] is False
    assert {item["code"] for item in invalid["errors"]} == {
        "duplicate_name",
        "unsafe_reference",
    }
    assert {item["code"] for item in invalid["warnings"]} == {
        "missing_description",
        "missing_reference",
    }


def test_validate_skill_content_rejects_malformed_frontmatter() -> None:
    from backend.services import skills_manager

    result = skills_manager.validate_skill_content(
        "---\nname: [broken\n---\n# Broken\n"
    )

    assert result["valid"] is False
    assert result["errors"][0]["code"] == "invalid_frontmatter"


def test_save_skill_content_blocks_validation_errors_without_writing(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    skill = hermes_home / "skills" / "core" / "validated" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    original = "---\nname: validated\ndescription: Valid\n---\n# Valid\n"
    skill.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="validation failed"):
        skills_manager.save_skill_content(
            str(skill),
            "---\nname: [broken\n---\n# Broken\n",
        )

    assert skill.read_text(encoding="utf-8") == original


def test_create_skill_writes_safe_skill_md_template(hermes_home: Path) -> None:
    from backend.services import skills_manager

    result = skills_manager.create_skill(
        category="data-science",
        name="notebook-helper",
        description="Help with notebook analysis.",
        content="",
    )

    skill_path = hermes_home / "skills" / "data-science" / "notebook-helper" / "SKILL.md"
    assert result["detail"]["path"] == str(skill_path)
    text = skill_path.read_text(encoding="utf-8")
    assert "name: notebook-helper" in text
    assert "description: Help with notebook analysis." in text
    assert "# notebook-helper" in text

    with pytest.raises(ValueError, match="safe slug"):
        skills_manager.create_skill(
            category="../escape",
            name="bad",
            description="bad",
            content="",
        )


def test_skill_enabled_state_is_collected_from_config_and_can_be_toggled(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    skill_md = hermes_home / "skills" / "core" / "debug-helper" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "---\nname: debug-helper\ndescription: Debug things\n---\n",
        encoding="utf-8",
    )
    (hermes_home / "config.yaml").write_text(
        "model:\n  provider: openrouter\nskills:\n  disabled:\n    - debug-helper\n",
        encoding="utf-8",
    )

    disabled_state = skills_collector.collect_skills(str(hermes_home))
    assert disabled_state.skills[0].enabled is False

    enabled = skills_manager.set_skill_enabled("debug-helper", True)
    assert enabled["enabled"] is True
    text = (hermes_home / "config.yaml").read_text(encoding="utf-8")
    assert "provider: openrouter" in text
    assert "debug-helper" not in text

    clear_cache()
    enabled_state = skills_collector.collect_skills(str(hermes_home))
    assert enabled_state.skills[0].enabled is True

    disabled = skills_manager.set_skill_enabled("debug-helper", False)
    assert disabled["enabled"] is False
    assert "debug-helper" in (hermes_home / "config.yaml").read_text(encoding="utf-8")


def test_delete_skill_moves_skill_directory_to_hud_backup(hermes_home: Path) -> None:
    from backend.services import skills_manager

    skill_dir = hermes_home / "skills" / "core" / "debug-helper"
    skill_md = skill_dir / "SKILL.md"
    skill_dir.mkdir(parents=True)
    skill_md.write_text("# Debug Helper\n", encoding="utf-8")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "notes.md").write_text("notes", encoding="utf-8")

    result = skills_manager.delete_skill(str(skill_md))

    assert result["deleted"] is True
    assert not skill_dir.exists()
    backup_path = Path(result["backup_path"])
    assert backup_path.is_dir()
    assert (backup_path / "SKILL.md").read_text(encoding="utf-8") == "# Debug Helper\n"
    assert (backup_path / "references" / "notes.md").read_text(encoding="utf-8") == "notes"
    with pytest.raises(ValueError):
        backup_path.resolve().relative_to(hermes_home.resolve())


def test_move_skill_moves_directory_and_backs_up_source(hermes_home: Path) -> None:
    from backend.services import skills_manager

    source = hermes_home / "skills" / "core" / "debug-helper"
    skill_md = source / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "---\nname: debug-helper\ndescription: Debug\n---\n# Debug\n",
        encoding="utf-8",
    )
    (source / "references").mkdir()
    (source / "references" / "notes.md").write_text("notes", encoding="utf-8")

    result = skills_manager.move_skill(str(skill_md), "research")

    moved = hermes_home / "skills" / "research" / "debug-helper"
    assert result["moved"] is True
    assert result["path"] == str(moved / "SKILL.md")
    assert not source.exists()
    assert (moved / "references" / "notes.md").read_text(encoding="utf-8") == "notes"
    backup = Path(result["backup_path"])
    assert (backup / "SKILL.md").is_file()


def test_move_skill_rejects_conflicts_and_outside_paths(hermes_home: Path) -> None:
    from backend.services import skills_manager

    source = hermes_home / "skills" / "core" / "shared" / "SKILL.md"
    target = hermes_home / "skills" / "research" / "shared" / "SKILL.md"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_text("# Source\n", encoding="utf-8")
    target.write_text("# Target\n", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        skills_manager.move_skill(str(source), "research")
    with pytest.raises(ValueError, match="outside"):
        skills_manager.move_skill(
            str(hermes_home / "outside" / "SKILL.md"),
            "research",
        )


def test_duplicate_skill_copies_support_files_and_updates_name(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    source = hermes_home / "skills" / "core" / "debug-helper"
    skill_md = source / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "---\nname: debug-helper\ndescription: Debug\nversion: 1.2.3\n---\n"
        "# Debug\n\n[Notes](references/notes.md)\n",
        encoding="utf-8",
    )
    (source / "references").mkdir()
    (source / "references" / "notes.md").write_text("notes", encoding="utf-8")

    result = skills_manager.duplicate_skill(
        str(skill_md),
        "research",
        "debug-helper-copy",
    )

    duplicate = hermes_home / "skills" / "research" / "debug-helper-copy"
    copied_text = (duplicate / "SKILL.md").read_text(encoding="utf-8")
    assert result["duplicated"] is True
    assert result["path"] == str(duplicate / "SKILL.md")
    assert "name: debug-helper-copy" in copied_text
    assert "version: 1.2.3" in copied_text
    assert (duplicate / "references" / "notes.md").read_text(encoding="utf-8") == "notes"

    with pytest.raises(FileExistsError, match="already exists"):
        skills_manager.duplicate_skill(
            str(skill_md),
            "research",
            "debug-helper-copy",
        )


def test_duplicate_skill_rejects_symbolic_links(hermes_home: Path) -> None:
    from backend.services import skills_manager

    source = hermes_home / "skills" / "core" / "linked"
    skill_md = source / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text(
        "---\nname: linked\ndescription: Linked\n---\n# Linked\n",
        encoding="utf-8",
    )
    outside = hermes_home / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    (source / "linked.txt").symlink_to(outside)

    with pytest.raises(ValueError, match="symbolic links"):
        skills_manager.duplicate_skill(str(skill_md), "research", "linked-copy")


def test_import_skills_zip_installs_multiple_skills_and_rejects_zip_slip(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "bundle/skills/productivity/alpha/SKILL.md",
            "---\nname: alpha\ndescription: Alpha skill\n---\n# Alpha\n",
        )
        zf.writestr(
            "bundle/skills/research/beta/SKILL.md",
            "---\nname: beta\ndescription: Beta skill\n---\n# Beta\n",
        )
        zf.writestr("bundle/skills/research/beta/references/info.md", "info")

    result = skills_manager.import_skills_zip_bytes(
        archive.getvalue(),
        filename="skills.zip",
    )

    installed = {item["name"]: item for item in result["items"]}
    assert result["installed_count"] == 2
    assert installed["alpha"]["category"] == "productivity"
    assert installed["beta"]["category"] == "research"
    assert (hermes_home / "skills" / "productivity" / "alpha" / "SKILL.md").is_file()
    assert (
        hermes_home
        / "skills"
        / "research"
        / "beta"
        / "references"
        / "info.md"
    ).read_text(encoding="utf-8") == "info"

    malicious = io.BytesIO()
    with zipfile.ZipFile(malicious, "w") as zf:
        zf.writestr("../escape/SKILL.md", "# escape")
    with pytest.raises(ValueError, match="unsafe"):
        skills_manager.import_skills_zip_bytes(
            malicious.getvalue(),
            filename="bad.zip",
        )


def test_preview_skills_zip_classifies_conflicts_without_writing(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    existing_skill = hermes_home / "skills" / "research" / "existing" / "SKILL.md"
    existing_skill.parent.mkdir(parents=True)
    existing_skill.write_text("# Existing\n\nKeep this content.\n", encoding="utf-8")

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "bundle/skills/productivity/new-skill/SKILL.md",
            "# New skill\n",
        )
        zf.writestr(
            "bundle/skills/research/existing/SKILL.md",
            "# Replacement\n",
        )

    skipped_preview = skills_manager.preview_skills_zip_bytes(
        archive.getvalue(),
        filename="bundle.zip",
        overwrite=False,
    )
    skipped_actions = {
        item["name"]: item["status"] for item in skipped_preview["items"]
    }

    assert skipped_preview["preview"] is True
    assert skipped_preview["filename"] == "bundle.zip"
    assert skipped_preview["add_count"] == 1
    assert skipped_preview["overwrite_count"] == 0
    assert skipped_preview["skip_count"] == 1
    assert skipped_actions == {"new-skill": "add", "existing": "skip"}

    overwrite_preview = skills_manager.preview_skills_zip_bytes(
        archive.getvalue(),
        filename="bundle.zip",
        overwrite=True,
    )
    overwrite_actions = {
        item["name"]: item["status"] for item in overwrite_preview["items"]
    }

    assert overwrite_preview["add_count"] == 1
    assert overwrite_preview["overwrite_count"] == 1
    assert overwrite_preview["skip_count"] == 0
    assert overwrite_actions == {"new-skill": "add", "existing": "overwrite"}
    assert not (
        hermes_home / "skills" / "productivity" / "new-skill"
    ).exists()
    assert existing_skill.read_text(encoding="utf-8") == (
        "# Existing\n\nKeep this content.\n"
    )
    backup_root = (
        Path(os.environ["XDG_CACHE_HOME"]) / "hermes-hudui" / "skill-backups"
    )
    assert not backup_root.exists()


def test_zip_preview_reports_validation_and_import_rejects_invalid_skill(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "bundle/skills/research/broken/SKILL.md",
            "---\nname: [broken\n---\n# Broken\n",
        )

    preview = skills_manager.preview_skills_zip_bytes(
        archive.getvalue(),
        filename="broken.zip",
    )
    assert preview["items"][0]["validation"]["valid"] is False
    assert preview["items"][0]["validation"]["errors"][0]["code"] == (
        "invalid_frontmatter"
    )

    with pytest.raises(ValueError, match="validation failed"):
        skills_manager.import_skills_zip_bytes(
            archive.getvalue(),
            filename="broken.zip",
        )


def test_import_skills_zip_overwrites_only_after_preview(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    existing_skill = hermes_home / "skills" / "research" / "existing" / "SKILL.md"
    existing_skill.parent.mkdir(parents=True)
    existing_skill.write_text("# Existing\n", encoding="utf-8")

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "bundle/skills/research/existing/SKILL.md",
            "# Replacement\n",
        )

    result = skills_manager.import_skills_zip_bytes(
        archive.getvalue(),
        filename="bundle.zip",
        overwrite=True,
    )

    assert result["installed_count"] == 1
    assert result["items"][0]["status"] == "overwritten"
    assert existing_skill.read_text(encoding="utf-8") == "# Replacement\n"
    backup_root = (
        Path(os.environ["XDG_CACHE_HOME"]) / "hermes-hudui" / "skill-backups"
    )
    backups = list(backup_root.rglob("SKILL.md"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == "# Existing\n"


def test_backup_skills_bytes_preserves_skill_files_without_writing_hermes_home(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    skill_dir = hermes_home / "skills" / "productivity" / "backup-helper"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("# Backup helper\n", encoding="utf-8")
    (skill_dir / "references").mkdir()
    (skill_dir / "references" / "notes.md").write_text("notes", encoding="utf-8")
    symlink = skill_dir / "references" / "outside.md"
    try:
        symlink.symlink_to(hermes_home / "outside.md")
    except OSError:
        symlink = None

    payload = skills_manager.backup_skills_bytes()

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = set(archive.namelist())
        assert "hermes-skills-backup/skills/productivity/backup-helper/SKILL.md" in names
        assert (
            archive.read(
                "hermes-skills-backup/skills/productivity/backup-helper/references/notes.md"
            )
            == b"notes"
        )
        if symlink is not None:
            assert (
                "hermes-skills-backup/skills/productivity/backup-helper/references/outside.md"
                not in names
            )

    assert not list(hermes_home.glob("*.zip"))


def test_backup_skills_bytes_supports_symlinked_hermes_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services import skills_manager

    real_home = tmp_path / "real-hermes-home"
    real_home.mkdir()
    linked_home = tmp_path / "linked-hermes-home"
    linked_home.symlink_to(real_home, target_is_directory=True)
    monkeypatch.setenv("HERMES_HOME", str(linked_home))
    clear_cache()

    skill = linked_home / "skills" / "research" / "linked-helper" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Linked helper\n", encoding="utf-8")

    payload = skills_manager.backup_skills_bytes()

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert (
            "hermes-skills-backup/skills/research/linked-helper/SKILL.md"
            in archive.namelist()
        )


def test_backup_zip_can_be_previewed_and_restored_with_existing_import_flow(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    skill_md = hermes_home / "skills" / "research" / "restore-helper" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("# Restore helper\n", encoding="utf-8")
    nested_skill = skill_md.parent / "selves" / "nested-helper" / "SKILL.md"
    nested_skill.parent.mkdir(parents=True)
    nested_skill.write_text("# Nested helper\n", encoding="utf-8")

    backup = skills_manager.backup_skills_bytes()
    with zipfile.ZipFile(io.BytesIO(backup)) as archive:
        names = archive.namelist()
        assert len([name for name in names if name.endswith("/SKILL.md")]) == 2
        assert len(names) == len(set(names))
    skill_md.unlink()
    shutil.rmtree(skill_md.parent)

    preview = skills_manager.preview_skills_zip_bytes(
        backup,
        filename="hermes-skills-backup.zip",
        overwrite=True,
    )
    assert preview["add_count"] == 2
    assert {(item["category"], item["name"]) for item in preview["items"]} == {
        ("research", "restore-helper"),
        ("research", "nested-helper"),
    }

    result = skills_manager.import_skills_zip_bytes(
        backup,
        filename="hermes-skills-backup.zip",
        overwrite=True,
    )
    assert result["installed_count"] == 2
    assert skill_md.read_text(encoding="utf-8") == "# Restore helper\n"
    assert (
        hermes_home / "skills" / "research" / "nested-helper" / "SKILL.md"
    ).read_text(encoding="utf-8") == "# Nested helper\n"


def test_export_skills_bytes_includes_only_selected_skills_and_support_files(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    selected = hermes_home / "skills" / "research" / "export-helper" / "SKILL.md"
    selected.parent.mkdir(parents=True)
    selected.write_text("# Export helper\n", encoding="utf-8")
    references = selected.parent / "references"
    references.mkdir()
    (references / "notes.md").write_text("notes", encoding="utf-8")
    (references / "SKILL.md").write_text("# Reference format\n", encoding="utf-8")

    nested = selected.parent / "selves" / "nested-helper" / "SKILL.md"
    nested.parent.mkdir(parents=True)
    nested.write_text("# Nested helper\n", encoding="utf-8")

    unselected = hermes_home / "skills" / "research" / "other-helper" / "SKILL.md"
    unselected.parent.mkdir(parents=True)
    unselected.write_text("# Other helper\n", encoding="utf-8")

    payload = skills_manager.export_skills_bytes([str(selected), str(selected)])

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        assert names.count(
            "hermes-skills-backup/skills/research/export-helper/SKILL.md"
        ) == 1
        assert archive.read(
            "hermes-skills-backup/skills/research/export-helper/references/notes.md"
        ) == b"notes"
        assert archive.read(
            "hermes-skills-backup/skills/research/export-helper/references/SKILL.md"
        ) == b"# Reference format\n"
        assert not any("other-helper" in name for name in names)
        assert not any("nested-helper" in name for name in names)
        assert len(names) == len(set(names))

    preview = skills_manager.preview_skills_zip_bytes(
        payload,
        filename="hermes-skills-export.zip",
    )
    assert len(preview["items"]) == 1
    assert preview["items"][0]["name"] == "export-helper"


def test_export_skills_bytes_rejects_empty_or_outside_paths(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    outside = hermes_home / "outside" / "SKILL.md"
    outside.parent.mkdir(parents=True)
    outside.write_text("# Outside\n", encoding="utf-8")

    with pytest.raises(ValueError, match="at least one skill"):
        skills_manager.export_skills_bytes([])

    with pytest.raises(ValueError, match="outside the Hermes skills directory"):
        skills_manager.export_skills_bytes([str(outside)])


def test_export_skills_bytes_rejects_symlinked_skills_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services import skills_manager

    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    outside_skills = tmp_path / "outside-skills"
    skill = outside_skills / "research" / "secret" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Secret\n", encoding="utf-8")
    (hermes_home / "skills").symlink_to(outside_skills, target_is_directory=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    clear_cache()

    with pytest.raises(ValueError, match="no exportable skills"):
        skills_manager.export_skills_bytes([str(skill)])


def test_export_skills_bytes_excludes_filtered_nested_skill(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    parent = hermes_home / "skills" / "research" / "parent" / "SKILL.md"
    parent.parent.mkdir(parents=True)
    parent.write_text("# Parent\n", encoding="utf-8")
    nested = parent.parent / "selves" / "filtered" / "SKILL.md"
    nested.parent.mkdir(parents=True)
    nested.write_text(
        "---\nname: filtered\nplatforms: [never-current-platform]\n---\n# Filtered\n",
        encoding="utf-8",
    )

    payload = skills_manager.export_skills_bytes([str(parent)])

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        names = archive.namelist()
        assert any(name.endswith("parent/SKILL.md") for name in names)
        assert not any("filtered" in name for name in names)


def test_export_skills_bytes_disambiguates_conflicting_archive_paths(
    hermes_home: Path,
) -> None:
    from backend.services import skills_manager

    first = hermes_home / "skills" / "research" / "group-a" / "same" / "SKILL.md"
    second = hermes_home / "skills" / "research" / "group-b" / "same" / "SKILL.md"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("---\nname: first-same\n---\n# First\n", encoding="utf-8")
    second.write_text("---\nname: second-same\n---\n# Second\n", encoding="utf-8")

    payload = skills_manager.export_skills_bytes([str(first), str(second)])

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        skill_entries = [
            name for name in archive.namelist() if name.endswith("/SKILL.md")
        ]
        assert len(skill_entries) == 2
        assert len(skill_entries) == len(set(skill_entries))

    preview = skills_manager.preview_skills_zip_bytes(
        payload,
        filename="hermes-skills-export.zip",
    )
    assert preview["add_count"] == 2
    assert len({item["path"] for item in preview["items"]}) == 2


def test_read_archive_file_does_not_hide_read_errors(
    hermes_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services import skills_manager

    skill = hermes_home / "skills" / "research" / "read-error" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Read error\n", encoding="utf-8")
    skills_dir = (hermes_home / "skills").resolve()
    real_open = os.open

    def fail_open(path, *args, **kwargs):
        if Path(path) == skills_dir:
            raise PermissionError("permission denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(skills_manager.os, "open", fail_open)
    monkeypatch.setattr(skills_manager.os, "supports_dir_fd", {fail_open})

    with pytest.raises(PermissionError, match="permission denied"):
        skills_manager._read_archive_file(skill, skills_dir)


def test_export_skills_api_returns_downloadable_zip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_export(paths):
        captured["paths"] = paths
        return b"zip payload"

    async def direct_run(func, *args):
        return func(*args)

    monkeypatch.setattr(skills_api, "export_skills_bytes", fake_export)
    monkeypatch.setattr(skills_api, "run_in_threadpool", direct_run)

    request = skills_api.SkillExportRequest(paths=["/skills/one/SKILL.md"])
    response = asyncio.run(skills_api.export_skills(request))

    assert response.body == b"zip payload"
    assert response.media_type == "application/zip"
    assert response.headers["content-disposition"] == (
        'attachment; filename="hermes-skills-export.zip"'
    )
    assert captured["paths"] == ["/skills/one/SKILL.md"]


def test_preview_skills_zip_api_dispatches_without_importing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from starlette.requests import Request

    captured: dict[str, object] = {}

    def fake_preview(data, filename, overwrite):
        captured.update(data=data, filename=filename, overwrite=overwrite)
        return {"preview": True, "items": []}

    def fail_import(*args, **kwargs):
        raise AssertionError("preview request must not import files")

    async def direct_run(func, *args):
        return func(*args)

    async def receive():
        return {"type": "http.request", "body": b"zip payload", "more_body": False}

    monkeypatch.setattr(skills_api, "preview_skills_zip_bytes", fake_preview)
    monkeypatch.setattr(skills_api, "import_skills_zip_bytes", fail_import)
    monkeypatch.setattr(skills_api, "run_in_threadpool", direct_run)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/skills/import-zip",
            "headers": [],
        },
        receive,
    )

    result = asyncio.run(
        skills_api.import_skills_zip(
            request,
            filename="preview.zip",
            overwrite=True,
            preview=True,
        )
    )

    assert result == {"preview": True, "items": []}
    assert captured == {
        "data": b"zip payload",
        "filename": "preview.zip",
        "overwrite": True,
    }


def test_skill_market_search_normalizes_hermes_cli_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services import skills_manager

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "identifier": "official/debug-helper",
                            "name": "debug-helper",
                            "description": "Debug helper",
                            "source": "official",
                        }
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(skills_manager.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(skills_manager.subprocess, "run", fake_run)

    result = skills_manager.search_skill_market(
        "debug",
        source="official",
        limit=5,
    )

    assert captured["cmd"][:4] == ["/usr/bin/hermes", "skills", "search", "--json"]
    assert "--source" in captured["cmd"]
    assert captured["cmd"][-1] == "debug"
    assert result["items"][0]["identifier"] == "official/debug-helper"
    assert result["items"][0]["name"] == "debug-helper"


def test_skill_market_search_marks_installed_skills(
    hermes_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services import skills_manager

    installed_skill = (
        hermes_home / "skills" / "productivity" / "debug-helper" / "SKILL.md"
    )
    installed_skill.parent.mkdir(parents=True)
    installed_skill.write_text(
        "---\nname: Debug Helper\ndescription: Local copy\n---\n",
        encoding="utf-8",
    )

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "identifier": "official/debug-helper",
                            "name": "debug-helper",
                        },
                        {
                            "identifier": "official/new-skill",
                            "name": "new-skill",
                        },
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(skills_manager.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(skills_manager.subprocess, "run", fake_run)

    result = skills_manager.search_skill_market(
        "skill",
        source="official",
        limit=5,
    )
    items = {item["name"]: item for item in result["items"]}

    assert items["debug-helper"]["installed"] is True
    assert items["debug-helper"]["installed_category"] == "productivity"
    assert items["debug-helper"]["installed_path"] == str(installed_skill)
    assert items["new-skill"]["installed"] is False
    assert items["new-skill"]["installed_category"] == ""
    assert items["new-skill"]["installed_path"] == ""


def test_skill_market_reports_local_metadata_and_available_updates(
    hermes_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services import skills_manager

    installed_skill = hermes_home / "skills" / "research" / "versioned" / "SKILL.md"
    installed_skill.parent.mkdir(parents=True)
    installed_skill.write_text(
        "---\nname: versioned\ndescription: Local\nversion: 1.0.0\n"
        "author: Local Team\n---\n# Versioned\n",
        encoding="utf-8",
    )

    def fake_run(cmd, **kwargs):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "results": [
                        {
                            "identifier": "official/versioned",
                            "name": "versioned",
                            "version": "2.0.0",
                        },
                        {
                            "identifier": "official/unversioned",
                            "name": "unversioned",
                            "version": "1.0.0",
                        },
                    ]
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(skills_manager.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(skills_manager.subprocess, "run", fake_run)

    collected = skills_collector.collect_skills(str(hermes_home)).skills[0]
    assert collected.version == "1.0.0"
    assert collected.author == "Local Team"

    items = {
        item["name"]: item
        for item in skills_manager.search_skill_market("version", hermes_dir=str(hermes_home))[
            "items"
        ]
    }
    assert items["versioned"]["installed_version"] == "1.0.0"
    assert items["versioned"]["update_available"] is True
    assert items["unversioned"]["installed_version"] == ""
    assert items["unversioned"]["update_available"] is False


def test_skill_market_install_runs_hermes_install_and_clears_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.services import skills_manager

    captured: dict[str, list[str]] = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="installed", stderr="")

    monkeypatch.setattr(skills_manager.shutil, "which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(skills_manager.subprocess, "run", fake_run)

    result = skills_manager.install_market_skill(
        "official/debug-helper",
        category="productivity",
        force=True,
    )

    assert captured["cmd"] == [
        "/usr/bin/hermes",
        "skills",
        "install",
        "official/debug-helper",
        "--yes",
        "--category",
        "productivity",
        "--force",
    ]
    assert result["installed"] is True
    assert result["identifier"] == "official/debug-helper"
