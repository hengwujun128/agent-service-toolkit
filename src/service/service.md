# Service 模块文档

本文件是 `service.py` 的辅助文档，帮助理解 FastAPI 服务层的设计与实现。

## 模块职责

`service.py` 是整个项目的 **HTTP 服务入口**，负责：

1. **暴露 API 端点**：把 LangGraph Agent 包装成 `/invoke`、`/stream` 等 HTTP 接口
2. **生命周期管理**：启动时初始化数据库（Checkpointer/Store）、加载 Agent
3. **统一鉴权**：通过 Bearer Token 验证请求
4. **消息转换**：LangChain 消息格式 ↔ API 的 ChatMessage 格式
5. **流式输出**：SSE（Server-Sent Events）实现逐 token 返回

---

## 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              HTTP 请求                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           FastAPI App (service.py)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │  /info      │  │  /invoke    │  │  /stream    │  │  /health    │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                │                │                                 │
│         │                ▼                ▼                                 │
│         │         ┌─────────────────────────────┐                          │
│         │         │     _handle_input()         │                          │
│         │         │  - 组装 config              │                          │
│         │         │  - 检查 interrupt           │                          │
│         │         └─────────────────────────────┘                          │
│         │                │                │                                 │
│         │                ▼                ▼                                 │
│         │         ┌───────────┐    ┌───────────────────┐                   │
│         │         │  ainvoke  │    │ message_generator │                   │
│         │         │  (同步)   │    │    (SSE 流式)     │                   │
│         │         └───────────┘    └───────────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           LangGraph Agent                                    │
│                    (agents/__init__.py 注册的 Agent)                         │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                          ┌─────────┴─────────┐
                          ▼                   ▼
                   ┌───────────┐       ┌───────────┐
                   │Checkpointer│      │   Store   │
                   │ (短期记忆) │      │ (长期记忆) │
                   └───────────┘       └───────────┘
```

---

## 端点一览

| 端点 | 方法 | 功能 | 请求体 | 响应 |
|------|------|------|--------|------|
| `/info` | GET | 获取服务元数据 | - | ServiceMetadata |
| `/invoke` | POST | 同步调用 Agent | UserInput | ChatMessage |
| `/{agent_id}/invoke` | POST | 指定 Agent 同步调用 | UserInput | ChatMessage |
| `/stream` | POST | 流式调用 Agent | StreamInput | SSE 流 |
| `/{agent_id}/stream` | POST | 指定 Agent 流式调用 | StreamInput | SSE 流 |
| `/history` | POST | 获取对话历史 | ChatHistoryInput | ChatHistory |
| `/feedback` | POST | 提交用户反馈 | Feedback | FeedbackResponse |
| `/health` | GET | 健康检查 | - | `{"status": "ok"}` |

---

## 核心组件详解

### 1. 生命周期管理（lifespan）

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    ...
```

**执行时机**：FastAPI 应用启动时

**做的事情**：
1. 初始化 Checkpointer（短期记忆，按 thread_id 存对话）
2. 初始化 Store（长期记忆，按 user_id 存跨会话信息）
3. 加载所有注册的 Agent
4. 把 checkpointer/store 挂到每个 Agent 上

**数据流**：
```
服务启动
    ↓
initialize_database() → Checkpointer（SQLite/Postgres）
initialize_store() → Store（InMemory/Postgres）
    ↓
遍历所有 Agent
    ↓
agent.checkpointer = saver
agent.store = store
    ↓
服务就绪，开始接收请求
```

---

### 2. 鉴权（verify_bearer）

```python
def verify_bearer(http_auth: ...) -> None:
    if not settings.AUTH_SECRET:
        return  # 未配置则跳过
    if not http_auth or http_auth.credentials != auth_secret:
        raise HTTPException(status_code=401)
```

**工作方式**：
- 如果 `.env` 中配置了 `AUTH_SECRET`，所有请求必须带 `Authorization: Bearer <token>`
- 未配置则不启用鉴权

**使用示例**：
```bash
# .env 中配置 AUTH_SECRET=my-secret-key
curl -H "Authorization: Bearer my-secret-key" http://localhost:8080/info
```

---

### 3. 输入处理（_handle_input）

```python
async def _handle_input(user_input: UserInput, agent: AgentGraph) -> tuple[dict, UUID]:
    ...
```

**职责**：把用户请求转换成 LangGraph 需要的格式

**处理逻辑**：

```
UserInput
    ↓
生成 run_id（UUID v7，LangSmith 要求）
    ↓
确定 thread_id / user_id（没传就自动生成）
    ↓
组装 configurable = {thread_id, user_id, model, ...}
    ↓
检查是否有未完成的 interrupt
    ↓
┌─────────────────────────────────────┐
│ 有 interrupt？                      │
│   ├─ 是 → input = Command(resume=) │
│   └─ 否 → input = {messages: [...]}│
└─────────────────────────────────────┘
    ↓
返回 kwargs（给 agent.ainvoke/astream 用）
```

**关键点**：
- `thread_id`：同一个值 = 同一个对话，消息会累积
- `user_id`：跨对话的用户标识，用于长期记忆
- `interrupt`：Agent 可以暂停等用户输入，下次请求自动恢复

---

### 4. 同步调用（invoke）

```python
@router.post("/invoke")
async def invoke(user_input: UserInput, agent_id: str = DEFAULT_AGENT) -> ChatMessage:
    ...
```

**数据流**：
```
POST /invoke {message: "你好", thread_id: "xxx"}
    ↓
_handle_input() 组装 kwargs
    ↓
agent.ainvoke(**kwargs, stream_mode=["updates", "values"])
    ↓
等待 Agent 执行完成（可能调 LLM、调工具）
    ↓
取最后一条消息，转成 ChatMessage
    ↓
返回给客户端
```

**使用示例**：
```bash
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{"message": "今天天气怎么样？", "thread_id": "conv-123"}'
```

---

### 5. 流式调用（stream + message_generator）

```python
@router.post("/stream")
async def stream(user_input: StreamInput, agent_id: str = DEFAULT_AGENT) -> StreamingResponse:
    return StreamingResponse(
        message_generator(user_input, agent_id),
        media_type="text/event-stream",
    )
```

**数据流**：
```
POST /stream {message: "讲个笑话", stream_tokens: true}
    ↓
message_generator() 异步生成器
    ↓
agent.astream(**kwargs, stream_mode=["updates", "messages", "custom"])
    ↓
┌─────────────────────────────────────────────┐
│ 订阅三种事件：                               │
│ - updates: 节点完成时的完整消息              │
│ - messages: LLM 输出的每个 token            │
│ - custom: 自定义事件（如后台任务状态）       │
└─────────────────────────────────────────────┘
    ↓
每收到一个事件，转成 SSE 格式 yield
    ↓
客户端收到：
  data: {"type": "message", "content": {...}}
  data: {"type": "token", "content": "从前"}
  data: {"type": "token", "content": "有座山"}
  data: [DONE]
```

**SSE 事件类型**：

| type | 含义 | 内容 |
|------|------|------|
| message | 完整消息 | ChatMessage 对象 |
| token | LLM 输出的 token | 字符串 |
| error | 错误 | 错误信息 |
| [DONE] | 结束标记 | - |

---

### 6. 对话历史（history）

```python
@router.post("/history")
async def history(input: ChatHistoryInput) -> ChatHistory:
    ...
```

**数据流**：
```
POST /history {thread_id: "conv-123"}
    ↓
agent.aget_state(config={thread_id: ...})
    ↓
从 Checkpointer 读取该线程的所有消息
    ↓
转成 ChatMessage 列表返回
```

---

### 7. 用户反馈（feedback）

```python
@router.post("/feedback")
async def feedback(feedback: Feedback) -> FeedbackResponse:
    ...
```

**数据流**：
```
POST /feedback {run_id: "xxx", key: "human-feedback-stars", score: 0.8}
    ↓
LangsmithClient().create_feedback(...)
    ↓
反馈记录到 LangSmith（用于模型评估、追踪）
```

**注意**：需要配置 `LANGCHAIN_API_KEY` 才能使用

---

## 关键设计决策

### 1. 为什么用 stream_mode=["updates", "values"]？

`invoke` 需要同时获取：
- **updates**：中间状态更新（如 interrupt）
- **values**：最终结果

这样才能正确处理 Agent 被中断的情况。

### 2. 为什么 stream 用三种 stream_mode？

```python
stream_mode=["updates", "messages", "custom"]
```

- **updates**：节点完成时的完整消息（工具调用结果等）
- **messages**：LLM 逐 token 输出（打字机效果）
- **custom**：自定义事件（后台任务状态等）

### 3. subgraphs=True 是什么？

```python
agent.astream(..., subgraphs=True)
```

支持多 Agent 协作（如 supervisor-agent）时，事件会带上来源子图的路径。
代码中需要兼容两种事件结构：
- 普通：`(stream_mode, event)`
- 子图：`(node_path, stream_mode, event)`

### 4. 为什么要过滤 HumanMessage？

```python
if chat_message.type == "human" and chat_message.content == user_input.message:
    continue
```

LangGraph 会把用户输入也作为事件发出，但前端已经显示过了，不需要重复。

---

## 错误处理

### 403 地区限制

```python
if "403" in err_str and "unsupported_country_region_territory" in err_str:
    raise HTTPException(status_code=403, detail="LLM API 不支持当前地区...")
```

OpenAI 等厂商对部分地区限制访问，服务层捕获并返回明确提示。

### 通用错误

其他异常统一返回 500，避免泄露内部信息。

---

## 相关文件

| 文件 | 作用 |
|------|------|
| `service/__init__.py` | 导出 app |
| `service/utils.py` | 消息转换工具（LangChain ↔ ChatMessage） |
| `schema/schema.py` | 请求/响应数据结构 |
| `agents/__init__.py` | Agent 注册与获取 |
| `memory/` | Checkpointer 和 Store 初始化 |
| `core/settings.py` | 配置管理 |

---

## 调试技巧

### 1. 查看完整请求日志

```bash
# .env 中设置
LOG_LEVEL=DEBUG
```

### 2. 测试 SSE 流

```bash
curl -N -X POST http://localhost:8080/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "stream_tokens": true}'
```

`-N` 禁用缓冲，实时看到流式输出。

### 3. 查看 OpenAPI 文档

浏览器访问 `http://localhost:8080/docs`，自动生成的交互式 API 文档。
