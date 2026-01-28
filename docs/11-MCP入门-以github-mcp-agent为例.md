# 11 - MCP 入门：以 github-mcp-agent 为例

## 📚 学习目标

读完本文档后，你将能够：
- ✅ 理解 MCP（Model Context Protocol）是什么
- ✅ 理解 MCP 与传统 Tool 的区别
- ✅ 分析 GitHub MCP Agent 的实现
- ✅ 学会如何集成其他 MCP 服务器

## 🎯 5 分钟验证

完成以下步骤后，你应该能：
1. 配置 GitHub PAT 并启动 GitHub MCP Agent
2. 使用 Agent 查询 GitHub 仓库信息
3. 理解 MCP 工具的动态加载机制

## 📖 MCP 核心概念

### 什么是 MCP？

**MCP = Model Context Protocol（模型上下文协议）**

MCP 是 Anthropic 提出的一个开放标准，用于连接 AI 模型与外部数据源和工具。

**类比理解**：

| 概念 | 传统 Tool | MCP |
|------|----------|-----|
| 前端类比 | 内嵌的 API 调用 | 微服务/插件系统 |
| 工具定义 | 代码中硬编码 | 外部服务器动态提供 |
| 部署方式 | 与 Agent 一起部署 | 独立部署，按需连接 |
| 扩展性 | 修改代码 | 添加新服务器 |

### MCP 架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                           MCP 架构                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────┐         ┌─────────────┐         ┌─────────────┐   │
│  │  AI Agent   │ ◄─────► │ MCP Client  │ ◄─────► │ MCP Server  │   │
│  │  (LLM)      │         │ (适配器)     │   HTTP  │ (工具提供者) │   │
│  └─────────────┘         └─────────────┘         └─────────────┘   │
│                                                         │           │
│                                                         │           │
│                                                         ▼           │
│                                               ┌─────────────────┐   │
│                                               │   外部服务       │   │
│                                               │ (GitHub API)    │   │
│                                               │ (文件系统)       │   │
│                                               │ (数据库)         │   │
│                                               └─────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### MCP vs 传统 Tool

```python
# ========== 传统 Tool ==========
# 工具定义在代码中，与 Agent 紧耦合

@tool
def search_github(query: str) -> str:
    """搜索 GitHub"""
    # 硬编码的 API 调用
    response = requests.get(f"https://api.github.com/search?q={query}")
    return response.json()

tools = [search_github]  # 静态工具列表


# ========== MCP Tool ==========
# 工具由外部 MCP 服务器提供，动态加载

mcp_client = MultiServerMCPClient(connections={
    "github": StreamableHttpConnection(url="https://mcp.github.com/...")
})

# 动态获取工具（可能有 20+ 个工具）
tools = await mcp_client.get_tools()  # 运行时从服务器获取
```

**优势对比**：

| 方面 | 传统 Tool | MCP |
|------|----------|-----|
| 工具数量 | 手动定义每个工具 | 服务器提供完整工具集 |
| 维护成本 | API 变化需改代码 | 服务器负责维护 |
| 认证管理 | 每个工具单独处理 | 统一在 MCP 连接层 |
| 复用性 | 每个项目重写 | 跨项目共享 MCP 服务器 |

## 🔧 GitHub MCP Agent 代码分析

### 文件结构

```
src/agents/github_mcp_agent/
└── github_mcp_agent.py    # 主文件
```

### 核心代码解读

#### 1. 导入和依赖

```python
# src/agents/github_mcp_agent/github_mcp_agent.py

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection
from agents.lazy_agent import LazyLoadingAgent
```

- `MultiServerMCPClient`：MCP 客户端，可连接多个 MCP 服务器
- `StreamableHttpConnection`：HTTP 传输层
- `LazyLoadingAgent`：懒加载 Agent 基类（因为 MCP 需要异步初始化）

#### 2. LazyLoadingAgent 模式

为什么使用懒加载？

```python
class GitHubMCPAgent(LazyLoadingAgent):
    """GitHub MCP Agent with async initialization."""

    def __init__(self) -> None:
        super().__init__()
        self._mcp_tools: list[BaseTool] = []
        self._mcp_client: MultiServerMCPClient | None = None

    async def load(self) -> None:
        """Initialize the GitHub MCP agent by loading MCP tools."""
        # MCP 工具需要异步加载
        # 如果在 __init__ 中同步初始化会阻塞服务启动
        ...
```

**原因**：
- MCP 工具列表需要从远程服务器获取
- HTTP 请求是异步操作
- 服务启动时不能阻塞等待外部服务

#### 3. MCP 连接配置

```python
async def load(self) -> None:
    # 检查 GitHub PAT 是否配置
    if not settings.GITHUB_PAT:
        logger.info("GITHUB_PAT is not set, GitHub MCP agent will have no tools")
        self._mcp_tools = []
        self._graph = self._create_graph()
        self._loaded = True
        return

    # 配置 MCP 连接
    github_pat = settings.GITHUB_PAT.get_secret_value()
    connections = {
        "github": StreamableHttpConnection(
            transport="streamable_http",
            url=settings.MCP_GITHUB_SERVER_URL,  # 默认: https://api.githubcopilot.com/mcp/
            headers={
                "Authorization": f"Bearer {github_pat}",  # 认证
            },
        )
    }

    # 创建 MCP 客户端
    self._mcp_client = MultiServerMCPClient(connections)
    
    # 获取工具列表
    self._mcp_tools = await self._mcp_client.get_tools()
    logger.info(f"GitHub MCP agent initialized with {len(self._mcp_tools)} tools")
```

#### 4. 创建 Agent 图

```python
def _create_graph(self) -> CompiledStateGraph:
    """Create the GitHub MCP agent graph."""
    model = get_model(settings.DEFAULT_MODEL)

    return create_agent(
        model=model,
        tools=self._mcp_tools,  # 使用 MCP 工具
        name="github-mcp-agent",
        system_prompt=prompt,
    )
```

使用 `langchain.agents.create_agent` 创建标准的 ReAct Agent。

### System Prompt 设计

```python
prompt = f"""
You are GitHubBot, a specialized assistant for GitHub repository management...

Your capabilities include:
- Repository management (create, clone, browse)
- Issue management (create, list, update, close)
- Pull request management (create, review, merge)
...

Guidelines:
- Be cautious with destructive operations (deletes, force pushes, etc.)
- Provide context about what you're doing and why
...

NOTE: You have access to GitHub MCP tools that provide direct GitHub API access.
"""
```

**设计要点**：
- 明确角色（GitHubBot）
- 列出能力范围
- 设定安全规则（避免破坏性操作）
- 提醒 LLM 有 MCP 工具可用

## 🚀 配置和使用

### 步骤 1：获取 GitHub PAT

1. 访问 GitHub Settings → Developer settings → Personal access tokens
2. 创建新的 Classic Token
3. 选择权限：
   - `repo`：仓库完整访问
   - `read:org`：读取组织信息
   - `read:user`：读取用户信息

### 步骤 2：配置环境变量

```bash
# .env
GITHUB_PAT=ghp_xxxxxxxxxxxxxxxxxxxx

# 可选：自定义 MCP 服务器 URL
# MCP_GITHUB_SERVER_URL=https://api.githubcopilot.com/mcp/
```

### 步骤 3：测试 Agent

```bash
# 启动服务
python src/run_service.py

# 测试 GitHub MCP Agent
curl -X POST http://0.0.0.0:8080/github-mcp-agent/invoke \
  -H "Content-Type: application/json" \
  -d '{"message": "Describe the JoshuaC215/agent-service-toolkit repository"}'
```

### 示例对话

```
用户: "列出 langchain-ai/langchain 仓库的最近 5 个 issue"

Agent: [调用 MCP 工具: list_issues]

Agent 回复:
以下是 langchain-ai/langchain 仓库的最近 5 个 issue:

1. #12345 - [Bug] Memory leak in streaming mode
   状态: Open | 创建者: user1 | 时间: 2024-01-15

2. #12344 - [Feature] Add support for new model
   状态: Open | 创建者: user2 | 时间: 2024-01-14
   
...
```

## 📊 MCP 工具列表

GitHub MCP Server 提供的部分工具：

| 工具名称 | 功能 | 示例用法 |
|---------|------|---------|
| `get_repo` | 获取仓库信息 | "描述 xxx 仓库" |
| `list_commits` | 列出提交历史 | "最近的提交记录" |
| `get_file_contents` | 读取文件内容 | "显示 README.md" |
| `list_issues` | 列出 issues | "有哪些 open issues" |
| `create_issue` | 创建 issue | "创建一个 bug report" |
| `create_pull_request` | 创建 PR | "从 dev 分支创建 PR" |
| `search_code` | 搜索代码 | "搜索 async 函数" |

## 🔧 创建自己的 MCP Agent

### 模板代码

```python
# src/agents/my_mcp_agent/my_mcp_agent.py

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.sessions import StreamableHttpConnection

from agents.lazy_agent import LazyLoadingAgent
from core import get_model, settings


prompt = """
You are MyMCPBot, a specialized assistant with MCP tools.
...
"""


class MyMCPAgent(LazyLoadingAgent):
    """Custom MCP Agent template."""

    def __init__(self) -> None:
        super().__init__()
        self._mcp_tools = []
        self._mcp_client = None

    async def load(self) -> None:
        """Initialize MCP tools."""
        try:
            connections = {
                "my_server": StreamableHttpConnection(
                    transport="streamable_http",
                    url="https://my-mcp-server.com/mcp/",
                    headers={"Authorization": f"Bearer {settings.MY_API_KEY}"},
                )
            }
            
            self._mcp_client = MultiServerMCPClient(connections)
            self._mcp_tools = await self._mcp_client.get_tools()
            
        except Exception as e:
            logger.error(f"Failed to initialize MCP agent: {e}")
            self._mcp_tools = []

        self._graph = self._create_graph()
        self._loaded = True

    def _create_graph(self):
        """Create agent graph."""
        model = get_model(settings.DEFAULT_MODEL)
        return create_agent(
            model=model,
            tools=self._mcp_tools,
            name="my-mcp-agent",
            system_prompt=prompt,
        )


# Export agent instance
my_mcp_agent = MyMCPAgent()
```

### 注册 Agent

```python
# src/agents/agents.py

from agents.my_mcp_agent.my_mcp_agent import my_mcp_agent

agents: dict[str, Agent] = {
    # ...
    "my-mcp-agent": Agent(
        description="My custom MCP agent.",
        graph_like=my_mcp_agent
    ),
}
```

## ⚠️ 常见问题

### Q1: MCP 工具加载失败

**症状**：Agent 没有任何工具

**检查**：
1. 环境变量是否正确（如 `GITHUB_PAT`）
2. MCP 服务器 URL 是否可访问
3. 认证 Token 是否有效

**调试**：
```python
# 添加详细日志
logger.info(f"Loaded {len(self._mcp_tools)} MCP tools")
for tool in self._mcp_tools:
    logger.debug(f"Tool: {tool.name} - {tool.description}")
```

### Q2: 权限不足

**症状**：某些操作返回 403 错误

**解决**：检查 GitHub PAT 的 scope 权限，确保包含所需权限。

### Q3: 网络超时

**症状**：MCP 连接超时

**解决**：
```python
connections = {
    "github": StreamableHttpConnection(
        url=settings.MCP_GITHUB_SERVER_URL,
        timeout=30,  # 增加超时时间
        ...
    )
}
```

## 📝 下一步

- **文档 12**：学习多 Agent 协作（Supervisor 模式）
- 探索其他 MCP 服务器（文件系统、数据库等）
- 学习如何创建自己的 MCP 服务器

## 🔗 相关代码文件

- GitHub MCP Agent：[`src/agents/github_mcp_agent/github_mcp_agent.py`](../src/agents/github_mcp_agent/github_mcp_agent.py)
- 懒加载 Agent 基类：[`src/agents/lazy_agent.py`](../src/agents/lazy_agent.py)
- 官方配置文档：[`docs/GitHub_MCP_Agent.md`](GitHub_MCP_Agent.md)

## 🔗 外部资源

- [MCP 官方文档](https://modelcontextprotocol.io/)
- [GitHub MCP Server](https://github.com/github/github-mcp-server)
- [LangChain MCP Adapters](https://github.com/langchain-ai/langchain-mcp-adapters)
- [MCP 服务器列表](https://github.com/modelcontextprotocol/servers)
