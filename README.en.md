# Hermes HUD Web UI (Chinese Fork)

Language: [中文](README.md) | **English**

Hermes HUD Web UI is a browser-based monitoring and management panel for Hermes Agent. It reads the local `~/.hermes/` data directory and the `hermes` CLI, then shows agent identity, memory, skills, sessions, cron jobs, projects, cost, models, Gateway, plugins, profiles, and live chat.

This repository is a secondary-development fork of [Hermes HUD UI](https://github.com/joeynyc/hermes-hudui). The current focus is making local Hermes Agent usage more suitable for Chinese workflows, profile management, and visual debugging.

![Executive Dashboard](assets/dashboard-executive.png)

![Gateway Managed Tools](assets/gateway-tools.png)

![Model Analytics](assets/model-analytics.png)

![Plugin Hub](assets/plugin-hub.png)

## Quick Start

```bash
cd hermes-hudui
./install.sh
hermes-hudui
```

Open `http://localhost:3002` in your browser.

Requirements:

- Python 3.11+
- Node.js 18+
- A working local Hermes Agent
- Hermes Agent data under `~/.hermes/`

For later runs:

```bash
source venv/bin/activate
hermes-hudui
```

The current HUD has been verified against **Hermes Agent v0.17.0** (`state.db` schema v16). The Health page checks the Agent data layout and schema version; if your local Hermes disk layout drifts from this baseline, it will report diagnostics.

## Current Fork Changes

### Chinese Localization

- Full UI support for English / Chinese switching.
- The header language toggle persists to `localStorage`.
- When the UI is set to Chinese, Chat passes a Chinese-response hint to Hermes Agent.
- README now supports Chinese / English switching, and future docs will follow this fork's direction.

### Profile Management

The Profiles page has been expanded into a full Hermes profile management interface:

- Create new profiles.
- Import `config.yaml` and `SOUL.md`.
- Edit model, provider, base URL, API mode, context length, toolsets, skin, compression, and soul content.
- Set a profile as the global Hermes default, equivalent to `hermes profile use <name>`.
- Delete non-default profiles with name confirmation.

Write paths use `fcntl.flock` plus `tempfile.mkstemp` and `os.replace` for locked atomic writes. Profile paths are protected with name validation, path escape checks, and symlink rejection to avoid writing outside `~/.hermes/profiles/`.

### Memory Providers

The Memory page can inspect and switch the official `memory.provider` external memory setting. Built-in `MEMORY.md` / `USER.md` memory stays enabled, and only one external provider can be active at a time. Supported providers include Honcho, OpenViking, Mem0, Hindsight, Holographic, RetainDB, ByteRover, Supermemory, and Memori.

### Skills Management and Bilingual Reading

The Skills page has grown from a read-only list into a complete local skill management interface:

- Browse skills by category with localized category names and descriptions, then filter by name, description, category, enabled state, or custom type.
- Open `SKILL.md` in a modal with the original fixed on the left and its translation on the right. English source documents are translated into Chinese, while Chinese source documents are translated into English.
- Comparison mode synchronizes scrolling by heading and content anchors. Long documents scroll inside the modal instead of moving the entire page.
- Translation providers and models come from the current Hermes configuration. Only providers with a configured API key are shown, and users can apply a model, translate manually, or retry a failed translation.
- Translations are cached outside the Hermes Skills directory by source content, target language, provider, and model. The UI records which model generated each translation to avoid repeated token usage.
- Create, edit, and validate `SKILL.md`, then enable, disable, duplicate, move, or delete a skill with confirmation.
- Inspect support files under `references`, `scripts`, `assets`, `templates`, and related directories from the detail modal.
- Import multiple skills from ZIP with a preview step. Restore accepts ZIP archives only and can overwrite existing skills when explicitly selected.
- Create one-click backups, browse backup history, download or delete backups, and export selected skills as a batch.
- Batch enable, disable, export, move, and delete operations include confirmation, progress reporting, and failed-item retry.
- Search the skills market, install skills, compare local and remote versions, and update installed skills when a newer version is available.

Skills writes are serialized with thread and cross-process file locks. Create, duplicate, and ZIP import operations write into a scanner-excluded staging area before publishing to a category, and a multi-skill import rolls back changes already committed by that import if a later item fails. Paths, symlinks, ZIP slip, file count, and expanded archive size are validated. Backups created before delete, overwrite, or move operations live in the HUD cache rather than the Hermes Skills directory.

### Themes, Backgrounds, and UI Tuning

- The default theme is now **Hermes Teal**, close to the official Nous / Hermes dashboard palette.
- Eight themes are available: Hermes Teal, Graphite Grid, Aurora Pulse, Sunset Signal, Neural Awakening, Blade Runner, fsociety, and Anime.
- The header theme menu supports custom background images via image URL or `data:image/...`.
- Auto wallpaper mode uses `https://bing.img.run/rand.php` for random Bing images.
- The background layer moved from individual panels to `.hud-workspace`, keeping the page background consistent.
- Wallpaper / glass CSS variables centralize theme transparency and glass effects.
- The top tab bar supports horizontal scrolling, so all pages remain reachable on narrow windows.

### Gateway, Plugins, and Runtime Status

- The Gateway page shows managed-tool routing through Nous Tool Gateway, direct credentials, or unavailable state.
- It covers web search, image generation, text-to-speech, browser automation, and related managed tools.
- The `Update hermes` action requires a second confirmation and displays recent status, log path, log tail, and exit code.
- Plugin Hub shows dashboard plugins, agent plugins, entry points, runtime status, auth commands, and safe enable / disable / update actions.
- Providers shows OAuth / API-key provider status, expiry, scope, and the active provider.
- Safety summarizes runtime safety posture, write policy, environment classification, and production path matches.

### Hermes Replay

Replay turns Hermes Agent runs into shareable proof artifacts.

![Hermes Replay tab](assets/replay-tab.png)

Current local exports include:

- Redacted JSON replay
- GitHub-ready Markdown
- Standalone HTML replay
- 1200 x 630 PNG share card
- Fork-safe `fork.json`

Safe Share Mode is the default export posture. It redacts raw tool arguments, terminal output, assistant reasoning, token-like values, emails, local paths, and other sensitive fields before writing share artifacts. Exports include local hashes and Ed25519 signatures generated on this machine; they prove local artifact integrity, not third-party attestation.

Remote publishing is optional. You can configure GitHub Pages or another git-backed static host in the Replay page, then manually sync a public gallery. Remote sync is off by default, only runs when explicitly triggered, and only includes Safe Share Mode artifacts.

## Pages

The panel currently includes 20 main pages:

- Dashboard: health, cost, model, provider / gateway risk, and action summary.
- Memory: view and edit Hermes memory / user memory.
- Skills: bilingual reading, skill creation and editing, enable-state management, batch actions, ZIP import and restore, backups, and skills-market installation.
- Sessions: search and inspect Hermes sessions.
- Replay: export redacted run proof artifacts.
- Cron: view and manage cron jobs.
- Projects: inspect project activity, branches, and language info.
- Health: check filesystem, schema, data layout, and Agent compatibility.
- Agents: view Agent runtime-related status.
- Chat: talk to Hermes Agent inside the HUD.
- Profiles: create, import, edit, switch the global Hermes default profile, and delete profiles.
- Token Costs: inspect token and cost statistics.
- Corrections: view correction records.
- Patterns: inspect behavior patterns and activity trends.
- Sudo: review sudo / permission governance information.
- Providers: inspect OAuth and API-key providers.
- Gateway: inspect Gateway status and managed tools.
- Model Info: inspect model usage and session analytics.
- Plugins: view and manage dashboard / agent plugins.
- Safety: inspect runtime safety posture.

Data updates in real time through WebSocket, so normal usage does not require manual refreshes.

## Development

Backend development mode:

```bash
hermes-hudui --dev
```

Frontend development mode:

```bash
cd frontend
npm run dev
```

The frontend dev server runs at `http://localhost:5173` by default and proxies `/api/*` to `http://localhost:3002`.

Common verification commands:

```bash
pytest
cd frontend && npm run build
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1`–`9`, `0` | Switch main tabs |
| `t` | Open theme picker |
| `Ctrl+K` | Open command palette |

## Safety Boundary

Hermes HUD UI is designed as a trusted local tool. Use it only on localhost or trusted networks. Profiles, Memory, Skills, Cron, Gateway, and related pages can write config, modify skill directories, start commands, or call the `hermes` CLI; if you expose the service to the public internet or an untrusted network, treat these APIs as high-risk management endpoints.

Profile and Skills writes use path validation, symlink rejection, locks, staging, and transactional rollback where needed, but they still modify real local configuration and skills under `~/.hermes/`. Confirm that the current Hermes home points to the instance you intend to manage before running write operations.

## Relationship to the TUI

Hermes HUD Web UI is the browser companion to [hermes-hud](https://github.com/joeynyc/hermes-hud). Both independently read the same `~/.hermes/` data directory. You can use either one, or both at the same time.

To install the TUI as well:

```bash
pip install 'hermes-hudui[tui]'
```

Keep the quotes in zsh so `[tui]` is not parsed as a glob.

## Platform Support

macOS · Linux · WSL

## License

MIT. See [LICENSE](LICENSE).
