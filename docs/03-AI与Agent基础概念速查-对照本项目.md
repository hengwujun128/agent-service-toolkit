# 03 - AI 与 Agent 基础概念速查：对照本项目

## 📚 学习目标

读完本文档后，你将能够：
- ✅ 理解 AI/Agent 开发中的核心术语（LLM、Tool、Graph、Memory 等）
- ✅ 知道每个概念在本项目中的具体实现位置
- ✅ 理解这些概念之间的关系
- ✅ 能够阅读和修改 Agent 代码

## 🎯 5 分钟验证

完成以下步骤后，你应该能：
1. 在代码中找到 LLM 初始化的位置
2. 理解一个 Tool 是如何定义和使用的
3. 看懂一个简单的 Agent 图结构

## 📖 核心概念速查表

### 1. LLM (Large Language Model) - 大语言模型

**一句话解释**：能够理解和生成自然语言的 AI 模型（如 GPT-4、Claude、Gemini）。

**前端类比**：类似一个"智能 API"，输入文本，返回文本。

**在本项目中的位置**：
- **模型定义**：[`src/schema/models.py`](src/schema/models.py) - 定义所有支持的模型枚举
- **模型初始化**：[`src/core/llm.py`](src/core/llm.py) - `get_model()` 函数根据模型名返回对应的 LangChain ChatModel
- **使用示例**：在 Agent 节点中调用 `get_model(config["configurable"].get("model", settings.DEFAULT_MODEL))`

**代码示例**：
```python
# src/core/llm.py
@cache
def get_model(model_name: AllModelEnum) -> ModelT:
    if model_name in OpenAIModelName:
        return ChatOpenAI(model=api_model_name, streaming=True)
    # ... 其他模型
```

**关键点**：
- 所有模型都实现了 `BaseChatModel` 接口
- 支持流式输出（`streaming=True`）
- 模型选择通过环境变量中的 API Key 决定（见 `src/core/settings.py`）

---

### 2. ChatModel - 聊天模型

**一句话解释**：专门用于对话的 LLM 包装器，处理消息历史（HumanMessage、AIMessage、SystemMessage）。

**前端类比**：类似 React 的 Context，维护对话状态。

**在本项目中的位置**：
- **消息类型**：使用 LangChain 的 `langchain_core.messages`（`HumanMessage`、`AIMessage`、`SystemMessage`）
- **使用示例**：在 Agent 节点中，`state["messages"]` 包含对话历史

**代码示例**：
```python
# src/agents/research_assistant.py
from langchain_core.messages import AIMessage, SystemMessage

def wrap_model(model: BaseChatModel) -> RunnableSerializable:
    preprocessor = RunnableLambda(
        lambda state: [SystemMessage(content=instructions)] + state["messages"],
    )
    return preprocessor | model
```

**关键点**：
- `SystemMessage`：系统提示（告诉模型如何行为）
- `HumanMessage`：用户输入
- `AIMessage`：AI 响应
- `ToolMessage`：工具调用结果

---

### 3. Prompt / SystemMessage - 提示词

**一句话解释**：告诉 LLM 如何行为的指令文本。

**前端类比**：类似组件的 `props` 或配置对象，定义组件的行为。

**在本项目中的位置**：
- **示例 1**：[`src/agents/research_assistant.py`](src/agents/research_assistant.py) 第 40-51 行
  ```python
  instructions = f"""
      You are a helpful research assistant with the ability to search the web and use other tools.
      Today's date is {current_date}.
      
      NOTE: THE USER CAN'T SEE THE TOOL RESPONSE.
      ...
  """
  ```
- **示例 2**：[`src/agents/rag_assistant.py`](src/agents/rag_assistant.py) 第 34-47 行

**关键点**：
- 通常包含角色定义、行为规则、工具使用说明
- **重要**：`NOTE: THE USER CAN'T SEE THE TOOL RESPONSE.` - 用户看不到工具调用的原始结果，需要 Agent 解释

---

### 4. Tool / Function Calling - 工具/函数调用

**一句话解释**：LLM 可以调用的外部函数（如搜索、计算器、数据库查询）。

**前端类比**：类似 API 调用或服务函数，但由 AI 决定何时调用。

**在本项目中的位置**：
- **工具定义**：[`src/agents/tools.py`](src/agents/tools.py)
  - `calculator`：数学计算
  - `database_search`：RAG 数据库搜索
- **工具使用**：在 Agent 中通过 `model.bind_tools(tools)` 绑定工具

**代码示例**：
```python
# src/agents/tools.py
@tool
def calculator_func(expression: str) -> str:
    """Calculates a math expression using numexpr."""
    # ... 实现

calculator: BaseTool = tool(calculator_func)

# src/agents/research_assistant.py
tools = [web_search, calculator]
bound_model = model.bind_tools(tools)  # 绑定工具
```

**关键点**：
- 工具必须有清晰的 `description`（LLM 用它决定是否调用）
- 工具参数通过 `@tool` 装饰器自动提取
- LLM 返回 `tool_calls`，然后由 `ToolNode` 执行

---

### 5. Agent - 智能体

**一句话解释**：能够使用工具、维护记忆、做出决策的 AI 系统。

**前端类比**：类似一个"智能组件"，有状态、有逻辑、能调用外部服务。

**在本项目中的位置**：
- **Agent 定义**：`src/agents/*.py` 文件
- **Agent 注册**：[`src/agents/agents.py`](src/agents/agents.py)
- **默认 Agent**：`research-assistant`（见 `DEFAULT_AGENT = "research-assistant"`）

**代码示例**：
```python
# src/agents/research_assistant.py
agent = StateGraph(AgentState)
agent.add_node("model", acall_model)
agent.add_node("tools", ToolNode(tools))
research_assistant = agent.compile()
```

**关键点**：
- Agent 是一个**图**（StateGraph），不是单个函数
- Agent 有**状态**（`AgentState`），包含消息历史等
- Agent 通过**节点**和**边**定义工作流

---

### 6. ReAct Pattern - 推理与行动模式

**一句话解释**：Agent 的经典模式：Reasoning（推理）→ Acting（行动/调用工具）→ Observing（观察结果）→ 循环。

**前端类比**：类似 Redux 的 action → reducer → state 循环。

**在本项目中的位置**：
- **实现**：通过 LangGraph 的条件边实现
- **示例**：[`src/agents/research_assistant.py`](src/agents/research_assistant.py) 第 135-144 行
  ```python
  def pending_tool_calls(state: AgentState) -> Literal["tools", "done"]:
      last_message = state["messages"][-1]
      if last_message.tool_calls:
          return "tools"  # 有工具调用，执行工具
      return "done"       # 没有工具调用，结束
  ```

**执行流程**：
```
model → [有工具调用?] → tools → model → [有工具调用?] → tools → ... → END
```

---

### 7. LangGraph - 图框架

**一句话解释**：用于构建 Agent 工作流的框架，用"图"（节点+边）定义 Agent 的执行流程。

**前端类比**：类似状态机（如 XState）或工作流引擎。

**核心概念**：

#### 7.1 StateGraph - 状态图

**一句话解释**：定义 Agent 的节点、边和状态结构。

**在本项目中的位置**：
- **定义**：所有 Agent 文件（如 `src/agents/research_assistant.py`）
- **示例**：
  ```python
  agent = StateGraph(AgentState)  # 创建图
  agent.add_node("model", acall_model)  # 添加节点
  agent.add_edge("tools", "model")  # 添加边
  agent.compile()  # 编译图
  ```

#### 7.2 Node - 节点

**一句话解释**：图中的一个执行单元（函数），处理状态并返回更新。

**在本项目中的位置**：
- **示例节点**：
  - `"model"`：调用 LLM
  - `"tools"`：执行工具（使用 `ToolNode`）
  - `"guard_input"`：安全检查
  - `"determine_birthdate"`：提取生日（interrupt-agent）

**代码示例**：
```python
async def acall_model(state: AgentState, config: RunnableConfig) -> AgentState:
    # 处理逻辑
    return {"messages": [response]}  # 返回状态更新
```

#### 7.3 Edge - 边

**一句话解释**：定义节点之间的连接（执行顺序）。

**类型**：
- **固定边**：`agent.add_edge("tools", "model")` - 总是执行
- **条件边**：`agent.add_conditional_edges("model", pending_tool_calls, {...})` - 根据条件选择

**在本项目中的位置**：
- **示例**：[`src/agents/research_assistant.py`](src/agents/research_assistant.py) 第 124-144 行

#### 7.4 State - 状态

**一句话解释**：Agent 的运行时数据（消息历史、中间变量等）。

**在本项目中的位置**：
- **定义**：每个 Agent 文件开头的 `AgentState` 类
- **示例**：
  ```python
  class AgentState(MessagesState, total=False):
      safety: LlamaGuardOutput
      remaining_steps: RemainingSteps
  ```

**关键点**：
- `MessagesState` 提供 `messages` 字段（对话历史）
- `total=False` 表示字段可选

#### 7.5 Compile - 编译

**一句话解释**：将图定义转换为可执行的运行时对象。

**代码示例**：
```python
research_assistant = agent.compile()  # 返回 CompiledStateGraph
```

---

### 8. Memory - 记忆

**一句话解释**：Agent 保存和检索对话历史、用户数据的能力。

**两种类型**：

#### 8.1 Checkpointer - 检查点（短期记忆）

**一句话解释**：保存对话历史（`thread_id` 级别），用于多轮对话。

**前端类比**：类似 sessionStorage，单次会话有效。

**在本项目中的位置**：
- **初始化**：[`src/service/service.py`](src/service/service.py) 第 72-79 行
  ```python
  async with initialize_database() as saver:
      agent.checkpointer = saver  # 设置 checkpointer
  ```
- **实现**：[`src/memory/postgres.py`](src/memory/postgres.py)、`src/memory/sqlite.py`、`src/memory/mongodb.py`
- **使用**：通过 `thread_id` 自动关联对话历史

**关键点**：
- 每个 `thread_id` 有独立的对话历史
- 用于 `agent.aget_state(config={"thread_id": "xxx"})` 获取历史

#### 8.2 Store - 存储（长期记忆）

**一句话解释**：保存跨对话的用户数据（`user_id` 级别），用于长期记忆。

**前端类比**：类似 localStorage，跨会话有效。

**在本项目中的位置**：
- **初始化**：[`src/service/service.py`](src/service/service.py) 第 73-79 行
  ```python
  async with initialize_store() as store:
      agent.store = store  # 设置 store
  ```
- **使用示例**：[`src/agents/interrupt_agent.py`](src/agents/interrupt_agent.py) 第 77-172 行
  ```python
  # 读取
  result = await store.aget((user_id,), key="birthdate")
  # 写入
  await store.aput((user_id,), "birthdate", {"birthdate": birthdate_str})
  ```

**关键点**：
- 使用 `namespace`（通常是 `(user_id,)`）和 `key` 存储数据
- 用于保存用户偏好、提取的信息等

---

### 9. Streaming - 流式输出

**一句话解释**：实时返回 LLM 生成的 token，而不是等待完整响应。

**前端类比**：类似 WebSocket 或 SSE（Server-Sent Events）。

**两种类型**：

#### 9.1 Token Streaming - Token 流

**一句话解释**：逐字返回 LLM 生成的文本（如 "Hello" → " world" → "!"）。

**在本项目中的位置**：
- **服务端**：[`src/service/service.py`](src/service/service.py) 第 306-321 行
  ```python
  if stream_mode == "messages":
      if isinstance(msg, AIMessageChunk):
          content = remove_tool_calls(msg.content)
          yield f"data: {json.dumps({'type': 'token', 'content': content})}\n\n"
  ```
- **客户端**：[`src/client/client.py`](src/client/client.py) 第 196-198 行
  ```python
  case "token":
      return parsed["content"]  # 直接返回字符串
  ```

#### 9.2 Message Streaming - 消息流

**一句话解释**：返回完整的消息对象（工具调用、中间响应等）。

**在本项目中的位置**：
- **服务端**：[`src/service/service.py`](src/service/service.py) 第 241-304 行
- **客户端**：[`src/client/client.py`](src/client/client.py) 第 190-195 行

**关键点**：
- `stream_tokens=false` 时，仍会收到 `"message"` 事件，但没有 `"token"` 事件
- 用于显示工具调用状态、中间结果等

---

### 10. Interrupt - 中断

**一句话解释**：Agent 暂停执行，等待用户输入后再继续。

**前端类比**：类似 `await` 或 Promise，等待用户响应。

**在本项目中的位置**：
- **实现**：[`src/agents/interrupt_agent.py`](src/agents/interrupt_agent.py) 第 138 行
  ```python
  birthdate_input = interrupt(f"{response.reasoning}\nPlease tell me your birthdate?")
  ```
- **恢复处理**：[`src/service/service.py`](src/service/service.py) 第 154-163 行
  ```python
  if interrupted_tasks:
      input = Command(resume=user_input.message)  # 恢复执行
  ```

**关键点**：
- `interrupt()` 返回一个值，用户下次请求时通过 `Command(resume=...)` 传递
- 用于需要用户确认、补充信息的场景

---

### 11. Guard / Moderation - 内容安全

**一句话解释**：检查用户输入或 AI 输出是否包含不安全内容。

**在本项目中的位置**：
- **实现**：[`src/agents/llama_guard.py`](src/agents/llama_guard.py)
- **使用**：[`src/agents/research_assistant.py`](src/agents/research_assistant.py) 第 94-101 行
  ```python
  async def llama_guard_input(state: AgentState, config: RunnableConfig):
      llama_guard = LlamaGuard()
      safety_output = await llama_guard.ainvoke("User", state["messages"])
      return {"safety": safety_output, "messages": []}
  ```

**关键点**：
- 需要 Groq API Key（LlamaGuard 运行在 Groq 上）
- 在 Agent 图的入口节点检查用户输入

---

### 12. RAG (Retrieval-Augmented Generation) - 检索增强生成

**一句话解释**：从向量数据库中检索相关文档，然后让 LLM 基于这些文档生成回答。

**前端类比**：类似搜索引擎 + AI 总结。

**在本项目中的位置**：
- **向量数据库创建**：[`scripts/create_chroma_db.py`](scripts/create_chroma_db.py)
- **检索工具**：[`src/agents/tools.py`](src/agents/tools.py) 第 65-76 行
- **RAG Agent**：[`src/agents/rag_assistant.py`](src/agents/rag_assistant.py)

**工作流程**：
1. 文档分块（chunk）→ 2. 向量化（embedding）→ 3. 存储到 ChromaDB → 4. 查询时检索相似文档 → 5. LLM 基于文档生成回答

**关键概念**：
- **Embedding**：将文本转换为向量（用于相似度搜索）
- **Chunk**：将长文档分割成小块（chunk_size、chunk_overlap）
- **Retriever**：从向量数据库中检索相关文档

---

## 🔗 概念关系图

```
LLM (模型)
  ↓
ChatModel (包装器，处理消息)
  ↓
Agent (图结构)
  ├─ Nodes (节点：model, tools, guard)
  ├─ Edges (边：条件/固定)
  └─ State (状态：messages, safety, ...)
      ↓
Memory
  ├─ Checkpointer (thread_id → 对话历史)
  └─ Store (user_id → 长期数据)
      ↓
Tools (外部函数)
  ├─ calculator
  ├─ database_search (RAG)
  └─ web_search
```

## 📝 下一步

- **文档 04**：了解常见疑难点和易错点
- **文档 10**（可选）：深入学习 RAG
- **文档 11**（可选）：深入学习 MCP

## 🔗 相关代码文件

- LLM 初始化：[`src/core/llm.py`](src/core/llm.py)
- 工具定义：[`src/agents/tools.py`](src/agents/tools.py)
- Agent 示例：[`src/agents/research_assistant.py`](src/agents/research_assistant.py)
- RAG Agent：[`src/agents/rag_assistant.py`](src/agents/rag_assistant.py)
- Interrupt Agent：[`src/agents/interrupt_agent.py`](src/agents/interrupt_agent.py)
- Memory 实现：[`src/memory/`](src/memory/)
