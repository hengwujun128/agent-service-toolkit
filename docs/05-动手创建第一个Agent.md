# 05 - 动手创建第一个 Agent

## 📚 学习目标

读完本文档后，你将能够：
- ✅ 从零创建一个自定义 Agent
- ✅ 理解 Agent 的基本结构（State、Node、Edge）
- ✅ 添加自定义工具（Tool）
- ✅ 将 Agent 注册到服务中

## 🎯 5 分钟验证

完成以下步骤后，你应该能：
1. 在 `/info` 端点看到你的新 Agent
2. 通过 Streamlit UI 与你的 Agent 对话
3. 看到自定义工具被调用

## 📖 实战：创建一个翻译助手

我们将创建一个简单的翻译助手 Agent，它可以：
- 回答用户问题
- 使用翻译工具（模拟）
- 记住对话历史

### 步骤 1：创建 Agent 文件

在 `src/agents/` 目录下创建 `translator_agent.py`：

```python
# src/agents/translator_agent.py
"""
翻译助手 Agent - 一个简单的示例 Agent
演示如何创建带工具的自定义 Agent
"""

from datetime import datetime
from typing import Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage
from langchain_core.runnables import RunnableConfig, RunnableLambda, RunnableSerializable
from langchain_core.tools import tool
from langgraph.graph import END, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode

from core import get_model, settings


# ========== 1. 定义状态 ==========
class TranslatorState(MessagesState, total=False):
    """Agent 的状态结构
    
    MessagesState 提供了 `messages` 字段，用于存储对话历史
    total=False 表示其他字段是可选的
    """
    pass  # 这里可以添加自定义字段，比如 language_preference


# ========== 2. 定义工具 ==========
@tool
def translate_text(text: str, target_language: str) -> str:
    """将文本翻译成目标语言。
    
    Args:
        text: 要翻译的文本
        target_language: 目标语言（如 "英语", "中文", "日语"）
    
    Returns:
        翻译后的文本
    """
    # 这是一个模拟实现，实际项目中可以调用翻译 API
    translations = {
        "英语": f"[English Translation] {text}",
        "中文": f"[中文翻译] {text}",
        "日语": f"[日本語翻訳] {text}",
        "法语": f"[Traduction française] {text}",
    }
    return translations.get(target_language, f"[Translation to {target_language}] {text}")


@tool
def detect_language(text: str) -> str:
    """检测文本的语言。
    
    Args:
        text: 要检测的文本
    
    Returns:
        检测到的语言
    """
    # 简单的模拟实现
    if any('\u4e00' <= char <= '\u9fff' for char in text):
        return "检测到语言：中文"
    elif any('\u3040' <= char <= '\u30ff' for char in text):
        return "检测到语言：日语"
    else:
        return "检测到语言：英语（默认）"


# 工具列表
tools = [translate_text, detect_language]


# ========== 3. 定义 System Prompt ==========
current_date = datetime.now().strftime("%Y年%m月%d日")
instructions = f"""
你是一个专业的翻译助手。今天是 {current_date}。

你的能力：
1. 使用 translate_text 工具将文本翻译成指定语言
2. 使用 detect_language 工具检测文本的语言

重要提示：
- 用户看不到工具的原始返回结果，你需要解释工具的输出
- 翻译时要保持原文的语气和风格
- 如果不确定目标语言，先询问用户

支持的语言：英语、中文、日语、法语
"""


# ========== 4. 定义模型包装器 ==========
def wrap_model(model: BaseChatModel) -> RunnableSerializable[TranslatorState, AIMessage]:
    """包装模型，添加工具绑定和 system prompt"""
    # 绑定工具到模型
    bound_model = model.bind_tools(tools)
    
    # 添加 system prompt
    preprocessor = RunnableLambda(
        lambda state: [SystemMessage(content=instructions)] + state["messages"],
        name="AddSystemPrompt",
    )
    
    return preprocessor | bound_model


# ========== 5. 定义节点函数 ==========
async def call_model(state: TranslatorState, config: RunnableConfig) -> TranslatorState:
    """调用 LLM 模型的节点"""
    # 获取模型（支持动态切换）
    model = get_model(config["configurable"].get("model", settings.DEFAULT_MODEL))
    model_runnable = wrap_model(model)
    
    # 调用模型
    response = await model_runnable.ainvoke(state, config)
    
    return {"messages": [response]}


# ========== 6. 定义条件边函数 ==========
def should_continue(state: TranslatorState) -> Literal["tools", "end"]:
    """决定是否继续执行工具"""
    last_message = state["messages"][-1]
    
    # 如果最后一条消息包含工具调用，则执行工具
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    
    # 否则结束
    return "end"


# ========== 7. 构建图 ==========
# 创建状态图
graph = StateGraph(TranslatorState)

# 添加节点
graph.add_node("model", call_model)
graph.add_node("tools", ToolNode(tools))

# 设置入口点
graph.set_entry_point("model")

# 添加边
graph.add_conditional_edges(
    "model",                          # 从 model 节点出发
    should_continue,                  # 使用 should_continue 函数决定下一步
    {"tools": "tools", "end": END}    # 映射：返回值 -> 目标节点
)
graph.add_edge("tools", "model")      # tools 执行完后回到 model

# 编译图
translator_agent = graph.compile()
```

### 步骤 2：注册 Agent

在 `src/agents/agents.py` 中添加你的 Agent：

```python
# 在文件顶部添加 import
from agents.translator_agent import translator_agent

# 在 agents 字典中添加
agents: dict[str, Agent] = {
    # ... 其他 agents
    "translator": Agent(
        description="A translator assistant that can translate text between languages.",
        graph_like=translator_agent
    ),
}
```

### 步骤 3：测试你的 Agent

**方法 1：使用 curl**

```bash
# 测试翻译功能
curl -X POST http://0.0.0.0:8080/translator/invoke \
  -H "Content-Type: application/json" \
  -d '{"message": "请帮我把 Hello World 翻译成中文"}'
```

**方法 2：使用 Streamlit UI**

1. 打开 `http://localhost:8501`
2. 在侧边栏选择 `translator` Agent
3. 输入：`请帮我把 Hello World 翻译成中文`

### 步骤 4：理解代码结构

```
translator_agent.py
├── TranslatorState        # 状态定义（继承 MessagesState）
├── tools                  # 工具列表
│   ├── translate_text     # 翻译工具
│   └── detect_language    # 语言检测工具
├── instructions           # System Prompt
├── wrap_model()           # 模型包装器
├── call_model()           # 模型调用节点
├── should_continue()      # 条件边函数
└── translator_agent       # 编译后的图
```

**执行流程**：

```
START → model → [有工具调用?] → tools → model → [有工具调用?] → ... → END
         ↓              ↓
         └──── 没有 ────┘→ END
```

## 🔧 进阶：添加更多功能

### 1. 添加新工具

```python
@tool
def get_word_count(text: str) -> str:
    """统计文本的字数和词数"""
    char_count = len(text)
    word_count = len(text.split())
    return f"字符数: {char_count}, 词数: {word_count}"

# 添加到工具列表
tools = [translate_text, detect_language, get_word_count]
```

### 2. 添加自定义状态字段

```python
class TranslatorState(MessagesState, total=False):
    """扩展状态"""
    preferred_language: str      # 用户偏好语言
    translation_count: int       # 翻译次数统计
```

### 3. 添加内容安全检查

参考 `research_assistant.py` 中的 `llama_guard_input` 节点，添加输入检查：

```python
from agents.llama_guard import LlamaGuard, LlamaGuardOutput, SafetyAssessment

async def check_input_safety(state: TranslatorState, config: RunnableConfig) -> TranslatorState:
    """检查输入内容是否安全"""
    llama_guard = LlamaGuard()
    safety_output = await llama_guard.ainvoke("User", state["messages"])
    return {"safety": safety_output, "messages": []}
```

## ⚠️ 常见问题

### Q1: Agent 未出现在 `/info` 端点

**检查**：
1. 确保在 `agents.py` 中正确导入和注册
2. 重启服务：`python src/run_service.py`

### Q2: 工具未被调用

**检查**：
1. 确保 `model.bind_tools(tools)` 正确调用
2. 检查工具的 docstring 是否清晰（LLM 用它决定是否调用）
3. 检查 `should_continue` 函数是否正确返回 `"tools"`

### Q3: 对话历史丢失

**检查**：
1. 确保使用相同的 `thread_id` 发送请求
2. 检查 `messages` 是否正确返回（`return {"messages": [response]}`）

## 📝 下一步

- **文档 06**：深入理解 LangGraph 图结构
- **文档 10**：学习 RAG 实现
- **文档 11**：学习 MCP 工具编排

## 🔗 相关代码文件

- 最简单的 Agent：[`src/agents/chatbot.py`](../src/agents/chatbot.py)
- 带工具的 Agent：[`src/agents/research_assistant.py`](../src/agents/research_assistant.py)
- 工具定义示例：[`src/agents/tools.py`](../src/agents/tools.py)
- Agent 注册表：[`src/agents/agents.py`](../src/agents/agents.py)
