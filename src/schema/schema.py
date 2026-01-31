"""
API Schema 模块：定义 FastAPI 服务所有端点的请求/响应数据结构。

本文件是服务与客户端之间的"契约"：
- 服务端用这些 Schema 做参数校验和序列化
- 客户端（Streamlit、run_client.py）用同样的 Schema 做反序列化
- OpenAPI 文档自动从这些 Schema 生成

详细的数据流图、端点对应关系、使用示例见 schema.md
"""

from typing import Any, Literal, NotRequired

from pydantic import BaseModel, Field, SerializeAsAny
from typing_extensions import TypedDict

from schema.models import AllModelEnum, AnthropicModelName, OpenAIModelName


# =============================================================================
# /info 端点相关
# =============================================================================


class AgentInfo(BaseModel):
    """单个 Agent 的信息，用于告诉客户端有哪些 Agent 可用。"""

    key: str = Field(
        description="Agent 唯一标识符，用于 URL 路径（如 /research-assistant/invoke）",
        examples=["research-assistant"],
    )
    description: str = Field(
        description="Agent 功能描述，显示在 UI 的下拉菜单里",
        examples=["A research assistant for generating research papers."],
    )


class ServiceMetadata(BaseModel):
    """服务元数据，由 GET /info 返回。客户端用它初始化界面。"""

    agents: list[AgentInfo] = Field(
        description="当前服务可用的 Agent 列表",
    )
    models: list[AllModelEnum] = Field(
        description="当前服务可用的 LLM 模型列表（根据已配置的 API Key 决定）",
    )
    default_agent: str = Field(
        description="默认 Agent（未指定时使用）",
        examples=["research-assistant"],
    )
    default_model: AllModelEnum = Field(
        description="默认模型（未指定时使用）",
    )


# =============================================================================
# /invoke 和 /stream 端点相关
# =============================================================================


class UserInput(BaseModel):
    """用户输入，POST /invoke 的请求体。"""

    message: str = Field(
        description="用户发送的消息内容",
        examples=["What is the weather in Tokyo?"],
    )
    model: SerializeAsAny[AllModelEnum] | None = Field(
        title="Model",
        description="使用的 LLM 模型。不传则用服务默认模型。",
        default=None,
        examples=[OpenAIModelName.GPT_5_NANO, AnthropicModelName.HAIKU_45],
    )
    thread_id: str | None = Field(
        description="线程 ID，用于多轮对话。同一 thread_id 的消息会保持上下文。",
        default=None,
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    user_id: str | None = Field(
        description="用户 ID，用于跨线程的长期记忆（如用户偏好）。",
        default=None,
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    agent_config: dict[str, Any] = Field(
        description="传给 Agent 的额外配置（不能包含 thread_id/user_id/model 等保留字段）",
        default={},
        examples=[{"spicy_level": 0.8}],
    )


class StreamInput(UserInput):
    """流式请求输入，POST /stream 的请求体。继承 UserInput，增加 stream_tokens 选项。"""

    stream_tokens: bool = Field(
        description="是否逐 token 流式返回。true=返回每个 token；false=只返回完整消息。",
        default=True,
    )


# =============================================================================
# 消息相关（Agent 响应、对话历史）
# =============================================================================


class ToolCall(TypedDict):
    """工具调用信息，嵌在 ChatMessage.tool_calls 里。"""

    name: str
    """工具名称（如 "Weather"、"calculator"）"""
    args: dict[str, Any]
    """工具参数（如 {"city": "Tokyo"}）"""
    id: str | None
    """工具调用 ID，用于匹配后续的 ToolMessage 响应"""
    type: NotRequired[Literal["tool_call"]]


class ChatMessage(BaseModel):
    """聊天消息，是服务返回给客户端的核心数据结构。
    
    type 类型：human（用户）、ai（AI 响应）、tool（工具结果）、custom（自定义）
    """

    type: Literal["human", "ai", "tool", "custom"] = Field(
        description="消息角色/类型",
        examples=["human", "ai", "tool", "custom"],
    )
    content: str = Field(
        description="消息内容（AI 调用工具时可能为空字符串）",
        examples=["Hello, world!"],
    )
    tool_calls: list[ToolCall] = Field(
        description="AI 请求的工具调用列表（仅 type=ai 时可能有值）",
        default=[],
    )
    tool_call_id: str | None = Field(
        description="此消息响应的工具调用 ID（仅 type=tool 时有值）",
        default=None,
        examples=["call_Jja7J89XsjrOLA5r!MEOW!SL"],
    )
    run_id: str | None = Field(
        description="LangSmith run ID，用于提交反馈时关联",
        default=None,
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    response_metadata: dict[str, Any] = Field(
        description="响应元数据（如 token 计数、模型信息等）",
        default={},
    )
    custom_data: dict[str, Any] = Field(
        description="自定义数据（type=custom 时使用，如后台任务状态）",
        default={},
    )

    def pretty_repr(self) -> str:
        """返回格式化的消息字符串，便于调试打印。"""
        base_title = self.type.title() + " Message"
        padded = " " + base_title + " "
        sep_len = (80 - len(padded)) // 2
        sep = "=" * sep_len
        second_sep = sep + "=" if len(padded) % 2 else sep
        title = f"{sep}{padded}{second_sep}"
        return f"{title}\n\n{self.content}"

    def pretty_print(self) -> None:
        """打印格式化的消息。"""
        print(self.pretty_repr())  # noqa: T201


# =============================================================================
# /feedback 端点相关
# =============================================================================


class Feedback(BaseModel):  # type: ignore[no-redef]
    """用户反馈，POST /feedback 的请求体。用于把用户评分记录到 LangSmith。"""

    run_id: str = Field(
        description="要反馈的 run ID（从 ChatMessage.run_id 获取）",
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )
    key: str = Field(
        description="反馈类型标识（如 'human-feedback-stars'）",
        examples=["human-feedback-stars"],
    )
    score: float = Field(
        description="评分（0-1 之间，如 5 星评分中的 4 星 = 0.8）",
        examples=[0.8],
    )
    kwargs: dict[str, Any] = Field(
        description="传给 LangSmith 的额外参数（如评论文本）",
        default={},
        examples=[{"comment": "In-line human feedback"}],
    )


class FeedbackResponse(BaseModel):
    """反馈响应，POST /feedback 返回。"""
    status: Literal["success"] = "success"


# =============================================================================
# /history 端点相关
# =============================================================================


class ChatHistoryInput(BaseModel):
    """对话历史查询输入，POST /history 的请求体。"""

    thread_id: str = Field(
        description="要查询的线程 ID",
        examples=["847c6285-8fc9-4560-a83f-4e6285809254"],
    )


class ChatHistory(BaseModel):
    """对话历史，POST /history 返回。"""
    messages: list[ChatMessage]
