"""Write-path tests for the memory editing API (backend/api/memory.py).

Memory editing mutates the user's MEMORY.md / USER.md via fcntl locking +
atomic writes, so a bug here can corrupt real agent data. These cover the
risky surface: the ``\n§\n`` entry-delimiter round-trip contract, substring
matching, atomic writes leaving no temp files, and the validation guards.

The endpoint functions are plain ``def`` (FastAPI auto-threads them), so they
are exercised directly. ``default_hermes_dir()`` reads ``HERMES_HOME`` at call
time, so pointing it at a tmp dir is just an env var.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.memory import (
    ENTRY_DELIMITER,
    AddBody,
    DeleteBody,
    EditBody,
    MemoryProviderConfigBody,
    MemoryProviderBody,
    _read_entries,
    add_entry,
    check_memory_provider_status,
    delete_entry,
    edit_entry,
    get_memory_providers,
    save_memory_provider_config,
    set_memory_provider,
)


@pytest.fixture
def hermes_home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def _memory_file(home: Path, target: str = "memory") -> Path:
    name = "USER.md" if target == "user" else "MEMORY.md"
    return home / "memories" / name


def _config_file(home: Path) -> Path:
    return home / "config.yaml"


def _env_file(home: Path) -> Path:
    return home / ".env"


def test_add_creates_file_with_single_entry(hermes_home: Path) -> None:
    result = add_entry(AddBody(target="memory", content="first fact"))
    assert result == {"ok": True, "entry_count": 1}

    path = _memory_file(hermes_home)
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "first fact\n"


def test_add_appends_with_delimiter_and_round_trips(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="alpha"))
    add_entry(AddBody(target="memory", content="beta"))

    path = _memory_file(hermes_home)
    assert path.read_text(encoding="utf-8") == "alpha" + ENTRY_DELIMITER + "beta" + "\n"
    # the on-disk format parses back to the original entries
    assert _read_entries("memory") == ["alpha", "beta"]


def test_add_rejects_empty_content(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        add_entry(AddBody(target="memory", content="   "))
    assert exc.value.status_code == 400


def test_add_rejects_duplicate(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="dup"))
    with pytest.raises(HTTPException) as exc:
        add_entry(AddBody(target="memory", content="dup"))
    assert exc.value.status_code == 409
    # the duplicate did not double-write
    assert _read_entries("memory") == ["dup"]


def test_memory_and_user_targets_are_isolated(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="in memory"))
    add_entry(AddBody(target="user", content="in user"))

    assert _read_entries("memory") == ["in memory"]
    assert _read_entries("user") == ["in user"]
    assert _memory_file(hermes_home, "memory").read_text(encoding="utf-8") == "in memory\n"
    assert _memory_file(hermes_home, "user").read_text(encoding="utf-8") == "in user\n"


def test_edit_replaces_matched_entry_preserving_others(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="keep one"))
    add_entry(AddBody(target="memory", content="change me"))
    add_entry(AddBody(target="memory", content="keep two"))

    result = edit_entry(EditBody(target="memory", old_text="change", content="changed!"))
    assert result["ok"] is True
    assert _read_entries("memory") == ["keep one", "changed!", "keep two"]


def test_edit_no_match_returns_404(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="something"))
    with pytest.raises(HTTPException) as exc:
        edit_entry(EditBody(target="memory", old_text="absent", content="x"))
    assert exc.value.status_code == 404
    assert _read_entries("memory") == ["something"]


def test_edit_ambiguous_match_is_rejected_without_writing(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="shared token A"))
    add_entry(AddBody(target="memory", content="shared token B"))

    with pytest.raises(HTTPException) as exc:
        edit_entry(EditBody(target="memory", old_text="shared token", content="x"))
    assert exc.value.status_code == 409
    # both entries are intact — an ambiguous edit must not clobber data
    assert _read_entries("memory") == ["shared token A", "shared token B"]


def test_edit_rejects_empty_content(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="x"))
    with pytest.raises(HTTPException) as exc:
        edit_entry(EditBody(target="memory", old_text="x", content="  "))
    assert exc.value.status_code == 400


def test_delete_removes_matched_entry_preserving_others(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="alpha"))
    add_entry(AddBody(target="memory", content="bravo"))
    add_entry(AddBody(target="memory", content="charlie"))

    result = delete_entry(DeleteBody(target="memory", old_text="bravo"))
    assert result == {"ok": True, "entry_count": 2}
    assert _read_entries("memory") == ["alpha", "charlie"]


def test_delete_last_entry_empties_file(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="only"))
    delete_entry(DeleteBody(target="memory", old_text="only"))

    assert _read_entries("memory") == []
    assert _memory_file(hermes_home).read_text(encoding="utf-8") == ""


def test_delete_no_match_returns_404(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="present"))
    with pytest.raises(HTTPException) as exc:
        delete_entry(DeleteBody(target="memory", old_text="absent"))
    assert exc.value.status_code == 404
    assert _read_entries("memory") == ["present"]


def test_delete_ambiguous_match_is_rejected_without_writing(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="dupe x"))
    add_entry(AddBody(target="memory", content="dupe y"))

    with pytest.raises(HTTPException) as exc:
        delete_entry(DeleteBody(target="memory", old_text="dupe"))
    assert exc.value.status_code == 409
    assert _read_entries("memory") == ["dupe x", "dupe y"]


def test_atomic_writes_leave_no_temp_files(hermes_home: Path) -> None:
    add_entry(AddBody(target="memory", content="a"))
    edit_entry(EditBody(target="memory", old_text="a", content="b"))
    delete_entry(DeleteBody(target="memory", old_text="b"))

    leftovers = list((hermes_home / "memories").glob("*.tmp"))
    assert leftovers == []


def test_memory_provider_status_defaults_to_builtin_only(hermes_home: Path) -> None:
    status = get_memory_providers()

    assert status["builtin"]["enabled"] is True
    assert status["active_provider"] == ""
    assert "honcho" in status["providers"]
    assert "supermemory" in status["providers"]
    assert "memori" in status["providers"]
    assert status["providers"]["honcho"]["setup_command"] == "hermes memory setup"
    assert status["providers"]["honcho"]["config_command"] == "hermes config set memory.provider honcho"


def test_memory_provider_status_reads_config(hermes_home: Path) -> None:
    _config_file(hermes_home).write_text(
        "memory:\n  provider: holographic\n  memory_char_limit: 3000\n",
        encoding="utf-8",
    )

    status = get_memory_providers()

    assert status["active_provider"] == "holographic"
    assert status["providers"]["holographic"]["active"] is True


def test_memory_provider_status_reads_memori_config(hermes_home: Path) -> None:
    _config_file(hermes_home).write_text(
        "memory:\n  provider: memori\n",
        encoding="utf-8",
    )

    status = get_memory_providers()

    assert status["active_provider"] == "memori"
    assert status["providers"]["memori"]["config_command"] == "hermes config set memory.provider memori"


def test_set_memory_provider_writes_config_preserving_memory_limits(hermes_home: Path) -> None:
    _config_file(hermes_home).write_text(
        "memory:\n  memory_char_limit: 3000\n  user_char_limit: 2000\n",
        encoding="utf-8",
    )

    result = set_memory_provider(MemoryProviderBody(provider="mem0"))

    assert result["active_provider"] == "mem0"
    text = _config_file(hermes_home).read_text(encoding="utf-8")
    assert "provider: mem0" in text
    assert "memory_char_limit: 3000" in text
    assert "user_char_limit: 2000" in text


def test_set_memory_provider_accepts_memori(hermes_home: Path) -> None:
    result = set_memory_provider(MemoryProviderBody(provider="memori"))

    assert result["active_provider"] == "memori"
    assert "provider: memori" in _config_file(hermes_home).read_text(encoding="utf-8")


def test_set_memory_provider_off_removes_external_provider(hermes_home: Path) -> None:
    _config_file(hermes_home).write_text(
        "memory:\n  provider: honcho\n  user_char_limit: 2000\n",
        encoding="utf-8",
    )

    result = set_memory_provider(MemoryProviderBody(provider=""))

    assert result["active_provider"] == ""
    text = _config_file(hermes_home).read_text(encoding="utf-8")
    assert "provider:" not in text
    assert "user_char_limit: 2000" in text


def test_set_memory_provider_rejects_unknown_provider(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        set_memory_provider(MemoryProviderBody(provider="unknown"))

    assert exc.value.status_code == 400


def test_save_honcho_config_writes_json_and_redacts_secret(hermes_home: Path) -> None:
    result = save_memory_provider_config(
        "honcho",
        MemoryProviderConfigBody(
            fields={
                "apiKey": "honcho-secret",
                "baseUrl": "http://localhost:8000",
                "peerName": "asher",
                "workspace": "hermes",
                "aiPeer": "coder",
            }
        ),
    )

    text = (hermes_home / "honcho.json").read_text(encoding="utf-8")
    assert "honcho-secret" in text
    assert "http://localhost:8000" in text
    assert '"peerName": "asher"' in text
    assert result["providers"]["honcho"]["configured"] is True
    assert result["providers"]["honcho"]["config_values"]["apiKey"]["configured"] is True
    assert result["providers"]["honcho"]["config_values"]["apiKey"]["value"] == ""
    assert "honcho-secret" not in str(result)


def test_save_openviking_config_writes_env_preserving_existing_values(hermes_home: Path) -> None:
    _env_file(hermes_home).write_text("EXISTING=yes\n", encoding="utf-8")

    result = save_memory_provider_config(
        "openviking",
        MemoryProviderConfigBody(
            fields={
                "OPENVIKING_ENDPOINT": "http://127.0.0.1:9090",
                "OPENVIKING_AGENT": "hermes",
            }
        ),
    )

    text = _env_file(hermes_home).read_text(encoding="utf-8")
    assert "EXISTING=yes" in text
    assert "OPENVIKING_ENDPOINT=http://127.0.0.1:9090" in text
    assert "OPENVIKING_AGENT=hermes" in text
    assert result["providers"]["openviking"]["configured"] is True


def test_provider_payload_reports_config_state_without_secret(hermes_home: Path) -> None:
    _config_file(hermes_home).write_text("memory:\n  provider: mem0\n", encoding="utf-8")
    _env_file(hermes_home).write_text("MEM0_API_KEY=mem0-secret\n", encoding="utf-8")
    (hermes_home / "mem0.json").write_text('{"user_id": "u1"}\n', encoding="utf-8")

    status = get_memory_providers()

    mem0 = status["providers"]["mem0"]
    assert status["active_provider"] == "mem0"
    assert mem0["configured"] is True
    assert mem0["readiness"] in {"selected", "ready"}
    assert mem0["config_values"]["MEM0_API_KEY"]["configured"] is True
    assert mem0["config_values"]["MEM0_API_KEY"]["value"] == ""
    assert mem0["config_values"]["user_id"]["value"] == "u1"
    assert "mem0-secret" not in str(status)


def test_memory_provider_check_runs_official_status_command(monkeypatch, hermes_home: Path) -> None:
    _config_file(hermes_home).write_text("memory:\n  provider: honcho\n", encoding="utf-8")

    monkeypatch.setattr("backend.api.memory.shutil.which", lambda name: "/usr/bin/hermes")
    monkeypatch.setattr(
        "backend.api.memory.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="Memory provider: honcho\nStatus: active\n",
            stderr="",
        ),
    )

    result = check_memory_provider_status(MemoryProviderBody(provider="honcho"))

    assert result["provider"] == "honcho"
    assert result["status_command"]["ok"] is True
    assert "Status: active" in result["status_command"]["output"]


def test_memory_routes_are_registered(registered_routes) -> None:
    assert ("GET", "/api/memory") in registered_routes
    assert ("POST", "/api/memory") in registered_routes
    assert ("PUT", "/api/memory") in registered_routes
    assert ("DELETE", "/api/memory") in registered_routes
    assert ("GET", "/api/memory/providers") in registered_routes
    assert ("PUT", "/api/memory/providers") in registered_routes
    assert ("PUT", "/api/memory/providers/{provider}/config") in registered_routes
    assert ("POST", "/api/memory/providers/check") in registered_routes
