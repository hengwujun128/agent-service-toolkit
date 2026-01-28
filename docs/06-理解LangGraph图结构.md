# 06 - 理解 LangGraph 图结构

## 📚 学习目标

读完本文档后，你将能够：
- ✅ 理解 LangGraph 的核心概念（State、Node、Edge）
- ✅ 区分固定边（Edge）和条件边（Conditional Edge）
- ✅ 理解 Agent 的执行流程
- ✅ 能够设计复杂的 Agent 工作流

## 🎯 5 分钟验证

完成以下步骤后，你应该能：
1. 画出 `research_assistant` 的执行流程图
2. 理解 `ToolNode` 的作用
3. 知道如何添加新节点和边

## 📖 LangGraph 核心概念

### 类比前端状态管理

如果你熟悉前端状态管理，LangGraph 的概念可以这样类比：

| LangGraph | 前端类比 | 说明 |
|-----------|---------|------|
| **StateGraph** | XState Machine / Redux Store | 整体状态容器 |
| **State** | Store State | 当前状态数据 |
| **Node** | Action Handler / Reducer | 处理状态的函数 |
| **Edge** | Transition | 状态转换规则 |
| **Conditional Edge** | Guard / Middleware | 条件分支逻辑 |
| **compile()** | createStore() | 创建可运行实例 |

### 1. State（状态）

**定义**：Agent 运行时的数据结构，包含所有需要在节点间传递的信息。

**在本项目中**：

```python
# src/agents/research_assistant.py
class AgentState(MessagesState, total=False):
    """Agent 的状态结构"""
    safety: LlamaGuardOutput      # 安全检查结果
    remaining_steps: RemainingSteps  # 剩余步数
```

**关键点**：
- `MessagesState` 提供 `messages: list[BaseMessage]` 字段
- `total=False` 表示其他字段是可选的
- 状态在节点间**累积更新**（不是替换）

**状态更新规则**：

```python
# 节点返回值会与现有状态合并
async def my_node(state: AgentState) -> AgentState:
    # state["messages"] 已有 [msg1, msg2]
    return {"messages": [new_msg]}  
    # 合并后: state["messages"] = [msg1, msg2, new_msg]
```

### 2. Node（节点）

**定义**：图中的执行单元，是一个接收状态、返回状态更新的函数。

**在本项目中的示例**：

```python
# src/agents/research_assistant.py

# 节点 1: 调用模型
async def acall_model(state: AgentState, config: RunnableConfig) -> AgentState:
    model = get_model(config["configurable"].get("model", settings.DEFAULT_MODEL))
    response = await model.ainvoke(state["messages"])
    return {"messages": [response]}  # 返回状态更新

# 节点 2: 安全检查
async def llama_guard_input(state: AgentState, config: RunnableConfig) -> AgentState:
    llama_guard = LlamaGuard()
    safety_output = await llama_guard.ainvoke("User", state["messages"])
    return {"safety": safety_output, "messages": []}

# 节点 3: 工具执行（使用预置的 ToolNode）
tools_node = ToolNode(tools)  # LangGraph 提供的工具执行节点
```

**节点签名**：

```python
async def node_function(
    state: AgentState,           # 当前状态
    config: RunnableConfig,      # 运行配置（可选）
    store: BaseStore,            # 长期存储（可选）
) -> AgentState:                 # 返回状态更新
    ...
```

### 3. Edge（边）

**定义**：定义节点之间的连接关系，决定执行顺序。

#### 3.1 固定边（Edge）

**定义**：无条件的连接，执行完源节点后一定会执行目标节点。

```python
# src/agents/research_assistant.py
agent.add_edge("tools", "model")  # tools 执行完后，一定执行 model
agent.add_edge("block_unsafe_content", END)  # 阻断后直接结束
```

**语法**：
```python
graph.add_edge(source_node, target_node)
```

#### 3.2 条件边（Conditional Edge）

**定义**：根据条件选择下一个节点。

```python
# src/agents/research_assistant.py

# 条件函数：返回下一个节点的名称
def pending_tool_calls(state: AgentState) -> Literal["tools", "done"]:
    last_message = state["messages"][-1]
    if last_message.tool_calls:
        return "tools"
    return "done"

# 添加条件边
agent.add_conditional_edges(
    "model",                              # 源节点
    pending_tool_calls,                   # 条件函数
    {"tools": "tools", "done": END}       # 映射：返回值 -> 目标节点
)
```

**语法**：
```python
graph.add_conditional_edges(
    source_node,           # 源节点名称
    condition_function,    # 条件函数，返回字符串
    path_map               # 字典：条件函数返回值 -> 目标节点
)
```

### 4. 特殊节点

#### START（入口点）

```python
graph.set_entry_point("guard_input")  # 设置入口节点
# 等价于
graph.add_edge(START, "guard_input")
```

#### END（结束点）

```python
from langgraph.graph import END

graph.add_edge("generate_response", END)  # 结束执行
```

## 📊 本项目中的图结构分析

### 1. chatbot（最简单）

**特点**：使用 `@entrypoint()` 装饰器，没有显式的图结构。

```python
@entrypoint()
async def chatbot(inputs, previous, config):
    # 单节点执行
    response = await model.ainvoke(messages)
    return entrypoint.final(value={"messages": [response]}, ...)
```

**执行流程**：
```
START → chatbot → END
```

### 2. research_assistant（标准模式）

**特点**：ReAct 模式（推理-行动循环）+ 安全检查。

```python
# 图结构
agent = StateGraph(AgentState)
agent.add_node("guard_input", llama_guard_input)
agent.add_node("block_unsafe_content", block_unsafe_content)
agent.add_node("model", acall_model)
agent.add_node("tools", ToolNode(tools))

agent.set_entry_point("guard_input")
agent.add_conditional_edges("guard_input", check_safety, {...})
agent.add_conditional_edges("model", pending_tool_calls, {...})
agent.add_edge("tools", "model")
agent.add_edge("block_unsafe_content", END)
```

**执行流程图**：

```
                    ┌─────────────────────────────────────────────────────┐
                    │                                                     │
                    ▼                                                     │
START → guard_input → [safe?] → model → [tool_calls?] → tools ──────────┘
                         │                    │
                         │ unsafe             │ no tools
                         ▼                    ▼
                  block_unsafe_content       END
                         │
                         ▼
                        END
```

### 3. interrupt_agent（线性 + 中断）

**特点**：线性流程 + `interrupt()` 暂停执行。

```python
agent = StateGraph(AgentState)
agent.add_node("background", background)
agent.add_node("determine_birthdate", determine_birthdate)
agent.add_node("generate_response", generate_response)

agent.set_entry_point("background")
agent.add_edge("background", "determine_birthdate")
agent.add_edge("determine_birthdate", "generate_response")
agent.add_edge("generate_response", END)
```

**执行流程**：
```
START → background → determine_birthdate → generate_response → END
                            │
                            │ interrupt()
                            ▼
                    [等待用户输入]
                            │
                            │ resume
                            ▼
                    继续 determine_birthdate
```

## 🔧 实战：设计复杂图结构

### 示例：多步骤审核流程

假设我们要设计一个文章审核 Agent，流程如下：
1. 检查文章格式
2. 检查敏感词
3. AI 内容评估
4. 人工复核（如果 AI 不确定）

```python
from typing import Literal
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

class ReviewState(MessagesState, total=False):
    format_ok: bool
    sensitive_ok: bool
    ai_score: float
    human_approved: bool | None

# 节点定义
async def check_format(state: ReviewState) -> ReviewState:
    # 检查格式...
    return {"format_ok": True}

async def check_sensitive(state: ReviewState) -> ReviewState:
    # 检查敏感词...
    return {"sensitive_ok": True}

async def ai_review(state: ReviewState) -> ReviewState:
    # AI 评估...
    return {"ai_score": 0.75}

async def human_review(state: ReviewState) -> ReviewState:
    # 中断等待人工审核
    result = interrupt("请进行人工审核")
    return {"human_approved": result == "approved"}

async def generate_result(state: ReviewState) -> ReviewState:
    # 生成最终结果...
    return {"messages": [...]}

# 条件函数
def format_check(state: ReviewState) -> Literal["continue", "reject"]:
    return "continue" if state["format_ok"] else "reject"

def sensitive_check(state: ReviewState) -> Literal["continue", "reject"]:
    return "continue" if state["sensitive_ok"] else "reject"

def ai_confidence(state: ReviewState) -> Literal["approve", "human", "reject"]:
    score = state["ai_score"]
    if score > 0.9:
        return "approve"
    elif score > 0.5:
        return "human"  # 需要人工复核
    else:
        return "reject"

# 构建图
graph = StateGraph(ReviewState)
graph.add_node("check_format", check_format)
graph.add_node("check_sensitive", check_sensitive)
graph.add_node("ai_review", ai_review)
graph.add_node("human_review", human_review)
graph.add_node("generate_result", generate_result)

graph.set_entry_point("check_format")

graph.add_conditional_edges("check_format", format_check, {
    "continue": "check_sensitive",
    "reject": "generate_result"
})

graph.add_conditional_edges("check_sensitive", sensitive_check, {
    "continue": "ai_review",
    "reject": "generate_result"
})

graph.add_conditional_edges("ai_review", ai_confidence, {
    "approve": "generate_result",
    "human": "human_review",
    "reject": "generate_result"
})

graph.add_edge("human_review", "generate_result")
graph.add_edge("generate_result", END)

review_agent = graph.compile()
```

**执行流程图**：

```
START → check_format → [ok?] → check_sensitive → [ok?] → ai_review → [score?]
              │                      │                        │
              │ reject               │ reject                 │ approve
              ▼                      ▼                        ▼
        generate_result ◄───────────────────────────── generate_result
              │                                              ▲
              │                      human (0.5-0.9)         │
              │                           │                  │
              │                           ▼                  │
              │                    human_review ─────────────┘
              ▼
             END
```

## ⚠️ 常见问题

### Q1: 状态更新是替换还是合并？

**答**：默认是**合并**。对于列表类型（如 `messages`），新值会**追加**到现有列表。

```python
# 原状态: {"messages": [msg1, msg2]}
return {"messages": [msg3]}
# 新状态: {"messages": [msg1, msg2, msg3]}
```

### Q2: 如何完全替换状态？

使用 `Command` 和 `goto` 可以实现更复杂的状态控制：

```python
from langgraph.types import Command

return Command(
    update={"messages": [new_msg]},  # 更新状态
    goto="next_node"                  # 跳转到指定节点
)
```

### Q3: 条件函数必须是 Literal 类型吗？

**推荐**使用 `Literal` 类型注解，便于类型检查和文档生成：

```python
def my_condition(state) -> Literal["a", "b", "c"]:
    ...
```

### Q4: 如何调试图结构？

1. **可视化**：使用 `graph.get_graph().draw_mermaid_png()`
2. **日志**：在节点中添加 `logger.debug(f"State: {state}")`
3. **LangSmith**：启用追踪查看完整执行过程

## 📝 下一步

- **文档 10**：学习 RAG 实现，理解检索增强生成
- **文档 11**：学习 MCP 工具编排
- **文档 12**：学习多 Agent 协作（Supervisor 模式）

## 🔗 相关代码文件

- 最简单的图：[`src/agents/chatbot.py`](../src/agents/chatbot.py)
- 标准 ReAct 模式：[`src/agents/research_assistant.py`](../src/agents/research_assistant.py)
- 带中断的图：[`src/agents/interrupt_agent.py`](../src/agents/interrupt_agent.py)
- Supervisor 模式：[`src/agents/langgraph_supervisor_agent.py`](../src/agents/langgraph_supervisor_agent.py)

## 🔗 外部资源

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [LangGraph 概念指南](https://langchain-ai.github.io/langgraph/concepts/)
- [StateGraph API](https://langchain-ai.github.io/langgraph/reference/graphs/#langgraph.graph.StateGraph)
