"""Read-only runtime safety posture collector.

This borrows the production-boundary ideas from the local Hermes Control Panel:
classify the active Hermes home, surface production-like markers, and keep raw
runtime files out of any versioned surface. It intentionally reports only file
names, paths, and rule ids; it does not return secret values.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .utils import default_hermes_dir


@dataclass(frozen=True)
class SafetyRule:
    id: str
    kind: str
    pattern: str
    severity: str = "blocked"


@dataclass
class SafetyMatch:
    rule: str
    kind: str
    field: str
    redacted_value: str
    severity: str = "blocked"


@dataclass
class SafetyCheck:
    name: str
    status: str
    detail: str
    recommendation: str = ""
    evidence: list[str] = field(default_factory=list)


@dataclass
class RuntimeSurface:
    path: str
    present: bool
    status: str
    policy: str
    detail: str = ""


@dataclass
class OperationPolicy:
    name: str
    policy: str
    status: str
    detail: str


@dataclass
class SafetyState:
    hermes_dir: str
    hermes_dir_exists: bool
    environment_class: str
    write_policy: str
    checks: list[SafetyCheck] = field(default_factory=list)
    runtime_surface: list[RuntimeSurface] = field(default_factory=list)
    operation_policies: list[OperationPolicy] = field(default_factory=list)
    prod_matches: list[SafetyMatch] = field(default_factory=list)

    @property
    def ok_count(self) -> int:
        return sum(1 for item in self.checks if item.status == "ok")

    @property
    def warning_count(self) -> int:
        return sum(1 for item in self.checks if item.status == "warning")

    @property
    def blocked_count(self) -> int:
        return sum(1 for item in self.checks if item.status == "blocked")

    @property
    def sensitive_present_count(self) -> int:
        return sum(1 for item in self.runtime_surface if item.present)


PROD_RULES: tuple[SafetyRule, ...] = (
    SafetyRule("prod-domain-keyword", "domain", r"(^|[.-])(prod|production|live)([.-]|$)"),
    SafetyRule("prod-key-name", "key_name", r"(^|_)(PROD|PRODUCTION|LIVE)(_|$)"),
    SafetyRule("prod-database", "database", r"(^|[-_])(prod|production|live)([-_]|$)"),
    SafetyRule("prod-bucket", "bucket", r"(^|[-_])(prod|production|live)([-_]|$)"),
    SafetyRule("prod-path-keyword", "path", r"(^|[/:._-])(prod|production|live)([/:._-]|$)"),
)

SENSITIVE_RUNTIME_PATHS: tuple[tuple[str, str], ...] = (
    (".env", "Contains provider keys and gateway credentials."),
    ("auth.json", "Contains OAuth and account state."),
    ("config.yaml", "Primary live Hermes configuration."),
    ("state.db", "Live session and runtime database."),
    ("state.db-wal", "SQLite write-ahead log for live runtime state."),
    ("sessions", "Raw session transcripts and tool-call history."),
    ("memories", "Raw memory state."),
    ("weixin", "Messaging account state."),
    ("skills", "Installed skills and local customizations."),
    ("logs", "Runtime logs that can include prompts or tool output."),
    ("backups", "Backup archives and restore material."),
    ("gateway_state.json", "Gateway process and platform state."),
)


def _status_order(item: SafetyCheck) -> int:
    return {"blocked": 0, "warning": 1, "ok": 2}.get(item.status, 3)


def _redact(value: str) -> str:
    if len(value) <= 12:
        return "***"
    return f"{value[:4]}***{value[-4:]}"


def _read_text(path: Path, max_bytes: int = 256_000) -> str:
    try:
        with path.open("rb") as handle:
            data = handle.read(max_bytes)
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def _load_dotenv_key_names(path: Path) -> list[str]:
    keys: list[str] = []
    text = _read_text(path, 128_000)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            keys.append(key)
    return keys


def _match_value(rule: SafetyRule, field: str, value: str) -> Optional[SafetyMatch]:
    if not re.search(rule.pattern, value, flags=re.IGNORECASE):
        return None
    return SafetyMatch(
        rule=rule.id,
        kind=rule.kind,
        field=field,
        redacted_value=_redact(value),
        severity=rule.severity,
    )


def _find_prod_matches(hermes_path: Path) -> list[SafetyMatch]:
    values: list[tuple[str, str, str]] = [
        ("path", "hermes_dir", str(hermes_path)),
    ]
    config_path = hermes_path / "config.yaml"
    if config_path.exists():
        text = _read_text(config_path)
        for index, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if re.search(r"prod|production|live", stripped, re.IGNORECASE):
                values.append(("path", f"config.yaml:{index}", f"line-{index}-production-like"))
            if re.search(r"(database|bucket|host|url|origin)", stripped, re.IGNORECASE):
                values.append(("domain", f"config.yaml:{index}", f"line-{index}-connection-like"))

    env_path = hermes_path / ".env"
    for key in _load_dotenv_key_names(env_path):
        values.append(("key_name", ".env", key))

    matches: list[SafetyMatch] = []
    for kind, field, value in values:
        for rule in PROD_RULES:
            if rule.kind != kind:
                continue
            match = _match_value(rule, field, value)
            if match:
                matches.append(match)
    return matches


def _classify_environment(hermes_path: Path, prod_matches: list[SafetyMatch]) -> str:
    home_runtime = Path.home() / ".hermes"
    try:
        is_default_home = hermes_path.resolve() == home_runtime.resolve()
    except OSError:
        is_default_home = hermes_path == home_runtime

    if prod_matches:
        return "prod_like"
    if is_default_home:
        return "live_runtime"
    if any(part in {"test", "staging", "dev"} for part in hermes_path.parts):
        return "test_or_staging"
    return "unknown"


def _runtime_surface(hermes_path: Path) -> list[RuntimeSurface]:
    surface: list[RuntimeSurface] = []
    for rel_path, detail in SENSITIVE_RUNTIME_PATHS:
        path = hermes_path / rel_path
        present = path.exists()
        surface.append(
            RuntimeSurface(
                path=rel_path,
                present=present,
                status="warning" if present else "ok",
                policy="never track raw runtime data" if present else "not present",
                detail=detail,
            )
        )
    return surface


def _git_surface_check(hermes_path: Path) -> SafetyCheck:
    git_dir = hermes_path / ".git"
    gitignore = hermes_path / ".gitignore"
    if not git_dir.exists():
        return SafetyCheck(
            name="Runtime git surface",
            status="ok",
            detail="Hermes home is not itself a Git checkout.",
            recommendation="Keep raw runtime state out of application repositories.",
            evidence=[str(hermes_path)],
        )

    text = _read_text(gitignore, 64_000)
    default_deny = bool(re.search(r"(^|\n)\*\s*(\n|$)", text))
    if default_deny and "sanitized/" in text and "versioned/" in text:
        return SafetyCheck(
            name="Runtime git surface",
            status="ok",
            detail="Git checkout uses a default-deny snapshot policy.",
            recommendation="Continue tracking only sanitized/ and versioned/ surfaces.",
            evidence=[".gitignore default-deny", "sanitized/", "versioned/"],
        )
    return SafetyCheck(
        name="Runtime git surface",
        status="warning",
        detail="Hermes home is a Git checkout without a recognizable default-deny policy.",
        recommendation="Track only sanitized snapshots; keep auth, sessions, logs, databases, and raw skills ignored.",
        evidence=[".git present"],
    )


def _operation_policies(environment_class: str) -> list[OperationPolicy]:
    live = environment_class in {"live_runtime", "prod_like", "unknown"}
    return [
        OperationPolicy(
            name="Gateway restart",
            policy="explicit operator action",
            status="warning" if live else "ok",
            detail="Restarting the live gateway changes runtime behavior and should stay behind a visible user action.",
        ),
        OperationPolicy(
            name="Hermes update",
            policy="two-click confirmation",
            status="ok",
            detail="The existing HUD update action already requires a second confirmation click.",
        ),
        OperationPolicy(
            name="Raw config mutation",
            policy="blocked in HUD safety baseline",
            status="blocked",
            detail="Use CLI or a staging workflow for config edits; do not add silent production writes.",
        ),
        OperationPolicy(
            name="Snapshot publishing",
            policy="sanitized-only",
            status="ok",
            detail="Only redacted replay artifacts or sanitized/versioned snapshots should leave this machine.",
        ),
    ]


def collect_safety(hermes_dir: Optional[str] = None) -> SafetyState:
    hermes_path = Path(default_hermes_dir(hermes_dir)).expanduser()
    prod_matches = _find_prod_matches(hermes_path) if hermes_path.exists() else []
    environment_class = _classify_environment(hermes_path, prod_matches)
    write_policy = "blocked" if environment_class == "prod_like" else "manual_actions_only"

    checks: list[SafetyCheck] = []
    if hermes_path.exists():
        checks.append(
            SafetyCheck(
                name="Hermes home",
                status="warning" if environment_class == "live_runtime" else "ok",
                detail=f"Runtime directory classified as {environment_class}.",
                recommendation="Treat the default ~/.hermes directory as live runtime state.",
                evidence=[str(hermes_path)],
            )
        )
    else:
        checks.append(
            SafetyCheck(
                name="Hermes home",
                status="blocked",
                detail="Hermes home does not exist.",
                recommendation="Set HERMES_HOME or start Hermes before relying on runtime diagnostics.",
                evidence=[str(hermes_path)],
            )
        )

    checks.append(
        SafetyCheck(
            name="Production-like markers",
            status="blocked" if prod_matches else "ok",
            detail="Production-like strings were detected." if prod_matches else "No production-like markers detected in path, config lines, or .env key names.",
            recommendation="Do not add write actions for targets with prod/live markers." if prod_matches else "Keep this guard in place when adding new write endpoints.",
            evidence=[f"{match.field}:{match.rule}" for match in prod_matches[:8]],
        )
    )
    checks.append(_git_surface_check(hermes_path))
    checks.append(
        SafetyCheck(
            name="Runtime data tracking",
            status="warning",
            detail="Raw runtime files are present by design and must remain untracked.",
            recommendation="Use sanitized snapshots for audit/recovery, never raw auth/session/database files.",
            evidence=[item.path for item in _runtime_surface(hermes_path) if item.present][:8],
        )
    )

    checks.sort(key=_status_order)
    return SafetyState(
        hermes_dir=str(hermes_path),
        hermes_dir_exists=hermes_path.exists(),
        environment_class=environment_class,
        write_policy=write_policy,
        checks=checks,
        runtime_surface=_runtime_surface(hermes_path),
        operation_policies=_operation_policies(environment_class),
        prod_matches=prod_matches,
    )
