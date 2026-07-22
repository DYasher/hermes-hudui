# Skills 模块收尾实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 补齐 Skills 批量任务反馈、内容校验和自动化测试，并完成分类移动、复制、市场更新、备份历史及文件树功能。

**架构：** 后端服务层继续负责路径安全、文件变更和 ZIP 数据；FastAPI 暴露小而明确的操作端点。前端把批量执行状态提取为可测试的 TypeScript 单元，主面板只负责选择、确认、进度和结果展示；新增功能沿用现有弹窗和内部滚动布局。

**技术栈：** FastAPI、Pydantic、Python `pathlib`/`zipfile`/PyYAML、React 19、TypeScript、Node test runner、pytest、Vite。

---

## 文件结构

- `frontend/src/lib/skillBatch.ts`：批量确认状态和顺序执行器。
- `frontend/src/lib/skillBatch.test.ts`：Node 原生测试，覆盖确认、切换、进度和失败继续。
- `backend/services/skills_manager.py`：校验、移动、复制、备份历史和文件树服务。
- `backend/api/skills.py`：新增 Skills 管理端点和请求模型。
- `backend/collectors/models.py`、`backend/collectors/skills.py`：向 Skill 元数据暴露版本和作者。
- `frontend/src/components/SkillsPanel.tsx`：进度/结果、校验、移动、复制、市场更新、备份历史和文件树 UI。
- `frontend/src/i18n/translations.ts`：全部新增中英文文案。
- `tests/test_skills_api.py`：后端行为与安全边界测试。
- `tests/test_skills_frontend.py`：前端契约回归。
- `frontend/package.json`：增加 Node 原生单元测试命令。

### 任务 1：批量任务状态和自动化测试

- [x] 新建 `skillBatch.test.ts`，测试第一次请求只进入确认、第二次同操作才通过、切换操作替换确认、重置返回空状态。
- [x] 运行 `npm test`，确认因模块缺失失败。
- [x] 实现 `resolveBatchConfirmation()` 和 `runSkillBatch()`；执行器逐项调用操作，持续报告 `completed/total`，捕获单项错误并继续。
- [x] 将批量启用、禁用、删除接入执行器；导出保持单请求，但使用同一进度/结果结构。
- [x] 在批量栏显示进度、成功数、失败项和“重试失败项”；二次确认显示选中数量。
- [x] 运行 `npm test`、Skills 前端测试和生产构建。
- [x] 提交 `feat: report batch skill operation results`。

### 任务 2：Skill 完整性检查

- [ ] 为 `validate_skill_content()` 编写测试：合法 frontmatter、格式错误、名称冲突、缺少说明、缺失本地引用和越界引用。
- [ ] 新增 `POST /api/skills/validate`；保存前对错误执行硬阻断，警告允许保存。
- [ ] ZIP 预览为每个 `SKILL.md` 返回校验错误/警告，正式导入拒绝包含错误的 Skill。
- [ ] 编辑器增加“检查”操作和错误/警告列表，保存前自动检查。
- [ ] 运行 API、前端测试和构建。
- [ ] 提交 `feat: validate skill content before writes`。

### 任务 3：批量移动分类和复制 Skill

- [ ] 测试 `move_skill(path, category)`：移动完整目录、拒绝目标冲突、备份原目录、拒绝越界路径。
- [ ] 测试 `duplicate_skill(path, category, name)`：复制支持文件、更新 frontmatter 名称、拒绝目标冲突和符号链接。
- [ ] 新增 `POST /api/skills/move` 与 `POST /api/skills/duplicate`。
- [ ] 批量栏增加目标分类输入和需二次确认的“移动分类”，接入进度和失败重试。
- [ ] Skill 详情增加复制表单，成功后刷新并打开副本。
- [ ] 运行测试和构建。
- [ ] 提交 `feat: move and duplicate skills`。

### 任务 4：技能市场版本和更新

- [ ] 扩展 `SkillInfo` 版本/作者元数据并测试序列化。
- [ ] 市场搜索结果增加 `installed_version` 和 `update_available`；仅在市场版本与本地版本都存在且不相同时标记更新。
- [ ] 市场条目显示本地/市场版本；有更新时显示“一键更新”，自动使用强制安装。
- [ ] 保留已安装、重装、重试和逐项状态行为。
- [ ] 运行市场测试、前端测试和构建。
- [ ] 提交 `feat: show and install skill market updates`。

### 任务 5：备份历史管理

- [ ] 测试创建持久化 ZIP、按时间倒序列出、读取下载和删除；文件名必须由服务生成并拒绝路径穿越。
- [ ] 新增 `POST/GET /api/skills/backups` 和 `GET/DELETE /api/skills/backups/{filename}`。
- [ ] 将“备份 Skills”改为创建并下载持久备份；新增备份历史弹窗，支持下载和二次确认删除。
- [ ] 运行测试和构建。
- [ ] 提交 `feat: manage skill backup history`。

### 任务 6：Skill 文件树

- [ ] 测试文件树只返回 Skill 根目录内普通文件，按相对路径排序并跳过符号链接和嵌套 Skill。
- [ ] 新增 `GET /api/skills/files?path=...`，返回 `path/name/kind/size`。
- [ ] Skill 详情弹窗增加可折叠文件树，区分 references、scripts、assets、templates 和其他文件。
- [ ] 运行测试和构建。
- [ ] 提交 `feat: show skill support file tree`。

### 任务 7：完整验收与收尾

- [ ] 运行 `.venv/bin/pytest -q`，要求 0 failed。
- [ ] 运行 `npm test` 和 `npm run build`，要求退出码 0。
- [ ] 将 `frontend/dist` 同步到 `backend/static`，确认哈希文件一致。
- [ ] 在 `http://127.0.0.1:3002` 验证批量失败继续/重试、移动、复制、市场更新状态、备份历史、校验结果和文件树内部滚动。
- [ ] 执行最终代码审查，修复所有 Critical/Important 问题。
- [ ] 推送全部提交到 `origin/main`，确认工作区干净并记录最终提交。
