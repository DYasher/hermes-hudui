# Skills 导入预览与市场状态实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 为 ZIP 批量导入增加执行前冲突预览，并为技能市场增加本地安装状态和逐项安装反馈。

**架构：** 后端复用单一 ZIP 扫描与规划逻辑完成预览和正式导入；市场搜索结果在服务层合并本地 Skills 索引。前端分别把导入流程改为“预览后确认”，把市场安装状态改为逐项状态机。

**技术栈：** FastAPI、Python `zipfile`、React 19、TypeScript、pytest、Vite。

---

## 文件结构

- `backend/services/skills_manager.py`：ZIP 扫描/动作规划、预览结果、市场本地安装索引。
- `backend/api/skills.py`：导入预览参数和服务分发。
- `frontend/src/components/SkillsPanel.tsx`：两阶段 ZIP 导入和市场逐项状态交互。
- `frontend/src/i18n/translations.ts`：新增中英文状态和操作文案。
- `tests/test_skills_api.py`：服务层和 API 行为回归。
- `tests/test_skills_frontend.py`：前端关键交互契约回归。

### 任务 1：ZIP 冲突预览后端

**文件：**
- 修改：`tests/test_skills_api.py`
- 修改：`backend/services/skills_manager.py`
- 修改：`backend/api/skills.py`

- [ ] **步骤 1：编写失败测试**

创建包含一个新 Skill 和一个已存在 Skill 的 ZIP，分别断言 `overwrite=False` 返回 `add/skip`、`overwrite=True` 返回 `add/overwrite`，并断言预览没有写入新 Skill 或改动旧 Skill。API 测试断言 `preview=true` 调用预览服务。

- [ ] **步骤 2：确认红灯**

运行：`.venv/bin/pytest tests/test_skills_api.py -k 'preview_skills_zip' -q`

预期：因 `preview_skills_zip_bytes` 或 `preview` 参数尚不存在而失败。

- [ ] **步骤 3：最少实现**

提取 `_scan_skill_zip()` 和 `_plan_skill_imports()`，新增：

```python
def preview_skills_zip_bytes(
    data: bytes,
    filename: str = "skills.zip",
    overwrite: bool = False,
    hermes_dir: str | None = None,
) -> dict[str, Any]:
    ...
```

在 `POST /api/skills/import-zip` 增加 `preview: bool = Query(False)`，为 `true` 时只调用预览服务。

- [ ] **步骤 4：确认绿灯并回归**

运行：`.venv/bin/pytest tests/test_skills_api.py -k 'preview_skills_zip or import_skills_zip' -q`

预期：相关测试全部通过。

- [ ] **步骤 5：提交**

```bash
git add backend/api/skills.py backend/services/skills_manager.py tests/test_skills_api.py
git commit -m "feat: preview skill zip import conflicts"
```

### 任务 2：ZIP 预览前端

**文件：**
- 修改：`tests/test_skills_frontend.py`
- 修改：`frontend/src/components/SkillsPanel.tsx`
- 修改：`frontend/src/i18n/translations.ts`

- [ ] **步骤 1：编写失败测试**

断言前端发送 `preview=true`，存在“预览导入/确认导入”文案和预览状态类型，更换文件或覆盖选项时清空预览，确认按钮在预览前禁用。

- [ ] **步骤 2：确认红灯**

运行：`.venv/bin/pytest tests/test_skills_frontend.py -k 'zip_import_preview' -q`

预期：缺少两阶段导入代码和文案而失败。

- [ ] **步骤 3：最少实现**

让 `importSkillsZip()` 接受 `preview` 参数。`SkillImportModal` 维护 `previewResult`，预览成功后展示 `add/overwrite/skip` 计数和明细；文件或覆盖选项变化时清空预览；正式导入成功后显示实际结果并刷新主列表。

- [ ] **步骤 4：确认绿灯并回归**

运行：`.venv/bin/pytest tests/test_skills_frontend.py -k 'zip_import_preview or exposes_zip_import' -q`

预期：相关测试全部通过。

- [ ] **步骤 5：提交**

```bash
git add frontend/src/components/SkillsPanel.tsx frontend/src/i18n/translations.ts tests/test_skills_frontend.py
git commit -m "feat: confirm skill zip imports from preview"
```

### 任务 3：市场已安装状态后端

**文件：**
- 修改：`tests/test_skills_api.py`
- 修改：`backend/services/skills_manager.py`

- [ ] **步骤 1：编写失败测试**

在临时 Hermes Skills 目录创建已安装 Skill，断言搜索结果附加 `installed=True`、分类和路径；未匹配项返回 `installed=False`。

- [ ] **步骤 2：确认红灯**

运行：`.venv/bin/pytest tests/test_skills_api.py -k 'market_search_marks_installed' -q`

预期：搜索结果缺少安装字段而失败。

- [ ] **步骤 3：最少实现**

新增本地 Skill 名称索引，在 `search_skill_market()` 规范化市场结果后合并 `installed`、`installed_category` 和 `installed_path`。

- [ ] **步骤 4：确认绿灯并回归**

运行：`.venv/bin/pytest tests/test_skills_api.py -k 'skill_market' -q`

预期：市场搜索和安装测试全部通过。

- [ ] **步骤 5：提交**

```bash
git add backend/services/skills_manager.py tests/test_skills_api.py
git commit -m "feat: mark installed skills in market results"
```

### 任务 4：市场逐项安装反馈前端

**文件：**
- 修改：`tests/test_skills_frontend.py`
- 修改：`frontend/src/components/SkillsPanel.tsx`
- 修改：`frontend/src/i18n/translations.ts`

- [ ] **步骤 1：编写失败测试**

断言 `SkillMarketItem` 包含安装字段；已安装且未强制重装时按钮禁用；存在安装中、成功、重试和重新安装文案；安装错误按项目保存。

- [ ] **步骤 2：确认红灯**

运行：`.venv/bin/pytest tests/test_skills_frontend.py -k 'market_install_status' -q`

预期：缺少安装状态和逐项反馈而失败。

- [ ] **步骤 3：最少实现**

将搜索忙碌状态与 `installStates` 分离。安装请求开始、成功和失败时只更新目标项目；成功后立即设置 `installed=true` 并刷新主 Skills 数据；已安装按钮只在强制重装开启时允许点击。

- [ ] **步骤 4：确认绿灯并回归**

运行：`.venv/bin/pytest tests/test_skills_frontend.py -k 'market_install_status or exposes_zip_import' -q`

预期：相关测试全部通过。

- [ ] **步骤 5：提交**

```bash
git add frontend/src/components/SkillsPanel.tsx frontend/src/i18n/translations.ts tests/test_skills_frontend.py
git commit -m "feat: improve skill market install feedback"
```

### 任务 5：完整验证与推送

**文件：**
- 验证：`tests/test_skills_api.py`
- 验证：`tests/test_skills_frontend.py`
- 构建：`frontend/`

- [ ] **步骤 1：运行完整 Skills 测试**

运行：`.venv/bin/pytest tests/test_skills_api.py tests/test_skills_frontend.py -q`

预期：全部通过，0 failed。

- [ ] **步骤 2：运行生产构建**

运行：`npm run build`（工作目录 `frontend`）

预期：TypeScript 和 Vite 构建退出码为 0。

- [ ] **步骤 3：浏览器验收**

在 `http://127.0.0.1:3002` 验证 ZIP 预览/确认、已安装标记、强制重装门控和逐项错误/成功反馈，确认弹窗内容可内部滚动且页面本身不跟随滚动。

- [ ] **步骤 4：检查提交和工作区**

运行：`git status --short --branch` 和 `git log -6 --oneline`。

预期：工作区无未提交代码，提交顺序与任务一致。

- [ ] **步骤 5：推送**

运行：`git push origin main`

预期：`origin/main` 更新到本次最后一个稳定提交。
