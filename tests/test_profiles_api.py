"""Write-path tests for the profile editing API (backend/api/profiles.py).

``PUT /api/profiles/{name}/edit`` rewrites a profile's ``config.yaml`` and
``SOUL.md`` via an atomic write under a lock. These cover the corruption- and
safety-sensitive surface: round-trip persistence, valid YAML output, path
traversal / name validation, the "model/provider cannot be silently cleared"
guards, and that rejected edits never touch the on-disk config.

``default_hermes_dir()`` reads ``HERMES_HOME`` at call time, so the profile
tree is built under a tmp dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import HTTPException

from backend.api.profiles import (
    ProfileCompressionEdit,
    ProfileCreateBody,
    ProfileDeleteBody,
    ProfileEditBody,
    ProfileImportBody,
    ProfileModelEdit,
    create_profile,
    delete_profile,
    get_active_profile,
    get_profile_edit,
    import_profile,
    use_profile,
    update_profile_edit,
)
from backend.collectors.utils import load_yaml


@pytest.fixture
def hermes_home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def _seed_profile(home: Path, name: str, config: dict) -> Path:
    profile_dir = home if name == "default" else home / "profiles" / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "config.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False), encoding="utf-8"
    )
    return profile_dir


def test_get_profile_edit_reads_existing_config(hermes_home: Path) -> None:
    _seed_profile(hermes_home, "work", {"model": {"default": "m1"}, "toolsets": ["web"]})

    payload = get_profile_edit("work")
    assert payload["name"] == "work"
    assert payload["model"]["default"] == "m1"
    assert payload["toolsets"] == ["web"]


def test_update_round_trips_config_and_soul(hermes_home: Path) -> None:
    profile_dir = _seed_profile(
        hermes_home, "work", {"model": {"provider": "anthropic", "default": "claude-x"}}
    )

    body = ProfileEditBody(
        model=ProfileModelEdit(
            provider="anthropic", default="claude-opus", context_length=200000
        ),
        toolsets=["web", "file", "web"],  # duplicate is deduped
        skin="blade-runner",
        compression=ProfileCompressionEdit(
            enabled=True, summary_provider="anthropic", summary_model="haiku"
        ),
        soul="You are helpful.",
    )
    result = update_profile_edit("work", body)

    # response reflects the new state
    assert result["model"]["default"] == "claude-opus"
    assert result["model"]["context_length"] == 200000
    assert result["toolsets"] == ["web", "file"]
    assert result["skin"] == "blade-runner"
    assert result["compression"]["enabled"] is True
    assert result["soul"] == "You are helpful.\n"

    # config.yaml is valid YAML with the persisted values
    cfg = load_yaml((profile_dir / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["model"]["default"] == "claude-opus"
    assert cfg["toolsets"] == ["web", "file"]
    assert cfg["display"]["skin"] == "blade-runner"
    assert cfg["compression"]["enabled"] is True
    # SOUL.md written with a trailing newline
    assert (profile_dir / "SOUL.md").read_text(encoding="utf-8") == "You are helpful.\n"


def test_update_default_profile_writes_to_hermes_root(hermes_home: Path) -> None:
    _seed_profile(hermes_home, "default", {"model": {"default": "m"}})

    update_profile_edit(
        "default", ProfileEditBody(model=ProfileModelEdit(default="m2"), soul="hi")
    )

    cfg = load_yaml((hermes_home / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["model"]["default"] == "m2"
    assert (hermes_home / "SOUL.md").read_text(encoding="utf-8") == "hi\n"


def test_invalid_profile_name_is_rejected(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        get_profile_edit("../evil")
    assert exc.value.status_code == 400


def test_unknown_profile_returns_404(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        get_profile_edit("ghost")
    assert exc.value.status_code == 404


def test_cannot_clear_existing_model_default(hermes_home: Path) -> None:
    profile_dir = _seed_profile(
        hermes_home, "work", {"model": {"provider": "anthropic", "default": "claude-x"}}
    )

    body = ProfileEditBody(model=ProfileModelEdit(provider="anthropic", default=""))
    with pytest.raises(HTTPException) as exc:
        update_profile_edit("work", body)
    assert exc.value.status_code == 400

    # the original config must be untouched after a rejected edit
    cfg = load_yaml((profile_dir / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["model"]["default"] == "claude-x"


def test_base_url_must_be_http(hermes_home: Path) -> None:
    _seed_profile(hermes_home, "work", {"model": {"default": "m"}})

    body = ProfileEditBody(model=ProfileModelEdit(default="m", base_url="ftp://nope"))
    with pytest.raises(HTTPException) as exc:
        update_profile_edit("work", body)
    assert exc.value.status_code == 400


def test_update_leaves_no_temp_files(hermes_home: Path) -> None:
    profile_dir = _seed_profile(hermes_home, "work", {"model": {"default": "m"}})

    update_profile_edit(
        "work", ProfileEditBody(model=ProfileModelEdit(default="m2"), soul="hi")
    )

    leftovers = [p.name for p in profile_dir.iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_create_profile_can_copy_default_template(hermes_home: Path) -> None:
    _seed_profile(hermes_home, "default", {"model": {"provider": "anthropic", "default": "claude-x"}})
    (hermes_home / "SOUL.md").write_text("Default soul\n", encoding="utf-8")

    result = create_profile(ProfileCreateBody(name="Work", use_default_template=True))

    assert result["name"] == "work"
    profile_dir = hermes_home / "profiles" / "work"
    cfg = load_yaml((profile_dir / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["model"]["default"] == "claude-x"
    assert (profile_dir / "SOUL.md").read_text(encoding="utf-8") == "Default soul\n"


def test_create_profile_without_template_uses_minimal_config(hermes_home: Path) -> None:
    result = create_profile(ProfileCreateBody(name="blank", use_default_template=False))

    assert result["name"] == "blank"
    cfg = load_yaml((hermes_home / "profiles" / "blank" / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["toolsets"] == []


def test_create_profile_rejects_reserved_official_names(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        create_profile(ProfileCreateBody(name="chat"))
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        create_profile(ProfileCreateBody(name="Root"))
    assert exc.value.status_code == 400


def test_import_profile_validates_and_writes_yaml(hermes_home: Path) -> None:
    result = import_profile(
        ProfileImportBody(
            name="imported",
            config_yaml="model:\n  provider: openai-codex\n  default: gpt-5\n",
            soul="Imported soul",
        )
    )

    profile_dir = hermes_home / "profiles" / "imported"
    cfg = load_yaml((profile_dir / "config.yaml").read_text(encoding="utf-8"))
    assert cfg["model"]["default"] == "gpt-5"
    assert (profile_dir / "SOUL.md").read_text(encoding="utf-8") == "Imported soul\n"
    assert not (profile_dir / ".hud-profile-disabled").exists()


def test_import_profile_rejects_invalid_yaml(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        import_profile(ProfileImportBody(name="bad", config_yaml="model: ["))
    assert exc.value.status_code == 400
    assert not (hermes_home / "profiles" / "bad").exists()


def test_profile_edit_payload_ignores_legacy_hud_disabled_marker(hermes_home: Path) -> None:
    profile_dir = _seed_profile(hermes_home, "work", {"model": {"default": "m2"}})
    (profile_dir / ".hud-profile-disabled").write_text("legacy marker\n", encoding="utf-8")

    result = get_profile_edit("work")

    assert "enabled" not in result


def test_delete_profile_does_not_require_enabled_profile_count(hermes_home: Path) -> None:
    _seed_profile(hermes_home, "default", {"model": {"default": "m"}})
    profile_dir = _seed_profile(hermes_home, "work", {"model": {"default": "m2"}})
    (profile_dir / ".hud-profile-disabled").write_text("legacy marker\n", encoding="utf-8")

    result = delete_profile("work", ProfileDeleteBody(confirm_name="work"))

    assert result == {"ok": True, "name": "work"}
    assert not profile_dir.exists()


def test_delete_active_profile_resets_to_default(hermes_home: Path) -> None:
    _seed_profile(hermes_home, "work", {"model": {"default": "m2"}})
    (hermes_home / "active_profile").write_text("work\n", encoding="utf-8")

    delete_profile("work", ProfileDeleteBody(confirm_name="WORK"))

    assert get_active_profile() == {"active_profile": "default"}
    assert not (hermes_home / "active_profile").exists()


def test_active_profile_defaults_to_default(hermes_home: Path) -> None:
    assert get_active_profile() == {"active_profile": "default"}


def test_use_profile_sets_sticky_default(hermes_home: Path) -> None:
    _seed_profile(hermes_home, "work", {"model": {"default": "m2"}})

    result = use_profile("work")

    assert result == {"active_profile": "work"}
    assert (hermes_home / "active_profile").read_text(encoding="utf-8") == "work\n"


def test_use_default_profile_clears_sticky_default(hermes_home: Path) -> None:
    (hermes_home / "active_profile").write_text("work\n", encoding="utf-8")

    result = use_profile("default")

    assert result == {"active_profile": "default"}
    assert not (hermes_home / "active_profile").exists()


def test_delete_profile_requires_confirmation_and_preserves_default(hermes_home: Path) -> None:
    _seed_profile(hermes_home, "default", {"model": {"default": "m"}})
    _seed_profile(hermes_home, "work", {"model": {"default": "m2"}})

    with pytest.raises(HTTPException) as exc:
        delete_profile("work", ProfileDeleteBody(confirm_name="wrong"))
    assert exc.value.status_code == 400

    result = delete_profile("work", ProfileDeleteBody(confirm_name="work"))
    assert result == {"ok": True, "name": "work"}
    assert not (hermes_home / "profiles" / "work").exists()

    with pytest.raises(HTTPException) as exc:
        delete_profile("default", ProfileDeleteBody(confirm_name="default"))
    assert exc.value.status_code == 400


def test_profile_edit_routes_are_registered(registered_routes) -> None:
    assert ("POST", "/api/profiles") in registered_routes
    assert ("POST", "/api/profiles/import") in registered_routes
    assert ("GET", "/api/profiles/{profile_name}/edit") in registered_routes
    assert ("PUT", "/api/profiles/{profile_name}/edit") in registered_routes
    assert ("GET", "/api/profiles/active") in registered_routes
    assert ("POST", "/api/profiles/{profile_name}/use") in registered_routes
    assert ("POST", "/api/profiles/{profile_name}/enable") not in registered_routes
    assert ("POST", "/api/profiles/{profile_name}/disable") not in registered_routes
    assert ("DELETE", "/api/profiles/{profile_name}") in registered_routes
