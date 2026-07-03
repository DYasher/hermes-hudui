# 外挂记忆社区提供商实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 在现有“外挂记忆控制台”中完整接入 Cognee、agentmemory、MemOS 三个社区第三方记忆系统，支持 provider-specific 配置、只读健康检查、安装/关闭指引和可展示的外部记忆状态。

**架构：** 先收口当前 UI 重构，再把 `backend/api/memory.py` 中的 provider 元数据和读写逻辑拆成可维护的服务模块。后端成为 provider 分组、配置字段、模式、健康检查和外部视图能力的唯一来源，前端只负责渲染控制台页签和表单。

**技术栈：** FastAPI、Pydantic、pytest、React、TypeScript、Vite、Tailwind、Hermes config.yaml / .env / provider JSON 文件。

---

## 上游依据

- Cognee：GitHub README 说明它是面向 agents 的开源 AI memory platform，支持 Python 安装、CLI、Docker API、MCP server，示例端口包括 API `8000` 和 MCP `8001`。
- agentmemory：GitHub README 说明它支持 server、REST API、MCP，默认本地 server 在 `:3111`，并有 `agentmemory connect` 与 Hermes provider 相关说明。
- MemOS：GitHub README 说明它提供 Cloud API 和 Self-Hosted 两种部署，self-hosted 需要配置 `.env`，支持 OpenAI、Azure OpenAI、Qwen、DeepSeek、MiniMax、Ollama、HuggingFace、vLLM 等后端。

这些上游项目变化较快，实现时必须保守：HUD 只做配置写入、只读探测和状态展示，不自动执行安装、卸载、启动 Docker、写外部 agent 配置。

## 文件结构

- 修改：`backend/api/memory.py`
  - 保留 FastAPI route 和内置 `MEMORY.md` / `USER.md` 逻辑。
  - 将 provider catalog、配置字段读写、健康检查、外部视图委托给服务层。
- 创建：`backend/services/memory_provider_catalog.py`
  - 集中维护 provider 元数据、分组、配置模式、能力矩阵、安装指引。
- 创建：`backend/services/memory_provider_config.py`
  - 负责读取/写入 `.env`、provider JSON、`config.yaml` 中的 provider 配置字段。
- 创建：`backend/services/memory_provider_health.py`
  - 负责只读依赖检查、端口/HTTP 探测、CLI 探测。
- 创建：`backend/services/memory_provider_external.py`
  - 负责 provider-specific 外部视图；第一版只返回安全的摘要、原因、只读项目，不写入外部系统。
- 修改：`frontend/src/components/MemoryPanel.tsx`
  - 使用后端返回的 `group` / `group_label` 替代前端硬编码 `communityProviderIds`。
  - 在安装指南页签中按 provider mode 展示命令和风险提示。
  - 在外部记忆视图中支持“摘要型 provider”和“条目型 provider”两种展示。
- 修改：`frontend/src/i18n/translations.ts`
  - 新增 Cognee、agentmemory、MemOS 配置字段、健康检查、安装指南文案。
- 修改：`tests/test_memory_api.py`
  - 覆盖 provider catalog、配置读写、健康检查、外部视图和安全边界。
- 修改：`tests/test_memory_frontend.py`
  - 覆盖 provider 分组来自 API、页签内容位置、社区 provider 配置表单和状态显示。
- 修改：`backend/static/index.html` 和强制添加新构建资产
  - 仅在前端构建通过后同步 `frontend/dist` 到 `backend/static`。

## 阶段 0：收口当前 UI 重构

**文件：**
- 修改：当前已有 `frontend/src/components/MemoryPanel.tsx`
- 修改：当前已有 `frontend/src/i18n/translations.ts`
- 修改：当前已有 `tests/test_memory_frontend.py`
- 修改：当前已有 `backend/static/index.html`
- 添加：当前构建产物 `backend/static/assets/index-2_PhGD-n.js`
- 添加：当前构建产物 `backend/static/assets/index-BTkRz3Wr.css`

- [ ] **步骤 0.1：确认当前工作区只包含本轮 UI 重构和已知未跟踪目录**

运行：

```bash
git status --short
```

预期：

```text
 M backend/static/index.html
 M frontend/src/components/MemoryPanel.tsx
 M frontend/src/i18n/translations.ts
 M tests/test_memory_frontend.py
?? .claude/
?? docs/superpowers/
```

`.claude/` 是既有未跟踪目录，不纳入提交。`docs/superpowers/` 是本计划文档。

- [ ] **步骤 0.2：重新运行验证**

运行：

```bash
npm run build
.venv/bin/pytest -q
git diff --check
```

预期：

```text
vite build exits 0
245 passed
git diff --check has no output
```

- [ ] **步骤 0.3：同步静态资源**

运行：

```bash
cp -r frontend/dist/* backend/static/
```

预期：`backend/static/index.html` 指向最新 JS/CSS hash。

- [ ] **步骤 0.4：提交当前 UI 重构**

运行：

```bash
git add frontend/src/components/MemoryPanel.tsx frontend/src/i18n/translations.ts tests/test_memory_frontend.py backend/static/index.html
git add -f backend/static/assets/index-2_PhGD-n.js backend/static/assets/index-BTkRz3Wr.css
git commit -m "refactor: simplify external memory console"
```

预期：生成一个只包含 UI 控制台重构和静态 bundle 更新的 commit。

## 阶段 1：Provider catalog 服务化

**文件：**
- 创建：`backend/services/memory_provider_catalog.py`
- 创建：`backend/services/memory_provider_config.py`
- 修改：`backend/api/memory.py`
- 测试：`tests/test_memory_api.py`

- [ ] **步骤 1.1：编写失败测试，要求后端返回 provider 分组**

在 `tests/test_memory_api.py` 增加：

```python
def test_memory_provider_payload_includes_provider_groups(hermes_home: Path) -> None:
    status = get_memory_providers()

    assert status["providers"]["honcho"]["group"] == "official"
    assert status["providers"]["mem0"]["group"] == "official"
    assert status["providers"]["cognee"]["group"] == "community"
    assert status["providers"]["agentmemory"]["group"] == "community"
    assert status["providers"]["memos"]["group"] == "community"
```

运行：

```bash
.venv/bin/pytest tests/test_memory_api.py::test_memory_provider_payload_includes_provider_groups -q
```

预期：FAIL，原因是 `cognee` / `agentmemory` / `memos` 不存在或没有 `group`。

- [ ] **步骤 1.2：创建 catalog 模块**

创建 `backend/services/memory_provider_catalog.py`，至少包含：

```python
OFFICIAL_PROVIDER_GROUP = "official"
COMMUNITY_PROVIDER_GROUP = "community"

MEMORY_PROVIDER_OPTIONS = {
    # 先从 backend/api/memory.py 原样搬迁现有 honcho/openviking/mem0/
    # hindsight/holographic/retaindb/byterover/supermemory/memori。
}

MEMORY_PROVIDER_CAPABILITIES = {
    # 先从 backend/api/memory.py 原样搬迁。
}

OFFICIAL_SCHEMA_PROVIDERS = {
    "honcho",
    "openviking",
    "mem0",
    "hindsight",
    "holographic",
    "retaindb",
    "supermemory",
}

COMMUNITY_SCHEMA_PROVIDERS = {
    "cognee",
    "agentmemory",
    "memos",
}

def provider_group(provider: str) -> str:
    return COMMUNITY_PROVIDER_GROUP if provider in COMMUNITY_SCHEMA_PROVIDERS else OFFICIAL_PROVIDER_GROUP
```

修改 `backend/api/memory.py`：

```python
from backend.services.memory_provider_catalog import (
    MEMORY_PROVIDER_CAPABILITIES,
    MEMORY_PROVIDER_OPTIONS,
    OFFICIAL_SCHEMA_PROVIDERS,
    provider_group,
)
```

并在 `_memory_provider_payload()` 的 provider payload 中加入：

```python
"group": provider_group(key),
```

- [ ] **步骤 1.3：运行阶段 1 测试**

运行：

```bash
.venv/bin/pytest tests/test_memory_api.py::test_memory_provider_payload_includes_provider_groups -q
.venv/bin/pytest tests/test_memory_api.py -q
```

预期：新增测试 PASS，现有 memory API 测试 PASS。

- [ ] **步骤 1.4：提交 provider catalog 拆分**

运行：

```bash
git add backend/api/memory.py backend/services/memory_provider_catalog.py tests/test_memory_api.py
git commit -m "refactor: extract memory provider catalog"
```

预期：一个纯重构加 group 字段的 commit。

## 阶段 2：接入 Cognee provider 元数据和只读探测

**文件：**
- 修改：`backend/services/memory_provider_catalog.py`
- 修改：`backend/services/memory_provider_health.py`
- 修改：`tests/test_memory_api.py`
- 修改：`frontend/src/components/MemoryPanel.tsx`
- 修改：`frontend/src/i18n/translations.ts`

- [ ] **步骤 2.1：编写 Cognee provider payload 测试**

在 `tests/test_memory_api.py` 增加：

```python
def test_cognee_provider_payload_describes_modes_and_minimum_config(hermes_home: Path) -> None:
    status = get_memory_providers()
    cognee = status["providers"]["cognee"]
    modes = {mode["id"]: mode for mode in cognee["config_modes"]}
    fields = {field["name"]: field for field in cognee["config_fields"]}

    assert cognee["label"] == "Cognee"
    assert cognee["group"] == "community"
    assert cognee["storage"] == "local/docker/mcp"
    assert set(modes) == {"python_cli", "docker_api", "mcp_http"}
    assert modes["python_cli"]["required_fields"] == ["LLM_API_KEY"]
    assert modes["docker_api"]["required_fields"] == ["COGNEE_API_URL"]
    assert modes["mcp_http"]["required_fields"] == ["COGNEE_MCP_URL"]
    assert fields["LLM_API_KEY"]["secret"] is True
    assert fields["COGNEE_API_URL"]["mode_ids"] == ["docker_api"]
    assert fields["COGNEE_MCP_URL"]["mode_ids"] == ["mcp_http"]
```

运行：

```bash
.venv/bin/pytest tests/test_memory_api.py::test_cognee_provider_payload_describes_modes_and_minimum_config -q
```

预期：FAIL，`cognee` 未定义。

- [ ] **步骤 2.2：实现 Cognee catalog**

在 `MEMORY_PROVIDER_OPTIONS` 加入：

```python
"cognee": {
    "label": "Cognee",
    "storage": "local/docker/mcp",
    "dependencies": [
        {"kind": "python", "name": "cognee"},
        {"kind": "command", "name": "cognee-cli"},
    ],
    "required_fields": [],
    "config_files": [".env", "cognee.json"],
    "fields": [
        {
            "name": "LLM_API_KEY",
            "label": "LLM API key",
            "storage": "env",
            "secret": True,
            "help": "Required for local Cognee Python/CLI memory pipelines.",
        },
        {
            "name": "COGNEE_API_URL",
            "label": "API URL",
            "storage": "env",
            "secret": False,
            "help": "Cognee API server URL, for example http://localhost:8000.",
        },
        {
            "name": "COGNEE_MCP_URL",
            "label": "MCP URL",
            "storage": "env",
            "secret": False,
            "help": "Cognee MCP HTTP/SSE endpoint, for example http://localhost:8001.",
        },
        {
            "name": "COGNEE_DATASET",
            "label": "Dataset",
            "storage": "json",
            "path": "cognee.json",
            "secret": False,
            "help": "Dataset name used for Hermes memory.",
        },
    ],
    "modes": [
        {
            "id": "python_cli",
            "label": "Python / CLI",
            "storage": "local",
            "description": "Local Cognee package and cognee-cli.",
            "fields": ["LLM_API_KEY", "COGNEE_DATASET"],
            "required_fields": ["LLM_API_KEY"],
            "required_any": [],
            "optional_fields": ["COGNEE_DATASET"],
        },
        {
            "id": "docker_api",
            "label": "Docker API",
            "storage": "self-hosted",
            "description": "Cognee API server, usually exposed on localhost:8000.",
            "fields": ["COGNEE_API_URL", "COGNEE_DATASET"],
            "required_fields": ["COGNEE_API_URL"],
            "required_any": [],
            "optional_fields": ["COGNEE_DATASET"],
        },
        {
            "id": "mcp_http",
            "label": "MCP HTTP",
            "storage": "mcp",
            "description": "Cognee MCP server, usually exposed on localhost:8001.",
            "fields": ["COGNEE_MCP_URL", "COGNEE_DATASET"],
            "required_fields": ["COGNEE_MCP_URL"],
            "required_any": [],
            "optional_fields": ["COGNEE_DATASET"],
        },
    ],
    "setup_command": "uv pip install cognee && cognee-cli -ui",
    "config_command": "hermes config set memory.provider cognee",
    "notes": [
        "Docker API commonly uses port 8000.",
        "MCP server commonly uses port 8001.",
    ],
},
```

在 `MEMORY_PROVIDER_CAPABILITIES` 加入：

```python
"cognee": {
    "external_read": True,
    "external_read_mode": "provider_summary",
    "direct_hud_config": True,
    "requires_network": False,
    "local_storage": True,
    "supports_tools": True,
    "supports_auto_recall": True,
    "supports_session_ingest": True,
    "supports_manual_write": True,
    "hooks": ["mcp", "tools", "session_ingest"],
},
```

- [ ] **步骤 2.3：只读健康检查不假设 Cognee 私有 API**

在 `backend/services/memory_provider_health.py` 添加：

```python
def check_http_endpoint(url: str) -> dict:
    if not url:
        return {"kind": "http", "name": "endpoint", "ok": False, "detail": "not_configured"}
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as response:
            return {
                "kind": "http",
                "name": url,
                "ok": 200 <= response.status < 500,
                "detail": f"HTTP {response.status}",
            }
    except Exception as exc:
        return {"kind": "http", "name": url, "ok": False, "detail": str(exc)}
```

Cognee health 使用 `COGNEE_API_URL` 或 `COGNEE_MCP_URL` 做只读 GET 探测；Python/CLI 模式继续使用 dependency checks。

- [ ] **步骤 2.4：运行 Cognee 测试并提交**

运行：

```bash
.venv/bin/pytest tests/test_memory_api.py::test_cognee_provider_payload_describes_modes_and_minimum_config -q
.venv/bin/pytest tests/test_memory_api.py -q
```

预期：PASS。

提交：

```bash
git add backend/services/memory_provider_catalog.py backend/services/memory_provider_health.py tests/test_memory_api.py
git commit -m "feat: add cognee memory provider metadata"
```

## 阶段 3：接入 agentmemory provider

**文件：**
- 修改：`backend/services/memory_provider_catalog.py`
- 修改：`backend/services/memory_provider_health.py`
- 修改：`backend/services/memory_provider_external.py`
- 修改：`tests/test_memory_api.py`

- [ ] **步骤 3.1：编写 agentmemory payload 测试**

在 `tests/test_memory_api.py` 增加：

```python
def test_agentmemory_provider_payload_describes_rest_and_mcp_modes(hermes_home: Path) -> None:
    status = get_memory_providers()
    provider = status["providers"]["agentmemory"]
    modes = {mode["id"]: mode for mode in provider["config_modes"]}
    fields = {field["name"]: field for field in provider["config_fields"]}

    assert provider["label"] == "agentmemory"
    assert provider["group"] == "community"
    assert modes["rest_server"]["required_fields"] == ["AGENTMEMORY_URL"]
    assert modes["mcp_server"]["required_fields"] == ["AGENTMEMORY_MCP_COMMAND"]
    assert fields["AGENTMEMORY_SECRET"]["secret"] is True
    assert provider["capabilities"]["external_read_mode"] == "provider_summary"
```

运行：

```bash
.venv/bin/pytest tests/test_memory_api.py::test_agentmemory_provider_payload_describes_rest_and_mcp_modes -q
```

预期：FAIL，`agentmemory` 未定义。

- [ ] **步骤 3.2：实现 agentmemory catalog**

加入 provider：

```python
"agentmemory": {
    "label": "agentmemory",
    "storage": "local/server/mcp",
    "dependencies": [
        {"kind": "command", "name": "agentmemory"},
        {"kind": "command", "name": "npx"},
    ],
    "required_fields": [],
    "config_files": [".env", "agentmemory.json"],
    "fields": [
        {
            "name": "AGENTMEMORY_URL",
            "label": "Server URL",
            "storage": "env",
            "secret": False,
            "help": "agentmemory server URL, usually http://localhost:3111.",
        },
        {
            "name": "AGENTMEMORY_SECRET",
            "label": "Secret",
            "storage": "env",
            "secret": True,
            "help": "Optional shared secret for protected agentmemory servers.",
        },
        {
            "name": "AGENTMEMORY_MCP_COMMAND",
            "label": "MCP command",
            "storage": "json",
            "path": "agentmemory.json",
            "secret": False,
            "help": "Default: npx -y @agentmemory/mcp.",
        },
    ],
    "modes": [
        {
            "id": "rest_server",
            "label": "REST server",
            "storage": "local",
            "description": "Local or remote agentmemory server.",
            "fields": ["AGENTMEMORY_URL", "AGENTMEMORY_SECRET"],
            "required_fields": ["AGENTMEMORY_URL"],
            "required_any": [],
            "optional_fields": ["AGENTMEMORY_SECRET"],
        },
        {
            "id": "mcp_server",
            "label": "MCP server",
            "storage": "mcp",
            "description": "MCP shim command used by Hermes.",
            "fields": ["AGENTMEMORY_MCP_COMMAND", "AGENTMEMORY_URL", "AGENTMEMORY_SECRET"],
            "required_fields": ["AGENTMEMORY_MCP_COMMAND"],
            "required_any": [],
            "optional_fields": ["AGENTMEMORY_URL", "AGENTMEMORY_SECRET"],
        },
    ],
    "setup_command": "npm install -g @agentmemory/agentmemory && agentmemory",
    "config_command": "hermes config set memory.provider agentmemory",
    "notes": [
        "Default REST server: http://localhost:3111.",
        "Default MCP command: npx -y @agentmemory/mcp.",
    ],
},
```

Capability：

```python
"agentmemory": {
    "external_read": True,
    "external_read_mode": "provider_summary",
    "direct_hud_config": True,
    "requires_network": False,
    "local_storage": True,
    "supports_tools": True,
    "supports_auto_recall": True,
    "supports_session_ingest": True,
    "supports_manual_write": True,
    "hooks": ["mcp", "rest", "session_start", "pre_compact", "tools"],
},
```

- [ ] **步骤 3.3：实现 agentmemory 只读健康和摘要外部视图**

健康检查：

```python
def agentmemory_health(values: dict[str, dict]) -> list[dict]:
    url = values.get("AGENTMEMORY_URL", {}).get("value") or "http://localhost:3111"
    return [
        check_http_endpoint(f"{url.rstrip('/')}/agentmemory/health"),
        check_http_endpoint(f"{url.rstrip('/')}/health"),
    ]
```

外部视图：

```python
{
    "provider": "agentmemory",
    "available": True,
    "readonly": True,
    "summary": {
        "total": 0,
        "categories": {"server": 1 if health_ok else 0},
    },
    "items": [],
    "reason": "summary_only"
}
```

第一版不直接读取 agentmemory 数据库，避免绑定其内部 schema。

- [ ] **步骤 3.4：运行 agentmemory 测试并提交**

运行：

```bash
.venv/bin/pytest tests/test_memory_api.py::test_agentmemory_provider_payload_describes_rest_and_mcp_modes -q
.venv/bin/pytest tests/test_memory_api.py -q
```

提交：

```bash
git add backend/services/memory_provider_catalog.py backend/services/memory_provider_health.py backend/services/memory_provider_external.py tests/test_memory_api.py
git commit -m "feat: add agentmemory provider metadata"
```

## 阶段 4：接入 MemOS provider

**文件：**
- 修改：`backend/services/memory_provider_catalog.py`
- 修改：`backend/services/memory_provider_health.py`
- 修改：`tests/test_memory_api.py`
- 修改：`frontend/src/i18n/translations.ts`

- [ ] **步骤 4.1：编写 MemOS provider 测试**

在 `tests/test_memory_api.py` 增加：

```python
def test_memos_provider_payload_describes_cloud_and_self_hosted_modes(hermes_home: Path) -> None:
    status = get_memory_providers()
    provider = status["providers"]["memos"]
    modes = {mode["id"]: mode for mode in provider["config_modes"]}
    fields = {field["name"]: field for field in provider["config_fields"]}

    assert provider["label"] == "MemOS"
    assert provider["group"] == "community"
    assert modes["cloud"]["required_fields"] == ["MEMOS_API_KEY"]
    assert modes["self_hosted"]["required_fields"] == ["MEMOS_BASE_URL"]
    assert fields["MEMOS_API_KEY"]["secret"] is True
    assert "MOS_CHAT_MODEL_PROVIDER" in fields
```

运行：

```bash
.venv/bin/pytest tests/test_memory_api.py::test_memos_provider_payload_describes_cloud_and_self_hosted_modes -q
```

预期：FAIL，`memos` 未定义。

- [ ] **步骤 4.2：实现 MemOS catalog**

加入 provider：

```python
"memos": {
    "label": "MemOS",
    "storage": "cloud/self-hosted",
    "dependencies": [{"kind": "python", "name": "memos"}],
    "required_fields": [],
    "config_files": [".env", "memos.json"],
    "fields": [
        {
            "name": "MEMOS_API_KEY",
            "label": "API key",
            "storage": "env",
            "secret": True,
            "help": "MemOS Cloud API key.",
        },
        {
            "name": "MEMOS_BASE_URL",
            "label": "Base URL",
            "storage": "env",
            "secret": False,
            "help": "Self-hosted MemOS API URL.",
        },
        {
            "name": "MOS_CHAT_MODEL_PROVIDER",
            "label": "Model provider",
            "storage": "env",
            "secret": False,
            "help": "openai, azure, qwen, deepseek, minimax, ollama, huggingface, or vllm.",
        },
        {
            "name": "MEMOS_NAMESPACE",
            "label": "Namespace",
            "storage": "json",
            "path": "memos.json",
            "secret": False,
            "help": "Hermes memory namespace or user scope.",
        },
    ],
    "modes": [
        {
            "id": "cloud",
            "label": "Cloud API",
            "storage": "cloud",
            "description": "Hosted MemOS Cloud API.",
            "fields": ["MEMOS_API_KEY", "MEMOS_NAMESPACE"],
            "required_fields": ["MEMOS_API_KEY"],
            "required_any": [],
            "optional_fields": ["MEMOS_NAMESPACE"],
        },
        {
            "id": "self_hosted",
            "label": "Self-hosted",
            "storage": "self-hosted",
            "description": "Private MemOS deployment.",
            "fields": ["MEMOS_BASE_URL", "MOS_CHAT_MODEL_PROVIDER", "MEMOS_NAMESPACE"],
            "required_fields": ["MEMOS_BASE_URL"],
            "required_any": [],
            "optional_fields": ["MOS_CHAT_MODEL_PROVIDER", "MEMOS_NAMESPACE"],
        },
    ],
    "setup_command": "git clone https://github.com/MemTensor/MemOS.git && cd MemOS && pip install -r ./docker/requirements.txt",
    "config_command": "hermes config set memory.provider memos",
    "notes": [
        "Cloud API and self-hosted deployments use different required fields.",
        "Self-hosted MemOS model provider is selected with MOS_CHAT_MODEL_PROVIDER.",
    ],
},
```

Capability：

```python
"memos": {
    "external_read": True,
    "external_read_mode": "provider_summary",
    "direct_hud_config": True,
    "requires_network": True,
    "local_storage": True,
    "supports_tools": True,
    "supports_auto_recall": True,
    "supports_session_ingest": True,
    "supports_manual_write": True,
    "hooks": ["mcp", "api", "session_ingest"],
},
```

- [ ] **步骤 4.3：实现 MemOS 只读探测**

Self-hosted 模式：

```python
def memos_health(values: dict[str, dict]) -> list[dict]:
    base_url = values.get("MEMOS_BASE_URL", {}).get("value") or ""
    checks = []
    if base_url:
        checks.append(check_http_endpoint(f"{base_url.rstrip('/')}/health"))
        checks.append(check_http_endpoint(base_url.rstrip('/')))
    api_key_configured = bool(values.get("MEMOS_API_KEY", {}).get("configured"))
    checks.append({"kind": "secret", "name": "MEMOS_API_KEY", "ok": api_key_configured})
    return checks
```

Cloud 模式第一版只检查 key 是否配置，不发起外部网络请求。

- [ ] **步骤 4.4：运行 MemOS 测试并提交**

运行：

```bash
.venv/bin/pytest tests/test_memory_api.py::test_memos_provider_payload_describes_cloud_and_self_hosted_modes -q
.venv/bin/pytest tests/test_memory_api.py -q
```

提交：

```bash
git add backend/services/memory_provider_catalog.py backend/services/memory_provider_health.py tests/test_memory_api.py
git commit -m "feat: add memos provider metadata"
```

## 阶段 5：前端控制台使用后端分组和增强外部视图

**文件：**
- 修改：`frontend/src/components/MemoryPanel.tsx`
- 修改：`frontend/src/i18n/translations.ts`
- 修改：`tests/test_memory_frontend.py`
- 修改：`backend/static/index.html`
- 添加：新构建产物 `backend/static/assets/*.js` 和 `backend/static/assets/*.css`

- [ ] **步骤 5.1：编写失败测试，禁止前端硬编码社区 provider**

在 `tests/test_memory_frontend.py` 增加或调整：

```python
def test_memory_panel_uses_backend_provider_group_metadata() -> None:
    panel = (ROOT / "frontend/src/components/MemoryPanel.tsx").read_text()

    assert "communityProviderIds" not in panel
    assert "provider.group" in panel
    assert "providerGroups(providers" in panel
```

运行：

```bash
.venv/bin/pytest tests/test_memory_frontend.py::test_memory_panel_uses_backend_provider_group_metadata -q
```

预期：FAIL，当前前端还有 `communityProviderIds`。

- [ ] **步骤 5.2：调整前端类型和分组函数**

在 `MemoryProviderInfo` 中增加：

```ts
group: 'official' | 'community'
```

替换 `providerGroups()`：

```ts
function providerGroups(providers: MemoryProviderInfo[]): Array<{ id: string; labelKey: TranslationKey; providers: MemoryProviderInfo[] }> {
  const groups: Array<{ id: string; labelKey: TranslationKey; providers: MemoryProviderInfo[] }> = [
    {
      id: 'official',
      labelKey: 'memory.officialProviders',
      providers: providers.filter(provider => provider.group !== 'community'),
    },
    {
      id: 'community',
      labelKey: 'memory.communityProviders',
      providers: providers.filter(provider => provider.group === 'community'),
    },
  ]
  return groups.filter(group => group.providers.length)
}
```

- [ ] **步骤 5.3：增强安装指南页签为 mode-aware**

将 `ProviderInstallGuideTab` 的命令构造改为按 mode 展示：

```ts
const modeCommands = provider.config_modes.map(mode => ({
  mode,
  command: provider.setup_command,
  config: provider.config_command,
}))
```

UI 显示：

```tsx
{modeCommands.map(item => (
  <div key={item.mode.id}>
    <div>{item.mode.label}</div>
    <code>{item.command}</code>
    <code>{item.config}</code>
  </div>
))}
```

保留“仅供核对，HUD 不自动执行安装/卸载”的风险提示。

- [ ] **步骤 5.4：增强外部视图支持 summary-only provider**

当前 `ExternalMemoryViewPanel` 已有 `summary` 和 `items`。加入显示规则：

```tsx
const summaryOnly = externalView?.reason === 'summary_only' && !externalView.items?.length
```

当 summary-only 时显示 provider、available、readonly、reason、categories，不显示空白条目列表。

- [ ] **步骤 5.5：运行前端测试和构建**

运行：

```bash
.venv/bin/pytest tests/test_memory_frontend.py -q
npm run build
cp -r frontend/dist/* backend/static/
```

预期：frontend 测试 PASS，Vite build exit 0，静态入口 hash 更新。

- [ ] **步骤 5.6：提交前端控制台增强**

运行：

```bash
git add frontend/src/components/MemoryPanel.tsx frontend/src/i18n/translations.ts tests/test_memory_frontend.py backend/static/index.html
git add -f backend/static/assets/*.js backend/static/assets/*.css
git commit -m "feat: support community memory providers in console"
```

## 阶段 6：全量回归和浏览器验证

**文件：**
- 不新增业务文件。
- 可生成临时 Playwright 截图，但不要提交 `.playwright-cli/`。

- [ ] **步骤 6.1：全量测试**

运行：

```bash
.venv/bin/pytest -q
npm run build
git diff --check
```

预期：

```text
pytest all tests pass
vite build exits 0
git diff --check has no output
```

- [ ] **步骤 6.2：浏览器验证**

在已有 `http://127.0.0.1:3002` 上验证：

1. 打开“记忆”页。
2. 外挂记忆下拉显示官方和社区分组。
3. Cognee、agentmemory、MemOS 均出现在社区分组。
4. 切换每个 provider 后：
   - 概览显示能力摘要。
   - 配置页显示 mode-specific 字段和红色必填星号。
   - 未填必填字段时保存按钮禁用。
   - 诊断页不自动启动外部服务，只显示只读状态。
   - 安装指南只展示命令，不执行命令。

- [ ] **步骤 6.3：清理临时文件**

运行：

```bash
rm -rf .playwright-cli
git status --short
```

预期：没有 `.playwright-cli/`，只剩预期源码/静态资产变更。

- [ ] **步骤 6.4：最终提交**

如果阶段 5 后还有修正：

```bash
git add <changed-files>
git commit -m "test: verify community memory providers"
```

## 安全边界

- HUD 不自动执行 `pip install`、`npm install`、`docker compose up`、`agentmemory connect`、`hermes config set` 之外的外部安装动作。
- HUD 不自动写第三方 agent 配置文件，只写 Hermes 自己的 `config.yaml`、`.env` 和 provider JSON。
- 所有 secret 字段返回前必须脱敏，测试必须断言 secret 不出现在 API payload。
- 外部视图第一版只读；如果 provider 没有稳定公开 API，只显示 summary 和 reason。
- 内置 `MEMORY.md` 和 `USER.md` 始终保留，外部 provider 只影响 `memory.provider`。
- 同一时间仍只启用一个外部 provider。

## 自检

- 规格覆盖：当前计划覆盖当前 UI 收口、provider 元数据拆分、Cognee、agentmemory、MemOS、前端分组、外部视图、健康检查、构建和浏览器验证。
- 占位符扫描：无“待定”“TODO”“后续实现”占位表达；每个阶段都有明确文件、测试和命令。
- 类型一致性：后端 provider 字段使用 `group`，前端 `MemoryProviderInfo.group` 同名消费；配置模式继续沿用现有 `config_modes` / `mode_ids` / `required_fields` 结构。
