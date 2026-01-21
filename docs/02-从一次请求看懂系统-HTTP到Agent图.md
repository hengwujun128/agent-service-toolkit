# 02 - 从一次请求看懂系统：HTTP 到 Agent 图

## 📚 学习目标

读完本文档后，你将能够：
- ✅ 理解一次 HTTP 请求如何从 FastAPI 传递到 LangGraph Agent
- ✅ 看懂请求体字段（`message`、`thread_id`、`user_id`、`model`、`agent_config`）
- ✅ 理解响应结构（message vs token vs DONE）
- ✅ 定位代码中的关键处理逻辑
- ✅ 理解 interrupt resume 机制

## 🎯 5 分钟验证

完成以下步骤后，你应该能：
1. 用 curl 发送一次 `/invoke` 请求并理解响应
2. 用 curl 发送一次 `/stream` 请求并看懂 SSE 流
3. 在代码中找到请求处理的入口函数

## 📖 请求流程概览

```
用户输入
   ↓
Streamlit UI (src/streamlit_app.py)
   ↓ HTTP POST
FastAPI Service (src/service/service.py)
   ↓ 解析请求 → 构建 RunnableConfig
LangGraph Agent (src/agents/*.py)
   ↓ 执行图 → 调用 LLM/Tools
返回响应
   ↓
Streamlit UI 显示
```

## 🔍 深入理解 `/invoke` 端点

### 请求示例

```bash
curl -X POST http://0.0.0.0:8080/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is 2+2?",
    "thread_id": "optional-thread-id",
    "user_id": "optional-user-id",
    "model": "gpt-5-nano",
    "agent_config": {}
  }'
```

### 请求体字段详解

根据 [`src/schema/schema.py`](src/schema/schema.py) 中的 `UserInput` 模型：

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `message` | `str` | ✅ | 用户输入的消息内容 |
| `thread_id` | `str \| None` | ❌ | 线程 ID，用于**多轮对话记忆**。相同 `thread_id` 的请求会共享对话历史 |
| `user_id` | `str \| None` | ❌ | 用户 ID，用于**跨线程的用户记忆**（长期记忆） |
| `model` | `AllModelEnum \| None` | ❌ | 指定使用的 LLM 模型。如果不提供，使用默认模型 |
| `agent_config` | `dict[str, Any]` | ❌ | 传递给 Agent 的额外配置。**注意**：不能包含保留字段（`thread_id`、`user_id`、`model`） |

**前端类比**：
- `thread_id` ≈ React 的 `useState` 作用域（单次会话）
- `user_id` ≈ 全局 Context（跨会话）
- `agent_config` ≈ props（传递给组件的额外参数）

### 代码追踪：请求处理流程

#### 1. FastAPI 路由入口

**文件**：[`src/service/service.py`](src/service/service.py)

```python
@router.post("/{agent_id}/invoke", operation_id="invoke_with_agent_id")
@router.post("/invoke")
async def invoke(user_input: UserInput, agent_id: str = DEFAULT_AGENT) -> ChatMessage:
    agent: AgentGraph = get_agent(agent_id)
    kwargs, run_id = await _handle_input(user_input, agent)
    # ... 调用 agent.ainvoke()
```

**关键点**：
- 如果没有提供 `agent_id`，使用默认 agent（`research-assistant`）
- 调用 `_handle_input()` 处理输入并构建调用参数

#### 2. 输入处理：`_handle_input()`

**文件**：[`src/service/service.py`](src/service/service.py)，第 118-172 行

```python
async def _handle_input(user_input: UserInput, agent: AgentGraph) -> tuple[dict[str, Any], UUID]:
    run_id = uuid4()
    thread_id = user_input.thread_id or str(uuid4())
    user_id = user_input.user_id or str(uuid4())
    
    configurable = {"thread_id": thread_id, "user_id": user_id}
    if user_input.model is not None:
        configurable["model"] = user_input.model
    
    # ... 检查 interrupt resume
    # ... 构建 config 和 input
```

**关键逻辑**：

1. **生成 run_id**：每次请求都有唯一的 `run_id`（用于追踪和反馈）
2. **处理 thread_id/user_id**：如果未提供，自动生成 UUID
3. **检查 interrupt resume**：
   ```python
   state = await agent.aget_state(config=config)
   interrupted_tasks = [task for task in state.tasks if hasattr(task, "interrupts") and task.interrupts]
   
   if interrupted_tasks:
       # 用户输入是 resume 响应
       input = Command(resume=user_input.message)
   else:
       # 正常的新消息
       input = {"messages": [HumanMessage(content=user_input.message)]}
   ```
   **这是什么？**：如果 Agent 之前被中断（需要用户输入），下一次请求会被视为"恢复"而不是新消息。

4. **构建 RunnableConfig**：
   ```python
   config = RunnableConfig(
       configurable=configurable,  # thread_id, user_id, model, agent_config
       run_id=run_id,
       callbacks=callbacks,  # Langfuse/LangSmith 追踪
   )
   ```

**⚠️ 易错点 1：`agent_config` 保留字段冲突**

代码中有检查：
```python
reserved_keys = {"thread_id", "user_id", "model"}
if overlap := reserved_keys & user_input.agent_config.keys():
    raise HTTPException(status_code=422, detail=f"agent_config contains reserved keys: {overlap}")
```

**为什么？**：`agent_config` 会被合并到 `configurable`，但 `thread_id`/`user_id`/`model` 已经在顶层设置了，避免冲突。

#### 3. Agent 调用：`agent.ainvoke()`

**文件**：[`src/service/service.py`](src/service/service.py)，第 195 行

```python
response_events: list[tuple[str, Any]] = await agent.ainvoke(
    **kwargs, 
    stream_mode=["updates", "values"]
)
```

**关键点**：
- `stream_mode=["updates", "values"]`：同时获取更新流和最终值
- `agent` 是 LangGraph 编译后的图（`CompiledStateGraph` 或 `Pregel`）

#### 4. 响应处理

**文件**：[`src/service/service.py`](src/service/service.py)，第 196-210 行

```python
response_type, response = response_events[-1]
if response_type == "values":
    # 正常完成
    output = langchain_to_chat_message(response["messages"][-1])
elif response_type == "updates" and "__interrupt__" in response:
    # 被中断（需要用户输入）
    output = langchain_to_chat_message(
        AIMessage(content=response["__interrupt__"][0].value)
    )
```

**响应类型**：
- `"values"`：Agent 正常完成，返回最终消息
- `"updates"` + `"__interrupt__"`：Agent 被中断，返回中断值（通常是提示用户输入）

**最终返回**：`ChatMessage` 对象（包含 `type`、`content`、`run_id` 等）

## 🔍 深入理解 `/stream` 端点

### 请求示例

```bash
curl -X POST http://0.0.0.0:8080/stream \
  -H "Content-Type: application/json" \
  -d '{
    "message": "What is 2+2?",
    "stream_tokens": true
  }'
```

### 请求体字段

`StreamInput` 继承自 `UserInput`，额外字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `stream_tokens` | `bool` | `true` | 是否流式返回 token（逐字显示） |

### SSE 响应格式

Server-Sent Events (SSE) 格式：

```
data: {"type": "message", "content": {...}}\n\n
data: {"type": "token", "content": "Hello"}\n\n
data: {"type": "token", "content": " world"}\n\n
data: {"type": "message", "content": {...}}\n\n
data: [DONE]\n\n
```

**事件类型**：
- `"message"`：完整的消息对象（AI 响应、工具调用结果等）
- `"token"`：LLM 生成的单个 token（仅当 `stream_tokens=true`）
- `"error"`：错误信息
- `"[DONE]"`：流结束标记

### 代码追踪：流式处理

#### 1. 路由入口

**文件**：[`src/service/service.py`](src/service/service.py)，第 356-371 行

```python
@router.post("/{agent_id}/stream", ...)
async def stream(user_input: StreamInput, agent_id: str = DEFAULT_AGENT) -> StreamingResponse:
    return StreamingResponse(
        message_generator(user_input, agent_id),
        media_type="text/event-stream",
    )
```

#### 2. 消息生成器：`message_generator()`

**文件**：[`src/service/service.py`](src/service/service.py)，第 216-326 行

**核心逻辑**：

```python
async def message_generator(user_input: StreamInput, agent_id: str) -> AsyncGenerator[str, None]:
    agent: AgentGraph = get_agent(agent_id)
    kwargs, run_id = await _handle_input(user_input, agent)
    
    async for stream_event in agent.astream(
        **kwargs, 
        stream_mode=["updates", "messages", "custom"],
        subgraphs=True
    ):
        # 处理不同的事件类型
        # 转换为 SSE 格式并 yield
```

**关键点**：

1. **`stream_mode`**：
   - `"updates"`：节点更新（工具调用、中间状态）
   - `"messages"`：消息流（用于 token streaming）
   - `"custom"`：自定义事件（如任务状态）

2. **`subgraphs=True`**：支持子图（多 Agent 协作）

3. **事件结构处理**：
   ```python
   if len(stream_event) == 3:
       # subgraphs=True: (node_path, stream_mode, event)
       _, stream_mode, event = stream_event
   else:
       # 普通: (stream_mode, event)
       stream_mode, event = stream_event
   ```

**⚠️ 易错点 2：`subgraphs=True` 时事件结构变化**

如果启用 `subgraphs=True`，事件是三元组 `(node_path, stream_mode, event)`，而不是二元组。代码需要兼容两种情况。

4. **处理 interrupt**：
   ```python
   if node == "__interrupt__":
       for interrupt in updates:
           new_messages.append(AIMessage(content=interrupt.value))
   ```

5. **Token streaming**：
   ```python
   if stream_mode == "messages":
       if not user_input.stream_tokens:
           continue
       msg, metadata = event
       if isinstance(msg, AIMessageChunk):
           content = remove_tool_calls(msg.content)
           if content:
               yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
   ```

**⚠️ 易错点 3：`stream_tokens=false` 时仍会收到 message**

即使 `stream_tokens=false`，你仍会收到 `"message"` 类型的事件（工具调用、中间响应等），只是没有 `"token"` 事件。

## 🔗 从 HTTP 到 Agent 图的完整链路

### 示例：用户问 "What is 2+2?"

1. **Streamlit UI** (`src/streamlit_app.py`)
   ```python
   response = await agent_client.ainvoke(message="What is 2+2?")
   ```

2. **AgentClient** (`src/client/client.py`)
   ```python
   response = await client.post(f"{base_url}/{agent}/invoke", json=request.model_dump())
   ```

3. **FastAPI Service** (`src/service/service.py`)
   ```python
   async def invoke(user_input: UserInput, agent_id: str = DEFAULT_AGENT):
       agent = get_agent(agent_id)  # 获取 "research-assistant"
       kwargs, run_id = await _handle_input(user_input, agent)
       response_events = await agent.ainvoke(**kwargs)
   ```

4. **Agent Graph** (`src/agents/research_assistant.py`)
   ```python
   # research_assistant 是一个编译后的 StateGraph
   # 执行流程：
   # 1. guard_input → 检查安全性
   # 2. model → LLM 生成响应（可能调用 calculator 工具）
   # 3. tools → 执行工具（calculator("2+2")）
   # 4. model → LLM 整合结果
   # 5. END → 返回最终消息
   ```

5. **返回响应**
   ```python
   # FastAPI 返回 ChatMessage
   # Streamlit 显示在 UI 中
   ```

### Agent 图结构（以 research-assistant 为例）

**文件**：[`src/agents/research_assistant.py`](src/agents/research_assistant.py)

```python
agent = StateGraph(AgentState)
agent.add_node("guard_input", llama_guard_input)  # 安全检查
agent.add_node("model", acall_model)                # LLM 调用
agent.add_node("tools", ToolNode(tools))           # 工具执行
agent.add_node("block_unsafe_content", ...)        # 阻止不安全内容

agent.set_entry_point("guard_input")
agent.add_conditional_edges("guard_input", check_safety, {...})
agent.add_edge("tools", "model")
agent.add_conditional_edges("model", pending_tool_calls, {...})
```

**执行流程**：
```
guard_input → [安全?] → model → [有工具调用?] → tools → model → END
                ↓不安全
         block_unsafe_content → END
```

## 📝 关键数据结构

### `RunnableConfig`

LangGraph 的配置对象，包含：
- `configurable`：可配置参数（`thread_id`、`user_id`、`model`、`agent_config`）
- `run_id`：本次运行的唯一 ID
- `callbacks`：回调函数（用于追踪）

### `AgentState`

Agent 的状态对象（继承自 `MessagesState`）：

```python
class AgentState(MessagesState, total=False):
    safety: LlamaGuardOutput
    remaining_steps: RemainingSteps
```

- `messages`：对话历史（来自 `MessagesState`）
- `safety`：安全检查结果
- `remaining_steps`：剩余步数（防止无限循环）

### `ChatMessage`

API 返回的消息格式：

```python
class ChatMessage(BaseModel):
    type: Literal["human", "ai", "tool", "custom"]
    content: str
    tool_calls: list[ToolCall]
    tool_call_id: str | None
    run_id: str | None
    # ...
```

## ⚠️ 易错点总结

1. **`agent_config` 不能包含保留字段**
   - 错误：`{"agent_config": {"thread_id": "xxx"}}`
   - 正确：`{"thread_id": "xxx"}` 或 `{"agent_config": {"custom_param": "value"}}`

2. **`stream_tokens=false` 时仍会收到 message 事件**
   - 这是正常的，`stream_tokens` 只控制 token 粒度，不影响 message 粒度

3. **Interrupt resume 机制**
   - 如果 Agent 被中断，下一次请求会被视为 resume，而不是新消息
   - 检查逻辑在 `_handle_input()` 中

4. **`subgraphs=True` 时事件结构变化**
   - 三元组 `(node_path, stream_mode, event)` vs 二元组 `(stream_mode, event)`
   - 代码需要兼容两种情况

## 📝 下一步

- **文档 03**：学习 AI/Agent 基础概念（LLM、Tool、Graph、Memory）
- **文档 04**：了解常见疑难点和易错点

## 🔗 相关代码文件

- FastAPI 服务主文件：[`src/service/service.py`](src/service/service.py)
- 请求/响应模型：[`src/schema/schema.py`](src/schema/schema.py)
- Agent 注册表：[`src/agents/agents.py`](src/agents/agents.py)
- 默认 Agent 实现：[`src/agents/research_assistant.py`](src/agents/research_assistant.py)
- 客户端实现：[`src/client/client.py`](src/client/client.py)
