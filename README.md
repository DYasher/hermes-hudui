# Hermes HUD Web UI（中文二次开发版）

语言：**中文** | [English](README.en.md)

Hermes HUD Web UI 是一个运行在浏览器中的 Hermes Agent 监控与管理面板。它读取本机 `~/.hermes/` 数据目录和 `hermes` CLI，展示智能体身份、记忆、技能、会话、定时任务、项目、成本、模型、Gateway、插件、配置档案和实时聊天等状态。

本仓库基于 [Hermes HUD UI](https://github.com/joeynyc/hermes-hudui) 做二次开发，当前重点是让本地 Hermes Agent 更适合中文使用、配置管理和可视化调试。

上游 v0.8.0 发布时覆盖 **19 tabs**；当前二次开发版因新增 Safety 页面展示 20 个主要页面。以下发布锚点仍按上游英文名称保留，方便核对 release notes：**Hermes Teal**、**Plugin Hub**、**Gateway Managed Tools**、**Model Analytics**。

![Executive Dashboard](assets/dashboard-executive.png)

![Gateway Managed Tools](assets/gateway-tools.png)

![Model Analytics](assets/model-analytics.png)

![Plugin Hub](assets/plugin-hub.png)

## 快速开始

```bash
cd hermes-hudui
./install.sh
hermes-hudui
```

打开浏览器访问：`http://localhost:3002`

运行要求：

- Python 3.11+
- Node.js 18+
- 本机已有可运行的 Hermes Agent
- `~/.hermes/` 中已有 Hermes Agent 数据

后续再次运行：

```bash
source venv/bin/activate
hermes-hudui
```

当前 HUD 按 **Hermes Agent v0.17.0**（`state.db` schema v16）验证。Health 页面会检查 Agent 数据布局和 schema 版本；如果本机 Hermes 的磁盘结构与当前基线不一致，会给出诊断提示。

## 当前二次开发内容

### 中文化与本地化

- 全量 UI 支持英文 / 中文切换。
- 顶栏语言切换会持久化到 `localStorage`。
- UI 设置为中文时，Chat 会向 Hermes Agent 传递中文回复提示。
- README 已改为中文，后续文档也会按当前二次开发方向整理。

### 配置档案管理

Profiles 页面已扩展为完整的 Hermes 配置档案管理界面：

- 创建新的 profile。
- 导入 `config.yaml` 和 `SOUL.md`。
- 编辑模型、provider、base URL、API mode、context length、toolsets、skin、compression 和 soul 内容。
- 将 profile 设为 Hermes 全局默认 profile，语义等价于 `hermes profile use <name>`。
- 删除非默认 profile，并带名称确认。

写入路径采用 `fcntl.flock` 加锁和 `tempfile.mkstemp` + `os.replace` 原子替换，避免配置文件被并发写坏。Profile 路径做了名称校验、路径逃逸校验和 symlink 拒绝，避免通过 profile 名称写出 `~/.hermes/profiles/` 边界。

### 外挂记忆

Memory 页面支持查看和切换官方 `memory.provider` 外部记忆配置。内置 `MEMORY.md` / `USER.md` 始终启用，外部 provider 同一时间只能启用一个。当前支持的 provider 包括 Honcho、OpenViking、Mem0、Hindsight、Holographic、RetainDB、ByteRover、Supermemory 和 Memori。

### 技能库管理与双语阅读

Skills 页面已经从只读列表扩展为完整的本地技能管理界面：

- 按分类浏览技能，分类名称和说明支持中文显示，并可按名称、说明、分类、启用状态和自定义类型筛选。
- 点击技能后使用弹窗浏览 `SKILL.md`；原文固定在左侧，译文固定在右侧。英文原文翻译为中文，中文原文翻译为英文。
- 对照阅读支持按标题和内容锚点同步滚动，长文档在弹窗内部滚动，不会带动整个页面。
- 翻译 provider 和模型从当前 Hermes 配置中读取，只展示已配置 API key 的 provider；可以应用指定模型、手动翻译或失败后重试。
- 译文按原文、目标语言、provider 和模型缓存到 Hermes Skills 目录之外，并显示生成译文所使用的模型，避免重复消耗 token。
- 支持创建、编辑和校验 `SKILL.md`，以及启用、禁用、复制、移动和带二次确认的删除操作。
- 详情弹窗可查看 `references`、`scripts`、`assets`、`templates` 等支持文件树。
- 支持 ZIP 批量导入和导入前预览；恢复操作只接受 ZIP，并可选择覆盖已有技能。
- 支持一键备份、备份历史、下载和删除备份，以及对已选技能进行批量导出。
- 批量启用、禁用、导出、移动和删除均带二次确认、进度统计和失败项重试。
- 技能市场支持搜索、安装、查看本地与远程版本，并对存在新版本的技能执行更新。

Skills 写操作使用线程锁和跨进程文件锁串行化。创建、复制和 ZIP 导入先写入扫描器忽略的 staging 目录，再发布到目标分类；多技能导入任一项失败时会回滚本次已提交内容。路径、symlink、ZIP slip、文件数量和解压体积均会校验，删除、覆盖和移动前的备份保存在 HUD 缓存目录，而不是 Hermes Skills 目录。

### 主题、背景与界面调优

- 默认主题改为 **Hermes Teal**，接近 Nous / Hermes 官方面板配色。
- 提供 8 套主题：Hermes Teal、Graphite Grid、Aurora Pulse、Sunset Signal、Neural Awakening、Blade Runner、fsociety、Anime。
- 顶栏主题面板增加自定义背景图设置，支持图片 URL 或 `data:image/...`。
- 增加自动壁纸模式，当前使用 `https://bing.img.run/rand.php` 获取随机 Bing 图片。
- 背景层从单个面板移动到 `.hud-workspace`，让底部内容和页面背景保持一致。
- 新增 wallpaper / glass CSS 变量，主题透明度和玻璃效果集中由 CSS 自定义属性控制。
- 顶部标签栏支持横向滚动，窗口变窄时仍能访问全部页面。

### Gateway、插件与运行状态

- Gateway 页面展示 Nous Tool Gateway、直接密钥和不可用状态下的工具路由情况。
- 支持查看 web search、image generation、text-to-speech、browser automation 等 managed tools 的来源。
- `Update hermes` 操作需要二次确认，并显示最近运行状态、日志路径、日志尾部和退出码。
- Plugin Hub 展示 dashboard 插件、agent 插件、入口点、运行状态、鉴权命令和安全启用 / 禁用 / 更新操作。
- Providers 页面展示 OAuth / API key provider 的连接状态、过期状态、scope 和当前活动 provider。
- Safety 页面汇总运行时安全姿态、写入策略、环境分类和生产路径匹配。

### Hermes Replay

Replay 页面把 Hermes Agent 运行记录导出为可分享的证明材料。

![Hermes Replay tab](assets/replay-tab.png)

当前本地导出内容包括：

- 脱敏 JSON replay
- GitHub 可直接阅读的 Markdown
- 独立 HTML replay
- 1200 x 630 PNG 分享卡片
- fork-safe `fork.json`

示例脱敏 replay：[`assets/example-replay.redacted.json`](assets/example-replay.redacted.json)

Safe Share Mode 是默认导出策略（**Safe Share Mode is the default export posture**）。它会在写出分享材料前脱敏原始工具参数、终端输出、assistant reasoning、类似 token 的值、邮箱、本地路径和其他敏感字段。导出文件包含本机生成的 hash 和 Ed25519 签名，用于证明本地文件完整性，**not external third-party attestation**。

远程发布是可选能力。你可以在 Replay 页配置 GitHub Pages 或其他 git 静态站点仓库，然后手动同步公开 gallery。远程同步默认关闭，只有显式点击同步才会推送，且只包含 Safe Share Mode 产物。

## 页面概览

当前面板包含 20 个主要页面：

- Dashboard：健康、成本、模型、provider / gateway 风险和行动项总览。
- Memory：查看和编辑 Hermes memory / user memory。
- Skills：双语对照阅读、创建和编辑技能，管理启用状态，执行批量操作、ZIP 导入恢复、备份和技能市场安装。
- Sessions：搜索和检查 Hermes 会话。
- Replay：导出脱敏运行证明材料。
- Cron：查看和管理定时任务。
- Projects：查看项目活动、分支和语言信息。
- Health：检查文件系统、schema、数据布局和 Agent 兼容性。
- Agents：查看 Agent 运行相关状态。
- Chat：在 HUD 内与 Hermes Agent 实时对话。
- Profiles：创建、导入、编辑、切换为 Hermes 全局默认 profile，以及删除 profile。
- Token Costs：查看 token 和成本统计。
- Corrections：查看纠错记录。
- Patterns：查看行为模式和活动趋势。
- Sudo：查看 sudo / 权限相关治理信息。
- Providers：查看 OAuth 和 API key provider。
- Gateway：查看 Gateway 状态和 managed tools。
- Model Info：查看模型使用与会话分析。
- Plugins：查看和管理 dashboard / agent 插件。
- Safety：查看运行时安全姿态。

数据通过 WebSocket 实时更新，正常使用时不需要手动刷新页面。

## 开发调试

后端开发模式：

```bash
hermes-hudui --dev
```

前端开发模式：

```bash
cd frontend
npm run dev
```

前端开发服务器默认运行在 `http://localhost:5173`，并将 `/api/*` 代理到 `http://localhost:3002`。

常用验证命令：

```bash
pytest
cd frontend && npm run build
```

## 键盘快捷键

| 按键 | 操作 |
|------|------|
| `1`–`9`、`0` | 切换主要标签页 |
| `t` | 打开主题选择器 |
| `Ctrl+K` | 打开命令面板 |

## 安全边界

Hermes HUD UI 默认按本机可信工具设计，请只在本机或受信任网络中使用。Profiles、Memory、Skills、Cron、Gateway 等页面包含写入配置、修改技能目录、启动命令或调用 `hermes` CLI 的能力；如果把服务暴露到公网或不受信任网络，应把这些接口视为高风险管理接口。

Profile 与 Skills 写入已经做了路径校验、symlink 拒绝、并发锁、staging 和必要的事务回滚，但它们仍然会修改本机 `~/.hermes/` 下的真实配置与技能。执行写操作前请确认当前 Hermes home 指向的是你希望管理的实例。

## 与 TUI 的关系

Hermes HUD Web UI 是 [hermes-hud](https://github.com/joeynyc/hermes-hud) 的浏览器伴侣。两者都独立读取同一个 `~/.hermes/` 数据目录，可以只使用其中一个，也可以同时使用。

如需同时安装 TUI：

```bash
pip install 'hermes-hudui[tui]'
```

在 zsh 中需要保留引号，避免 `[tui]` 被当作 glob 解析。

## 平台支持

macOS · Linux · WSL

## 许可证

MIT，详见 [LICENSE](LICENSE)。
