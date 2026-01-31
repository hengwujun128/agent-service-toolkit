# Schema 模块文档

本文件是 `schema.py` 的辅助文档，帮助理解 API 数据结构的设计与用法。

## 整体数据流图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              客户端 (Streamlit / curl)                       │
└─────────────────────────────────────────────────────────────────────────────┘
        │                           │                           │
        │ GET /info                 │ POST /invoke              │ POST /stream
        │                           │ POST /history             │ POST /feedback
        ▼                           ▼                           ▼
┌───────────────┐           ┌───────────────┐           ┌───────────────┐
│ ServiceMetadata│          │   UserInput   │           │  StreamInput  │
│   (响应)       │          │   (请求体)     │           │   (请求体)    │
└───────────────┘           └───────────────┘           └───────────────┘
                                    │                           │
                                    ▼                           ▼
                            ┌───────────────┐           ┌───────────────┐
                            │  ChatMessage  │           │ SSE 事件流     │
                            │   (响应)      │           │ (ChatMessage)  │
                            └───────────────┘           └───────────────┘
```

## 端点与 Schema 对应关系

| 端点              | 请求 Schema        | 响应 Schema         | 说明                    |
|-------------------|--------------------|--------------------|------------------------|
| GET  /info        | -                  | ServiceMetadata    | 获取可用 Agent/模型列表   |
| POST /invoke      | UserInput          | ChatMessage        | 同步调用，等待完整响应     |
| POST /stream      | StreamInput        | SSE(ChatMessage)   | 流式调用，逐 token 返回   |
| POST /history     | ChatHistoryInput   | ChatHistory        | 获取对话历史             |
| POST /feedback    | Feedback           | FeedbackResponse   | 提交用户反馈到 LangSmith  |
| GET  /health      | -                  | dict               | 健康检查                 |

## 各 Schema 详解

### ServiceMetadata

**用途**：服务元数据，由 `GET /info` 返回。客户端用它初始化界面。

**数据流**：
```
客户端启动
    ↓
GET /info
    ↓
ServiceMetadata（包含可用 agents、models、默认值）
    ↓
Streamlit 用这些数据渲染下拉菜单
```

**使用示例**：
```bash
curl http://localhost:8080/info
```

**响应示例**：
```json
{
  "agents": [
    {"key": "research-assistant", "description": "A research assistant..."}
  ],
  "models": ["deepseek-chat", "openai-compatible"],
  "default_agent": "research-assistant",
  "default_model": "deepseek-chat"
}
```

---

### UserInput

**用途**：用户输入，`POST /invoke` 的请求体。

**数据流**：
```
客户端发送 UserInput
    ↓
service.py 解析并校验
    ↓
_handle_input() 组装 LangGraph config
    ↓
agent.ainvoke() 调用 Agent
    ↓
返回 ChatMessage
```

**使用示例**：
```bash
curl -X POST http://localhost:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "message": "今天天气怎么样？",
    "model": "deepseek-chat",
    "thread_id": "conv-123",
    "user_id": "user-456"
  }'
```

**字段说明**：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| message | string | ✅ | 用户消息内容 |
| model | string | ❌ | LLM 模型，不传用默认 |
| thread_id | string | ❌ | 线程 ID，用于多轮对话 |
| user_id | string | ❌ | 用户 ID，用于跨线程记忆 |
| agent_config | object | ❌ | 传给 Agent 的额外配置 |

---

### StreamInput

**用途**：流式请求输入，`POST /stream` 的请求体。继承 UserInput。

**数据流**：
```
客户端发送 StreamInput
    ↓
service.py message_generator() 生成 SSE 事件流
    ↓
逐个 yield ChatMessage（type: message）和 token（type: token）
    ↓
客户端实时渲染
```

**使用示例**：
```bash
curl -X POST http://localhost:8080/stream \
  -H "Content-Type: application/json" \
  -d '{"message": "讲个笑话", "stream_tokens": true}'
```

**SSE 响应示例**：
```
data: {"type": "message", "content": {...}}
data: {"type": "token", "content": "从前"}
data: {"type": "token", "content": "有座山"}
data: [DONE]
```

---

### ChatMessage

**用途**：聊天消息，是服务返回给客户端的核心数据结构。

**消息类型（type）**：

| type | 含义 | 场景 |
|------|------|------|
| human | 用户消息 | 用户输入 |
| ai | AI 响应 | 回答或请求工具调用 |
| tool | 工具结果 | 工具执行后的返回 |
| custom | 自定义 | 后台任务状态等 |

**数据流（invoke）**：
```
Agent 执行完成
    ↓
service/utils.py langchain_to_chat_message() 转换
    ↓
返回 ChatMessage 给客户端
```

**数据流（stream）**：
```
Agent 执行中
    ↓
每产生一条消息就转成 ChatMessage
    ↓
通过 SSE 推送给客户端
```

**示例 - AI 普通响应**：
```json
{
  "type": "ai",
  "content": "东京今天晴天，气温 25°C。",
  "tool_calls": [],
  "run_id": "xxx-xxx"
}
```

**示例 - AI 请求工具调用**：
```json
{
  "type": "ai",
  "content": "",
  "tool_calls": [
    {"name": "Weather", "args": {"city": "Tokyo"}, "id": "call_123"}
  ]
}
```

**示例 - 工具执行结果**：
```json
{
  "type": "tool",
  "content": "Sunny, 25°C",
  "tool_call_id": "call_123"
}
```

---

### ToolCall

**用途**：工具调用信息，嵌在 `ChatMessage.tool_calls` 里。

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 工具名称（如 "Weather"） |
| args | object | 工具参数（如 `{"city": "Tokyo"}`） |
| id | string | 调用 ID，用于匹配后续 ToolMessage |

---

### Feedback

**用途**：用户反馈，`POST /feedback` 的请求体。

**数据流**：
```
用户在 Streamlit 点击星级评分
    ↓
客户端发送 Feedback（包含 run_id 和 score）
    ↓
service.py 调用 LangSmith API 记录
    ↓
返回 FeedbackResponse
```

**使用示例**：
```bash
curl -X POST http://localhost:8080/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "xxx-xxx-xxx",
    "key": "human-feedback-stars",
    "score": 0.8
  }'
```

---

### ChatHistoryInput / ChatHistory

**用途**：查询对话历史。

**数据流**：
```
客户端发送 ChatHistoryInput（指定 thread_id）
    ↓
service.py 从 checkpointer 读取该线程的消息
    ↓
返回 ChatHistory（包含所有 ChatMessage）
```

**使用示例**：
```bash
curl -X POST http://localhost:8080/history \
  -H "Content-Type: application/json" \
  -d '{"thread_id": "conv-123"}'
```

## 相关代码文件

- **Schema 定义**：`src/schema/schema.py`（本文件对应的代码）
- **模型枚举**：`src/schema/models.py`
- **服务层**：`src/service/service.py`（使用这些 Schema）
- **转换工具**：`src/service/utils.py`（LangChain 消息 ↔ ChatMessage）
- **客户端**：`src/client/client.py`（使用这些 Schema 做序列化/反序列化）
