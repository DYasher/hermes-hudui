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
import sqlite3
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from backend.api.memory import (
    ENTRY_DELIMITER,
    AddBody,
    DeleteBody,
    EditBody,
    MemoryExportBody,
    MemoryFileBody,
    MemoryHistoryCommitBody,
    MemorySettingsBody,
    MemoryProviderConfigBody,
    MemoryProviderBody,
    _read_entries,
    add_entry,
    approve_pending_memory,
    check_memory_provider_status,
    delete_entry,
    edit_entry,
    get_memory_files,
    get_memory_export,
    get_memory_history,
    get_memory_pending,
    get_memory_providers,
    get_memory_settings,
    get_memory_provider_external_view,
    reject_pending_memory,
    save_memory_file,
    save_memory_settings,
    save_memory_provider_config,
    create_memory_export_backup,
    commit_memory_history_candidate,
    set_memory_provider,
)


@pytest.fixture
def hermes_home(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    return tmp_path


def test_memory_provider_service_payload_matches_api_contract(hermes_home: Path) -> None:
    from backend.services.memory_provider_service import provider_payload

    result = provider_payload()

    assert result["builtin"] == {"enabled": True, "sources": ["MEMORY.md", "USER.md"]}
    assert result["active_provider"] == ""
    assert result["providers"]["honcho"]["schema_source"]["kind"] == "official_schema"
    assert result["providers"]["cognee"]["external_view"]["view_type"] == "summary"
    assert result["providers"]["holographic"]["external_view"]["view_type"] == "facts"


def test_memory_provider_service_export_redacts_secrets(hermes_home: Path) -> None:
    from backend.services.memory_provider_service import provider_export_payload

    _config_file(hermes_home).write_text("memory:\n  provider: mem0\n", encoding="utf-8")
    _env_file(hermes_home).write_text("MEM0_API_KEY=secret\n", encoding="utf-8")
    (hermes_home / "mem0.json").write_text('{"user_id": "u1"}\n', encoding="utf-8")

    result = provider_export_payload()

    assert result["active_provider"] == "mem0"
    assert result["providers"]["mem0"]["fields"]["MEM0_API_KEY"]["redacted"] is True
    assert result["providers"]["mem0"]["fields"]["MEM0_API_KEY"]["value"] == ""
    assert result["providers"]["mem0"]["fields"]["user_id"]["value"] == "u1"
    assert result["redactions"] == ["mem0.MEM0_API_KEY"]
    assert "secret" not in str(result)


def _memory_file(home: Path, target: str = "memory") -> Path:
    name = "USER.md" if target == "user" else "MEMORY.md"
    return home / "memories" / name


def _config_file(home: Path) -> Path:
    return home / "config.yaml"


def _env_file(home: Path) -> Path:
    return home / ".env"


def _pending_file(home: Path, pending_id: str) -> Path:
    return home / "pending" / "memory" / f"{pending_id}.json"


def _state_db(home: Path) -> Path:
    return home / "state.db"


def _create_state_db_with_messages(home: Path) -> Path:
    db_path = _state_db(home)
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            source TEXT,
            title TEXT,
            started_at REAL,
            message_count INTEGER,
            tool_call_count INTEGER,
            parent_session_id TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE messages (
            id TEXT PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            content TEXT,
            timestamp REAL
        )
        """
    )
    conn.execute(
        "INSERT INTO sessions (id, source, title, started_at, message_count, tool_call_count, parent_session_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("s1", "cli", "Preference discussion", 100, 2, 0, None),
    )
    conn.execute(
        "INSERT INTO sessions (id, source, title, started_at, message_count, tool_call_count, parent_session_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("tool1", "tool", "Internal tool session", 101, 1, 0, None),
    )
    conn.execute(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("m1", "s1", "user", "Please remember that I prefer compact Chinese replies.", 110),
    )
    conn.execute(
        "INSERT INTO messages (id, session_id, role, content, timestamp) VALUES (?, ?, ?, ?, ?)",
        ("m2", "tool1", "assistant", "Tool-only content should not become a memory candidate.", 120),
    )
    conn.commit()
    conn.close()
    return db_path


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


def test_memory_files_payload_includes_only_memory_and_user(hermes_home: Path) -> None:
    _memory_file(hermes_home, "memory").parent.mkdir(parents=True)
    _memory_file(hermes_home, "memory").write_text("agent fact\n§\nsecond fact\n", encoding="utf-8")
    _memory_file(hermes_home, "user").write_text("user prefers concise replies\n", encoding="utf-8")
    (hermes_home / "SOUL.md").write_text("You are direct.\n", encoding="utf-8")

    payload = get_memory_files()

    assert set(payload["files"]) == {"memory", "user"}
    assert payload["files"]["memory"]["label"] == "MEMORY.md"
    assert payload["files"]["memory"]["entry_count"] == 2
    assert payload["files"]["user"]["label"] == "USER.md"
    assert payload["files"]["user"]["entry_count"] == 1
    assert "SOUL.md" not in str(payload)
    assert payload["settings"]["memory_enabled"] is True


def test_save_memory_file_rejects_soul_without_modifying_profile_persona(hermes_home: Path) -> None:
    (hermes_home / "SOUL.md").write_text("Profile persona\n", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        save_memory_file("soul", MemoryFileBody(content="You are precise.\n"))

    assert exc.value.status_code == 400
    assert (hermes_home / "SOUL.md").read_text(encoding="utf-8") == "Profile persona\n"
    assert list(hermes_home.glob("*.tmp")) == []


def test_save_memory_file_rejects_nul_content(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        save_memory_file("memory", MemoryFileBody(content="bad\x00content"))

    assert exc.value.status_code == 400


def test_memory_settings_reads_defaults_and_config_overrides(hermes_home: Path) -> None:
    _config_file(hermes_home).write_text(
        "memory:\n"
        "  memory_enabled: false\n"
        "  user_profile_enabled: true\n"
        "  memory_char_limit: 3200\n"
        "  user_char_limit: 1800\n"
        "  write_approval: true\n"
        "display:\n"
        "  memory_notifications: verbose\n",
        encoding="utf-8",
    )

    settings = get_memory_settings()

    assert settings["memory_enabled"] is False
    assert settings["user_profile_enabled"] is True
    assert settings["memory_char_limit"] == 3200
    assert settings["user_char_limit"] == 1800
    assert settings["write_approval"] is True
    assert settings["memory_notifications"] == "verbose"


def test_save_memory_settings_preserves_provider_and_writes_display_section(hermes_home: Path) -> None:
    _config_file(hermes_home).write_text(
        "memory:\n"
        "  provider: honcho\n"
        "  memory_char_limit: 3000\n",
        encoding="utf-8",
    )

    result = save_memory_settings(
        MemorySettingsBody(
            memory_enabled=False,
            user_profile_enabled=False,
            memory_char_limit=4200,
            user_char_limit=2100,
            write_approval=True,
            memory_notifications="off",
        )
    )

    assert result["memory_enabled"] is False
    assert result["memory_char_limit"] == 4200
    text = _config_file(hermes_home).read_text(encoding="utf-8")
    assert "provider: honcho" in text
    assert "memory_enabled: false" in text
    assert "user_profile_enabled: false" in text
    assert "memory_char_limit: 4200" in text
    assert "user_char_limit: 2100" in text
    assert "write_approval: true" in text
    assert "memory_notifications: 'off'" in text or "memory_notifications: off" in text


def test_save_memory_settings_rejects_invalid_notification_mode(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        save_memory_settings(MemorySettingsBody(memory_notifications="loud"))

    assert exc.value.status_code == 400


def test_pending_memory_lists_official_records_oldest_first(hermes_home: Path) -> None:
    pending_dir = hermes_home / "pending" / "memory"
    pending_dir.mkdir(parents=True)
    (pending_dir / "b.json").write_text(
        '{"id":"b","subsystem":"memory","action":"add","summary":"second","origin":"foreground","created_at":2,"payload":{"action":"add","target":"memory","content":"second"}}',
        encoding="utf-8",
    )
    (pending_dir / "a.json").write_text(
        '{"id":"a","subsystem":"memory","action":"add","summary":"first","origin":"background_review","created_at":1,"payload":{"action":"add","target":"user","content":"first"}}',
        encoding="utf-8",
    )

    result = get_memory_pending()

    assert result["count"] == 2
    assert [record["id"] for record in result["pending"]] == ["a", "b"]
    assert result["pending"][0]["origin"] == "background_review"
    assert result["pending"][0]["payload"]["target"] == "user"


def test_approve_pending_memory_applies_add_and_deletes_pending_record(hermes_home: Path) -> None:
    pending = _pending_file(hermes_home, "abc123")
    pending.parent.mkdir(parents=True)
    pending.write_text(
        '{"id":"abc123","subsystem":"memory","action":"add","summary":"remember","origin":"foreground","created_at":1,"payload":{"action":"add","target":"memory","content":"approved fact"}}',
        encoding="utf-8",
    )

    result = approve_pending_memory("abc123")

    assert result["approved"] is True
    assert _read_entries("memory") == ["approved fact"]
    assert not pending.exists()


def test_reject_pending_memory_deletes_record_without_applying(hermes_home: Path) -> None:
    pending = _pending_file(hermes_home, "dropme")
    pending.parent.mkdir(parents=True)
    pending.write_text(
        '{"id":"dropme","subsystem":"memory","action":"add","summary":"drop","origin":"foreground","created_at":1,"payload":{"action":"add","target":"memory","content":"not applied"}}',
        encoding="utf-8",
    )

    result = reject_pending_memory("dropme")

    assert result == {"ok": True, "rejected": 1, "pending_id": "dropme"}
    assert _read_entries("memory") == []
    assert not pending.exists()


def test_memory_history_search_returns_user_facing_session_candidates(hermes_home: Path) -> None:
    _create_state_db_with_messages(hermes_home)

    result = get_memory_history(q="compact Chinese", limit=10)

    assert result["query"] == "compact Chinese"
    assert result["count"] == 1
    candidate = result["candidates"][0]
    assert candidate["session_id"] == "s1"
    assert candidate["message_id"] == "m1"
    assert candidate["title"] == "Preference discussion"
    assert candidate["suggested_target"] == "user"
    assert "compact Chinese replies" in candidate["snippet"]
    assert "tool1" not in str(result)


def test_commit_memory_history_candidate_writes_directly_when_approval_is_off(hermes_home: Path) -> None:
    result = commit_memory_history_candidate(
        MemoryHistoryCommitBody(
            target="user",
            content="User prefers compact Chinese replies.",
            source_session_id="s1",
            source_message_id="m1",
        )
    )

    assert result["ok"] is True
    assert result["staged"] is False
    assert result["target"] == "user"
    assert _read_entries("user") == ["User prefers compact Chinese replies."]


def test_commit_memory_history_candidate_stages_when_write_approval_is_on(hermes_home: Path) -> None:
    _config_file(hermes_home).write_text("memory:\n  write_approval: true\n", encoding="utf-8")

    result = commit_memory_history_candidate(
        MemoryHistoryCommitBody(
            target="memory",
            content="Project uses Hermes HUD on port 3002.",
            source_session_id="s2",
        )
    )

    assert result["ok"] is True
    assert result["staged"] is True
    assert result["pending_id"].startswith("history-")
    assert _read_entries("memory") == []
    pending_text = next((hermes_home / "pending" / "memory").glob("history-*.json")).read_text(encoding="utf-8")
    assert "Project uses Hermes HUD on port 3002." in pending_text
    assert '"origin": "history_candidate"' in pending_text


def test_memory_export_contains_memory_user_and_redacted_provider_config_only(hermes_home: Path) -> None:
    _memory_file(hermes_home, "memory").parent.mkdir(parents=True)
    _memory_file(hermes_home, "memory").write_text("agent fact\n", encoding="utf-8")
    _memory_file(hermes_home, "user").write_text("user fact\n", encoding="utf-8")
    (hermes_home / "SOUL.md").write_text("Profile persona must stay in Profiles.\n", encoding="utf-8")
    _config_file(hermes_home).write_text("memory:\n  provider: supermemory\n", encoding="utf-8")
    _env_file(hermes_home).write_text(
        "SUPERMEMORY_API_KEY=super-secret\nSUPERMEMORY_CONTAINER_TAG=visible-tag\n",
        encoding="utf-8",
    )
    (hermes_home / "supermemory.json").write_text(
        '{"container_tag":"container-visible","search_mode":"hybrid"}\n',
        encoding="utf-8",
    )

    result = get_memory_export()

    assert set(result["files"]) == {"memory", "user"}
    assert result["provider"]["active_provider"] == "supermemory"
    supermemory = result["provider"]["providers"]["supermemory"]
    assert supermemory["fields"]["SUPERMEMORY_CONTAINER_TAG"]["value"] == "visible-tag"
    assert supermemory["fields"]["container_tag"]["value"] == "container-visible"
    assert supermemory["fields"]["search_mode"]["value"] == "hybrid"
    assert supermemory["fields"]["SUPERMEMORY_API_KEY"]["redacted"] is True
    assert "super-secret" not in str(result)
    assert "SOUL.md" not in str(result)
    assert "Profile persona" not in str(result)


def test_memory_export_backup_writes_json_without_soul_or_secrets(hermes_home: Path) -> None:
    _memory_file(hermes_home, "memory").parent.mkdir(parents=True)
    _memory_file(hermes_home, "memory").write_text("agent fact\n", encoding="utf-8")
    _config_file(hermes_home).write_text("memory:\n  provider: mem0\n", encoding="utf-8")
    _env_file(hermes_home).write_text("MEM0_API_KEY=secret\n", encoding="utf-8")
    (hermes_home / "SOUL.md").write_text("Profile persona\n", encoding="utf-8")

    result = create_memory_export_backup(MemoryExportBody())

    assert result["ok"] is True
    backup = Path(result["path"])
    assert backup.exists()
    backup_text = backup.read_text(encoding="utf-8")
    assert "agent fact" in backup_text
    assert "secret" not in backup_text
    assert "SOUL.md" not in backup_text
    assert "Profile persona" not in backup_text


def test_memory_provider_status_defaults_to_builtin_only(hermes_home: Path) -> None:
    status = get_memory_providers()

    assert status["builtin"]["enabled"] is True
    assert status["active_provider"] == ""
    assert "honcho" in status["providers"]
    assert "supermemory" in status["providers"]
    assert "memori" in status["providers"]
    assert status["providers"]["honcho"]["setup_command"] == "hermes memory setup"
    assert status["providers"]["honcho"]["config_command"] == "hermes config set memory.provider honcho"


def test_memory_provider_payload_includes_provider_groups(hermes_home: Path) -> None:
    status = get_memory_providers()

    assert status["providers"]["honcho"]["group"] == "official"
    assert status["providers"]["mem0"]["group"] == "official"
    assert status["providers"]["cognee"]["group"] == "community"
    assert status["providers"]["agentmemory"]["group"] == "community"
    assert status["providers"]["memos"]["group"] == "community"


def test_cognee_provider_payload_describes_modes_and_minimum_config(hermes_home: Path) -> None:
    status = get_memory_providers()
    cognee = status["providers"]["cognee"]
    modes = {mode["id"]: mode for mode in cognee["config_modes"]}
    fields = {field["name"]: field for field in cognee["config_fields"]}

    assert cognee["label"] == "Cognee"
    assert cognee["group"] == "community"
    assert cognee["storage"] == "local/docker/mcp"
    assert cognee["configured"] is False
    assert cognee["missing_fields"] == ["LLM_API_KEY"]
    assert set(modes) == {"python_cli", "docker_api", "mcp_http"}
    assert modes["python_cli"]["required_fields"] == ["LLM_API_KEY"]
    assert modes["docker_api"]["required_fields"] == ["COGNEE_API_URL"]
    assert modes["mcp_http"]["required_fields"] == ["COGNEE_MCP_URL"]
    assert fields["LLM_API_KEY"]["secret"] is True
    assert fields["LLM_API_KEY"]["requirement"] == "required"
    assert fields["COGNEE_API_URL"]["requirement"] == "required"
    assert fields["COGNEE_MCP_URL"]["requirement"] == "required"
    assert fields["COGNEE_DATASET"]["requirement"] == "optional"
    assert fields["COGNEE_API_URL"]["mode_ids"] == ["docker_api"]
    assert fields["COGNEE_MCP_URL"]["mode_ids"] == ["mcp_http"]
    assert cognee["capabilities"]["external_read_mode"] == "provider_summary"


def test_agentmemory_provider_payload_describes_rest_and_mcp_modes(hermes_home: Path) -> None:
    status = get_memory_providers()
    provider = status["providers"]["agentmemory"]
    modes = {mode["id"]: mode for mode in provider["config_modes"]}
    fields = {field["name"]: field for field in provider["config_fields"]}

    assert provider["label"] == "agentmemory"
    assert provider["group"] == "community"
    assert provider["configured"] is False
    assert provider["missing_fields"] == ["AGENTMEMORY_URL"]
    assert modes["rest_server"]["required_fields"] == ["AGENTMEMORY_URL"]
    assert modes["mcp_server"]["required_fields"] == ["AGENTMEMORY_MCP_COMMAND"]
    assert fields["AGENTMEMORY_URL"]["requirement"] == "required"
    assert fields["AGENTMEMORY_SECRET"]["secret"] is True
    assert fields["AGENTMEMORY_SECRET"]["requirement"] == "optional"
    assert fields["AGENTMEMORY_MCP_COMMAND"]["requirement"] == "required"
    assert provider["capabilities"]["external_read_mode"] == "provider_summary"


def test_memos_provider_payload_describes_cloud_and_self_hosted_modes(hermes_home: Path) -> None:
    status = get_memory_providers()
    provider = status["providers"]["memos"]
    modes = {mode["id"]: mode for mode in provider["config_modes"]}
    fields = {field["name"]: field for field in provider["config_fields"]}

    assert provider["label"] == "MemOS"
    assert provider["group"] == "community"
    assert provider["configured"] is False
    assert provider["missing_fields"] == ["MEMOS_API_KEY"]
    assert modes["cloud"]["required_fields"] == ["MEMOS_API_KEY"]
    assert modes["self_hosted"]["required_fields"] == ["MEMOS_BASE_URL"]
    assert fields["MEMOS_API_KEY"]["secret"] is True
    assert fields["MEMOS_API_KEY"]["requirement"] == "required"
    assert fields["MEMOS_BASE_URL"]["requirement"] == "required"
    assert fields["MOS_CHAT_MODEL_PROVIDER"]["requirement"] == "optional"
    assert "MOS_CHAT_MODEL_PROVIDER" in fields
    assert provider["capabilities"]["external_read_mode"] == "provider_summary"


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


def test_save_provider_config_rejects_missing_required_fields(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        save_memory_provider_config(
            "openviking",
            MemoryProviderConfigBody(fields={"OPENVIKING_AGENT": "hermes"}),
        )

    assert exc.value.status_code == 400
    assert "OPENVIKING_ENDPOINT" in str(exc.value.detail)
    assert not _env_file(hermes_home).exists()


def test_save_provider_config_allows_optional_after_required_exists(hermes_home: Path) -> None:
    _env_file(hermes_home).write_text(
        "OPENVIKING_ENDPOINT=http://127.0.0.1:1933\n",
        encoding="utf-8",
    )

    result = save_memory_provider_config(
        "openviking",
        MemoryProviderConfigBody(fields={"OPENVIKING_AGENT": "hermes"}),
    )

    text = _env_file(hermes_home).read_text(encoding="utf-8")
    assert "OPENVIKING_ENDPOINT=http://127.0.0.1:1933" in text
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


def test_provider_payload_marks_required_optional_and_either_or_fields(hermes_home: Path) -> None:
    status = get_memory_providers()

    honcho_fields = {field["name"]: field for field in status["providers"]["honcho"]["config_fields"]}
    assert honcho_fields["apiKey"]["requirement"] == "required_any"
    assert honcho_fields["apiKey"]["required_group"] == ["apiKey", "baseUrl"]
    assert honcho_fields["baseUrl"]["requirement"] == "required_any"
    assert honcho_fields["peerName"]["requirement"] == "required"
    assert honcho_fields["workspace"]["requirement"] == "required"
    assert honcho_fields["aiPeer"]["requirement"] == "required"

    openviking_fields = {
        field["name"]: field for field in status["providers"]["openviking"]["config_fields"]
    }
    assert openviking_fields["OPENVIKING_ENDPOINT"]["requirement"] == "required"
    assert openviking_fields["OPENVIKING_API_KEY"]["requirement"] == "optional"
    assert openviking_fields["OPENVIKING_AGENT"]["requirement"] == "optional"

    supermemory_fields = {
        field["name"]: field for field in status["providers"]["supermemory"]["config_fields"]
    }
    assert supermemory_fields["SUPERMEMORY_API_KEY"]["requirement"] == "required"
    assert supermemory_fields["container_tag"]["requirement"] == "optional"


def test_provider_payload_describes_mode_specific_minimum_config(hermes_home: Path) -> None:
    status = get_memory_providers()

    honcho = status["providers"]["honcho"]
    honcho_modes = {mode["id"]: mode for mode in honcho["config_modes"]}
    honcho_fields = {field["name"]: field for field in honcho["config_fields"]}
    assert honcho["default_mode"] == "cloud"
    assert honcho["current_mode"] == "cloud"
    assert honcho_modes["cloud"]["required_fields"] == ["apiKey", "peerName", "workspace", "aiPeer"]
    assert honcho_modes["self_hosted"]["required_fields"] == [
        "baseUrl",
        "peerName",
        "workspace",
        "aiPeer",
    ]
    assert honcho_fields["apiKey"]["mode_ids"] == ["cloud"]
    assert honcho_fields["baseUrl"]["mode_ids"] == ["self_hosted"]
    assert honcho_fields["peerName"]["mode_ids"] == ["cloud", "self_hosted"]

    openviking = status["providers"]["openviking"]
    assert openviking["config_modes"][0]["id"] == "self_hosted"
    assert openviking["config_modes"][0]["required_fields"] == ["OPENVIKING_ENDPOINT"]


def test_provider_payload_infers_current_mode_from_existing_config(hermes_home: Path) -> None:
    (hermes_home / "honcho.json").write_text(
        '{"baseUrl":"http://localhost:8000","hosts":{"hermes":{"peerName":"asher","workspace":"local","aiPeer":"coder"}}}\n',
        encoding="utf-8",
    )

    status = get_memory_providers()

    assert status["providers"]["honcho"]["current_mode"] == "self_hosted"


def test_save_provider_config_enforces_selected_mode_requirements(hermes_home: Path) -> None:
    with pytest.raises(HTTPException) as exc:
        save_memory_provider_config(
            "honcho",
            MemoryProviderConfigBody(
                mode="self_hosted",
                fields={
                    "apiKey": "cloud-key",
                    "peerName": "asher",
                    "workspace": "hermes",
                    "aiPeer": "coder",
                },
            ),
        )

    assert exc.value.status_code == 400
    assert "baseUrl" in str(exc.value.detail)
    assert not (hermes_home / "honcho.json").exists()


def test_save_provider_config_persists_selected_mode_when_provider_has_mode_field(
    hermes_home: Path,
) -> None:
    result = save_memory_provider_config(
        "hindsight",
        MemoryProviderConfigBody(mode="local", fields={"bank_id": "hermes"}),
    )

    text = (hermes_home / "hindsight/config.json").read_text(encoding="utf-8")
    assert '"mode": "local"' in text
    assert '"bank_id": "hermes"' in text
    assert result["providers"]["hindsight"]["configured"] is True
    assert result["providers"]["hindsight"]["current_mode"] == "local"


def test_provider_payload_reports_structured_read_only_health(hermes_home: Path) -> None:
    (hermes_home / "honcho.json").write_text("{}\n", encoding="utf-8")

    status = get_memory_providers()
    health = status["providers"]["honcho"]["health"]

    assert health["provider"] == "honcho"
    assert health["active"] is False
    assert health["required_config"]["ok"] is False
    assert health["required_config"]["missing_fields"] == ["apiKey", "peerName", "workspace", "aiPeer"]
    assert health["required_config"]["missing_any"] == []
    assert health["config_files"] == [{"path": "honcho.json", "kind": "file", "exists": True}]
    assert health["dependencies"]["checks"] == status["providers"]["honcho"]["checks"]
    assert health["status_command"] is None
    assert health["checked_at"].endswith("Z")


def test_provider_payload_includes_capability_matrix_and_schema_source(hermes_home: Path) -> None:
    status = get_memory_providers()

    supermemory = status["providers"]["supermemory"]
    assert supermemory["capabilities"]["external_read"] is True
    assert supermemory["capabilities"]["external_read_mode"] == "provider_specific"
    assert supermemory["capabilities"]["direct_hud_config"] is True
    assert supermemory["capabilities"]["requires_network"] is True
    assert "prefetch" in supermemory["capabilities"]["hooks"]
    assert supermemory["schema_source"]["kind"] == "official_schema"
    assert supermemory["schema_source"]["method"] == "get_config_schema"
    assert supermemory["schema_source"]["fallback"] is False

    byterover = status["providers"]["byterover"]
    assert byterover["capabilities"]["direct_hud_config"] is False
    assert byterover["capabilities"]["external_read"] is False
    assert byterover["schema_source"]["kind"] == "hud_metadata"
    assert byterover["schema_source"]["fallback"] is True


def test_provider_payload_includes_external_view_summary(hermes_home: Path) -> None:
    status = get_memory_providers()

    holographic = status["providers"]["holographic"]
    assert holographic["external_view"]["available"] is True
    assert holographic["external_view"]["endpoint"] == "/api/memory/providers/holographic/external"
    assert holographic["external_view"]["view_type"] == "facts"

    honcho = status["providers"]["honcho"]
    assert honcho["external_view"]["available"] is False
    assert honcho["external_view"]["reason"] == "provider_specific_api_not_configured"


def test_holographic_external_view_reads_local_facts_without_mutation(hermes_home: Path) -> None:
    db_path = hermes_home / "memory_store.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE facts (
            fact_id INTEGER PRIMARY KEY,
            content TEXT NOT NULL,
            category TEXT DEFAULT 'general',
            tags TEXT DEFAULT '',
            trust_score REAL DEFAULT 0.5,
            retrieval_count INTEGER DEFAULT 0,
            helpful_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT '',
            updated_at TEXT DEFAULT ''
        )
        """
    )
    conn.execute(
        "INSERT INTO facts (fact_id, content, category, tags, trust_score, retrieval_count, helpful_count, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (7, "User prefers direct answers", "user_pref", "style,profile", 0.8, 3, 2, "2026-07-01", "2026-07-02"),
    )
    conn.commit()
    conn.close()

    result = get_memory_provider_external_view("holographic")

    assert result["provider"] == "holographic"
    assert result["available"] is True
    assert result["readonly"] is True
    assert result["summary"]["total"] == 1
    assert result["summary"]["categories"] == {"user_pref": 1}
    assert result["items"] == [
        {
            "id": "7",
            "content": "User prefers direct answers",
            "category": "user_pref",
            "tags": ["style", "profile"],
            "trust_score": 0.8,
            "retrieval_count": 3,
            "helpful_count": 2,
            "created_at": "2026-07-01",
            "updated_at": "2026-07-02",
        }
    ]


def test_external_view_for_cloud_provider_is_explicitly_unavailable(hermes_home: Path) -> None:
    result = get_memory_provider_external_view("supermemory")

    assert result["provider"] == "supermemory"
    assert result["available"] is False
    assert result["readonly"] is True
    assert result["reason"] == "provider_specific_api_not_configured"
    assert result["items"] == []


def test_external_view_for_cognee_is_summary_only(hermes_home: Path) -> None:
    result = get_memory_provider_external_view("cognee")

    assert result["provider"] == "cognee"
    assert result["available"] is True
    assert result["readonly"] is True
    assert result["reason"] == "provider_summary"
    assert result["summary"]["categories"]["configured_fields"] == 0
    assert result["summary"]["categories"]["missing_required"] == 1
    assert {item["category"] for item in result["items"]} == {"runtime", "config"}


def test_external_view_for_community_provider_reports_safe_config_summary(hermes_home: Path) -> None:
    _env_file(hermes_home).write_text(
        "MEMOS_API_KEY=secret-memos-key\n",
        encoding="utf-8",
    )
    (hermes_home / "memos.json").write_text('{"namespace": "hermes"}\n', encoding="utf-8")

    result = get_memory_provider_external_view("memos")

    assert result["provider"] == "memos"
    assert result["available"] is True
    assert result["reason"] == "provider_summary"
    assert result["summary"]["categories"]["configured_fields"] == 1
    assert result["summary"]["categories"]["missing_required"] == 0
    assert any("Cloud API" in item["content"] for item in result["items"])
    assert "secret-memos-key" not in str(result)


def test_memory_provider_check_runs_agentmemory_runtime_probe(monkeypatch, hermes_home: Path) -> None:
    _env_file(hermes_home).write_text(
        "AGENTMEMORY_URL=http://127.0.0.1:3111\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "backend.services.memory_provider_health.shutil.which",
        lambda name: "/usr/bin/hermes",
    )
    monkeypatch.setattr(
        "backend.services.memory_provider_health.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="Built-in only\n", stderr=""),
    )

    seen_urls: list[str] = []

    class FakeResponse:
        def getcode(self) -> int:
            return 200

        def close(self) -> None:
            pass

    def fake_urlopen(request, timeout):
        seen_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr("backend.services.memory_provider_health.urlopen", fake_urlopen)

    result = check_memory_provider_status(MemoryProviderBody(provider="agentmemory"))

    assert seen_urls == ["http://127.0.0.1:3111/agentmemory/health"]
    runtime = result["health"]["runtime"]
    assert runtime["ok"] is True
    assert runtime["mode"] == "rest_server"
    assert runtime["checks"][0]["kind"] == "http"
    assert runtime["checks"][0]["status_code"] == 200


def test_memory_provider_check_uses_selected_config_mode_for_runtime_probe(monkeypatch, hermes_home: Path) -> None:
    _env_file(hermes_home).write_text(
        "LLM_API_KEY=secret\n"
        "COGNEE_API_URL=http://127.0.0.1:8000\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "backend.services.memory_provider_health.shutil.which",
        lambda name: "/usr/bin/hermes",
    )
    monkeypatch.setattr(
        "backend.services.memory_provider_health.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="Built-in only\n", stderr=""),
    )

    seen_urls: list[str] = []

    class FakeResponse:
        def getcode(self) -> int:
            return 200

        def close(self) -> None:
            pass

    def fake_urlopen(request, timeout):
        seen_urls.append(request.full_url)
        return FakeResponse()

    monkeypatch.setattr("backend.services.memory_provider_health.urlopen", fake_urlopen)

    result = check_memory_provider_status(MemoryProviderBody(provider="cognee", mode="docker_api"))

    assert seen_urls == ["http://127.0.0.1:8000/health"]
    runtime = result["health"]["runtime"]
    assert runtime["ok"] is True
    assert runtime["mode"] == "docker_api"
    assert runtime["checks"][0]["name"] == "Cognee API"


def test_memory_provider_check_runs_official_status_command(monkeypatch, hermes_home: Path) -> None:
    _config_file(hermes_home).write_text("memory:\n  provider: honcho\n", encoding="utf-8")

    monkeypatch.setattr(
        "backend.services.memory_provider_health.shutil.which",
        lambda name: "/usr/bin/hermes",
    )
    monkeypatch.setattr(
        "backend.services.memory_provider_health.subprocess.run",
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
    assert result["health"]["provider"] == "honcho"
    assert result["health"]["status_command"]["ok"] is True
    assert result["health"]["checked_at"].endswith("Z")


def test_memory_provider_check_omits_health_for_builtin_only(monkeypatch, hermes_home: Path) -> None:
    monkeypatch.setattr(
        "backend.services.memory_provider_health.shutil.which",
        lambda name: "/usr/bin/hermes",
    )
    monkeypatch.setattr(
        "backend.services.memory_provider_health.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="Built-in only\n", stderr=""),
    )

    result = check_memory_provider_status(MemoryProviderBody(provider=""))

    assert result["provider"] == ""
    assert result["health"] is None


def test_memory_routes_are_registered(registered_routes) -> None:
    assert ("GET", "/api/memory") in registered_routes
    assert ("POST", "/api/memory") in registered_routes
    assert ("PUT", "/api/memory") in registered_routes
    assert ("DELETE", "/api/memory") in registered_routes
    assert ("GET", "/api/memory/files") in registered_routes
    assert ("PUT", "/api/memory/files/{target}") in registered_routes
    assert ("GET", "/api/memory/history") in registered_routes
    assert ("POST", "/api/memory/history/commit") in registered_routes
    assert ("GET", "/api/memory/export") in registered_routes
    assert ("POST", "/api/memory/export") in registered_routes
    assert ("GET", "/api/memory/settings") in registered_routes
    assert ("PUT", "/api/memory/settings") in registered_routes
    assert ("GET", "/api/memory/pending") in registered_routes
    assert ("POST", "/api/memory/pending/{pending_id}/approve") in registered_routes
    assert ("POST", "/api/memory/pending/{pending_id}/reject") in registered_routes
    assert ("GET", "/api/memory/providers") in registered_routes
    assert ("PUT", "/api/memory/providers") in registered_routes
    assert ("PUT", "/api/memory/providers/{provider}/config") in registered_routes
    assert ("GET", "/api/memory/providers/{provider}/external") in registered_routes
    assert ("POST", "/api/memory/providers/check") in registered_routes
