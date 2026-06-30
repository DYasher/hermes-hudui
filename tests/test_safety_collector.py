from pathlib import Path

from backend.collectors.safety import collect_safety


def _by_name(items):
    return {item.name: item for item in items}


def test_safety_collects_runtime_surface_without_returning_secret_values(tmp_path: Path) -> None:
    hermes_dir = tmp_path / "hermes"
    hermes_dir.mkdir()
    (hermes_dir / ".env").write_text("ANTHROPIC_API_KEY=secret-value\n", encoding="utf-8")
    (hermes_dir / "auth.json").write_text('{"access_token":"secret"}', encoding="utf-8")
    (hermes_dir / "config.yaml").write_text("model:\n  provider: anthropic\n", encoding="utf-8")
    (hermes_dir / "state.db").write_bytes(b"sqlite")

    state = collect_safety(str(hermes_dir))

    assert state.environment_class == "unknown"
    assert state.write_policy == "manual_actions_only"
    assert state.sensitive_present_count == 4
    assert state.prod_matches == []

    surface = {item.path: item for item in state.runtime_surface}
    assert surface[".env"].present is True
    assert surface[".env"].policy == "never track raw runtime data"
    assert surface["sessions"].present is False

    text = repr(state)
    assert "secret-value" not in text
    assert "access_token" not in text


def test_safety_flags_production_like_markers(tmp_path: Path) -> None:
    hermes_dir = tmp_path / "prod-hermes"
    hermes_dir.mkdir()
    (hermes_dir / ".env").write_text("PROD_OPENAI_API_KEY=secret\n", encoding="utf-8")
    (hermes_dir / "config.yaml").write_text("base_url: https://api.production.example\n", encoding="utf-8")

    state = collect_safety(str(hermes_dir))
    checks = _by_name(state.checks)

    assert state.environment_class == "prod_like"
    assert state.write_policy == "blocked"
    assert state.prod_matches
    assert checks["Production-like markers"].status == "blocked"
    assert any(match.rule == "prod-key-name" for match in state.prod_matches)


def test_safety_accepts_default_deny_snapshot_git_surface(tmp_path: Path) -> None:
    hermes_dir = tmp_path / "hermes"
    hermes_dir.mkdir()
    (hermes_dir / ".git").mkdir()
    (hermes_dir / ".gitignore").write_text(
        "*\n!.gitignore\n!sanitized/\n!sanitized/**\n!versioned/\n!versioned/**\n",
        encoding="utf-8",
    )

    state = collect_safety(str(hermes_dir))
    checks = _by_name(state.checks)

    assert checks["Runtime git surface"].status == "ok"
    assert "default-deny" in checks["Runtime git surface"].detail
