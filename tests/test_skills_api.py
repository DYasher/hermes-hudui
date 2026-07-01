from __future__ import annotations

import asyncio
import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from fastapi import HTTPException

import backend.api.skills as skills_api
import backend.collectors.skills as skills_collector
from backend.api.skills import get_skill_detail


@pytest.fixture
def hermes_home(tmp_path: Path, monkeypatch) -> Path:
    hermes_home = tmp_path / "hermes-home"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.delenv("HERMES_HUD_TRANSLATION_CACHE_DIR", raising=False)
    return hermes_home


def test_skill_detail_route_is_registered(registered_routes) -> None:
    assert ("GET", "/api/skills/detail") in registered_routes


def test_skill_translation_route_is_registered(registered_routes) -> None:
    assert ("POST", "/api/skills/translate") in registered_routes


def test_skill_translation_options_route_is_registered(registered_routes) -> None:
    assert ("GET", "/api/skills/translation-options") in registered_routes


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
