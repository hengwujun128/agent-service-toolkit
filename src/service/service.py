"""
FastAPI 服务层：把 LangGraph Agent 暴露成 HTTP API。

主要职责：
- 定义 `/info`、`/invoke`、`/stream`、`/history`、`/feedback`、`/health` 等端点
- 统一做鉴权、Tracing、SSE 流式输出封装
- 在 lifespan 生命周期里初始化数据库 Checkpointer（短期记忆）和 Store（长期记忆），并挂到每个 Agent 上
"""

import inspect  # 这里用来动态检查 AIMessage 的 __init__ 签名
import json
import logging
import warnings
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated, Any
from uuid import UUID, uuid4

# Use UUID v7 for LangSmith run_id (required by LangSmith)
try:
    from langsmith import uuid7
except ImportError:
    # Fallback to uuid4 if langsmith is not available
    from uuid import uuid4 as uuid7

from fastapi import APIRouter, Depends, FastAPI, HTTPException, status
from fastapi.responses import StreamingResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer  # Header 里的 Bearer Token 校验
from langchain_core._api import LangChainBetaWarning
from langchain_core.messages import (
    AIMessage,  # 完整 AI 消息
    AIMessageChunk,  # 流式输出的增量消息
    AnyMessage,
    HumanMessage,
    ToolMessage,
)
from langchain_core.runnables import RunnableConfig
from langfuse import Langfuse  # type: ignore[import-untyped]
from langfuse.langchain import (
    CallbackHandler,  # type: ignore[import-untyped]
)

from langgraph.types import Command, Interrupt
from langsmith import Client as LangsmithClient

from agents import (
    DEFAULT_AGENT,  # 默认的 Agent 名称（字符串）
    AgentGraph,  # 运行时的 Agent 图类型（StateGraph 或 Pregel）
    get_agent,
    get_all_agent_info,
    load_agent,
)
from core import settings
from memory import initialize_database, initialize_store
from schema import (
    ChatHistory,
    ChatHistoryInput,
    ChatMessage,
    Feedback,
    FeedbackResponse,
    ServiceMetadata,
    StreamInput,
    UserInput,
)
from service.utils import (  # 一些服务层与 LangChain/LangGraph 之间的转换工具
    convert_message_content_to_string,
    langchain_to_chat_message,
    remove_tool_calls,
)

# 忽略 LangChain Beta 相关的警告，避免在日志里刷屏
warnings.filterwarnings("ignore", category=LangChainBetaWarning)
# Suppress UUID v7 warning from pydantic v1 (used internally by LangChain)
# This warning appears because pydantic v1 doesn't natively support UUID v7,
# but langsmith.uuid7() returns a valid UUID that works correctly with LangSmith
warnings.filterwarnings(
    "ignore",
    message=".*LangSmith now uses UUID v7.*",
)
logger = logging.getLogger(__name__)  # 当前模块的 logger，供整份文件使用


def custom_generate_unique_id(route: APIRoute) -> str:
    """
    为每个路由生成 OpenAPI operation_id。

    默认情况下 FastAPI 会根据路径/方法生成比较长的 ID，这里直接用 route.name，
    方便前端生成客户端 SDK（例如 TypeScript 客户端）时得到更“干净”的函数名。
    """
    return route.name


def verify_bearer(
    http_auth: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(HTTPBearer(description="Please provide AUTH_SECRET api key.", auto_error=False)),
    ],
) -> None:
    # 如果没有配置 AUTH_SECRET，说明不启用鉴权，直接放行
    if not settings.AUTH_SECRET:
        return
    auth_secret = settings.AUTH_SECRET.get_secret_value()
    # HTTP Header 中没有 Bearer Token，或者 Token 不匹配，直接 401
    if not http_auth or http_auth.credentials != auth_secret:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    FastAPI 应用的生命周期管理。

    在应用启动时做几件关键的初始化工作：
    - 初始化数据库 Checkpointer（线程级/对话级记忆）
    - 初始化 Store（用户级/长期记忆）
    - 异步加载所有 Agent（包括 MCP 这类需要异步初始化的 Agent）
    - 把 checkpointer / store 挂到每个 Agent 上
    """
    try:
        # Initialize both checkpointer (for short-term memory) and store (for long-term memory)
        async with initialize_database() as saver, initialize_store() as store:
            # Set up both components（如果底层实现需要建表/建索引，这里统一调用 setup）
            if hasattr(saver, "setup"):  # ignore: union-attr
                await saver.setup()
            # Only setup store for Postgres as InMemoryStore doesn't need setup
            if hasattr(store, "setup"):  # ignore: union-attr
                await store.setup()

            # Configure agents with both memory components and async loading
            agents = get_all_agent_info()
            for a in agents:
                try:
                    # 异步加载 Agent（某些 Agent 是 LazyLoading 的，需要在这里真正初始化）
                    await load_agent(a.key)
                    logger.info(f"Agent loaded: {a.key}")
                except Exception as e:
                    logger.error(f"Failed to load agent {a.key}: {e}")
                    # Continue with other agents rather than failing startup

                agent = get_agent(a.key)
                # 设置 checkpointer：按 thread_id 维度保存对话历史（短期记忆）
                agent.checkpointer = saver
                # 设置 store：按 user_id 维度保存跨会话信息（长期记忆）
                agent.store = store
            yield
    except Exception as e:
        logger.error(f"Error during database/store/agents initialization: {e}")
        raise


app = FastAPI(
    lifespan=lifespan,  # 注册上面的生命周期管理函数
    generate_unique_id_function=custom_generate_unique_id,  # 自定义 OpenAPI operation_id
)
# 所有挂在 router 上的路由，都会自动应用 verify_bearer 这个依赖做鉴权
router = APIRouter(dependencies=[Depends(verify_bearer)])


@router.get("/info")
async def info() -> ServiceMetadata:
    models = list(settings.AVAILABLE_MODELS)
    models.sort()
    # 返回当前服务支持的 Agent 列表和模型列表，供前端初始化界面使用
    return ServiceMetadata(
        agents=get_all_agent_info(),
        models=models,
        default_agent=DEFAULT_AGENT,
        default_model=settings.DEFAULT_MODEL,
    )


async def _handle_input(user_input: UserInput, agent: AgentGraph) -> tuple[dict[str, Any], UUID]:
    """
    统一处理用户输入，生成调用 Agent 所需的 kwargs 和 run_id。

    主要工作：
    - 确定 thread_id / user_id（如果没传就自动生成 UUID）
    - 组装 LangGraph RunnableConfig（configurable + run_id + callbacks）
    - 检查当前线程是否有未完成的 interrupt，决定是 resume 还是新 HumanMessage
    """
    run_id = uuid7()  # LangSmith 要求使用 UUID v7 作为 run_id
    thread_id = user_input.thread_id or str(uuid4())  # 没传就创建一个新的对话线程
    user_id = user_input.user_id or str(uuid4())  # 没传就创建一个匿名用户 ID

    # 传给 LangGraph 的 config.configurable，用于：
    # - 关联 Checkpointer（按 thread_id 保存对话）
    # - 关联 Store（按 user_id 保存长期记忆）
    configurable = {"thread_id": thread_id, "user_id": user_id}
    if user_input.model is not None:
        configurable["model"] = user_input.model

    callbacks: list[Any] = []
    if settings.LANGFUSE_TRACING:
        # Initialize Langfuse CallbackHandler for Langchain (tracing)
        langfuse_handler = CallbackHandler()

        callbacks.append(langfuse_handler)

    if user_input.agent_config:
        # Check for reserved keys (including 'model' even if not in configurable)
        # 这些 key 是服务层保留的配置字段，不能在 agent_config 里覆盖
        reserved_keys = {"thread_id", "user_id", "model"}
        if overlap := reserved_keys & user_input.agent_config.keys():
            raise HTTPException(
                status_code=422,
                detail=f"agent_config contains reserved keys: {overlap}",
            )
        configurable.update(user_input.agent_config)

    # LangGraph 的标准运行配置对象
    config = RunnableConfig(
        configurable=configurable,
        run_id=run_id,
        callbacks=callbacks,
    )

    # Check for interrupts that need to be resumed
    state = await agent.aget_state(config=config)
    interrupted_tasks = [
        task for task in state.tasks if hasattr(task, "interrupts") and task.interrupts
    ]

    input: Command | dict[str, Any]
    if interrupted_tasks:
        # 存在未完成的中断 → 本次用户输入被视为对 interrupt 的“继续回答”
        input = Command(resume=user_input.message)
    else:
        # 正常的新一轮对话，从 HumanMessage 开始
        input = {"messages": [HumanMessage(content=user_input.message)]}

    kwargs = {
        "input": input,
        "config": config,
    }

    return kwargs, run_id


@router.post("/{agent_id}/invoke", operation_id="invoke_with_agent_id")
@router.post("/invoke")
async def invoke(user_input: UserInput, agent_id: str = DEFAULT_AGENT) -> ChatMessage:
    """
    Invoke an agent with user input to retrieve a final response.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation. run_id kwarg
    is also attached to messages for recording feedback.
    Use user_id to persist and continue a conversation across multiple threads.
    """
    # NOTE: Currently this only returns the last message or interrupt.
    # In the case of an agent outputting multiple AIMessages (such as the background step
    # in interrupt-agent, or a tool step in research-assistant), it's omitted. Arguably,
    # you'd want to include it. You could update the API to return a list of ChatMessages
    # in that case.
    agent: AgentGraph = get_agent(agent_id)  # 根据 agent_id 取出对应的 Compiled 图
    kwargs, run_id = await _handle_input(user_input, agent)

    try:
        # ainvoke 返回一个事件列表，每个元素是 (event_type, payload)
        # 这里请求 "updates" + "values" 两种模式：中间更新和最终结果
        response_events: list[tuple[str, Any]] = await agent.ainvoke(
            **kwargs, stream_mode=["updates", "values"]
        )  # type: ignore
        response_type, response = response_events[-1]
        if response_type == "values":
            # Normal response, the agent completed successfully
            output = langchain_to_chat_message(response["messages"][-1])
        elif response_type == "updates" and "__interrupt__" in response:
            # The last thing to occur was an interrupt
            # Return the value of the first interrupt as an AIMessage
            output = langchain_to_chat_message(
                AIMessage(content=response["__interrupt__"][0].value)
            )
        else:
            raise ValueError(f"Unexpected response type: {response_type}")

        # 把 run_id 附在返回的 ChatMessage 上，前端可以用它做反馈（feedback）
        output.run_id = str(run_id)
        return output
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"An exception occurred: {e}")
        err_str = str(e).lower()
        if "403" in err_str and "unsupported_country_region_territory" in err_str:
            raise HTTPException(
                status_code=403,
                detail="LLM API 不支持当前地区访问。请更换模型（如 deepseek-chat、ollama）或使用代理。",
            )
        raise HTTPException(status_code=500, detail="Unexpected error")


async def message_generator(
    user_input: StreamInput, agent_id: str = DEFAULT_AGENT
) -> AsyncGenerator[str, None]:
    """
    核心的流式消息生成器，为 `/stream` SSE 端点提供数据。

    负责：
    - 调用 LangGraph 的 astream，订阅 updates/messages/custom 三种事件
    - 将 LangGraph 的消息格式转换为统一的 ChatMessage
    - 按 SSE 协议格式化成 `data: ...\\n\\n` 形式输出
    - 同时支持 message 粒度事件和 token 粒度事件
    """
    agent: AgentGraph = get_agent(agent_id)
    kwargs, run_id = await _handle_input(user_input, agent)

    try:
        # Process streamed events from the graph and yield messages over the SSE stream.
        async for stream_event in agent.astream(
            **kwargs, stream_mode=["updates", "messages", "custom"], subgraphs=True
        ):
            if not isinstance(stream_event, tuple):
                continue
            # Handle different stream event structures based on subgraphs
            if len(stream_event) == 3:
                # With subgraphs=True: (node_path, stream_mode, event)
                _, stream_mode, event = stream_event
            else:
                # Without subgraphs: (stream_mode, event)
                stream_mode, event = stream_event
            new_messages = []
            if stream_mode == "updates":
                for node, updates in event.items():
                    # A simple approach to handle agent interrupts.
                    # In a more sophisticated implementation, we could add
                    # some structured ChatMessage type to return the interrupt value.
                    if node == "__interrupt__":
                        interrupt: Interrupt
                        for interrupt in updates:
                            new_messages.append(AIMessage(content=interrupt.value))
                        continue
                    updates = updates or {}
                    update_messages = updates.get("messages", [])
                    # special cases for using langgraph-supervisor library
                    if "supervisor" in node or "sub-agent" in node:
                        # the only tools that come from the actual agent are the handoff and handback tools
                        if isinstance(update_messages[-1], ToolMessage):
                            if "sub-agent" in node and len(update_messages) > 1:
                                # If this is a sub-agent, we want to keep the last 2 messages - the handback tool, and it's result
                                update_messages = update_messages[-2:]
                            else:
                                # If this is a supervisor, we want to keep the last message only - the handoff result. The tool comes from the 'agent' node.
                                update_messages = [update_messages[-1]]
                        else:
                            update_messages = []
                    new_messages.extend(update_messages)

            if stream_mode == "custom":
                new_messages = [event]

            # LangGraph streaming may emit tuples: (field_name, field_value)
            # e.g. ('content', <str>), ('tool_calls', [ToolCall,...]), ('additional_kwargs', {...}), etc.
            # We accumulate only supported fields into `parts` and skip unsupported metadata.
            # More info at: https://langchain-ai.github.io/langgraph/cloud/how-tos/stream_messages/
            processed_messages = []
            current_message: dict[str, Any] = {}
            for message in new_messages:
                if isinstance(message, tuple):
                    key, value = message
                    # Store parts in temporary dict
                    current_message[key] = value
                else:
                    # Add complete message if we have one in progress
                    if current_message:
                        processed_messages.append(_create_ai_message(current_message))
                        current_message = {}
                    processed_messages.append(message)

            # Add any remaining message parts
            if current_message:
                processed_messages.append(_create_ai_message(current_message))

            for message in processed_messages:
                try:
                    chat_message = langchain_to_chat_message(message)
                    chat_message.run_id = str(run_id)
                except Exception as e:
                    logger.error(f"Error parsing message: {e}")
                    yield f"data: {json.dumps({'type': 'error', 'content': 'Unexpected error'})}\n\n"
                    continue
                # LangGraph 会把用户输入也作为 stream 事件重新发一次，这里直接丢弃，避免前端重复显示
                if chat_message.type == "human" and chat_message.content == user_input.message:
                    continue
                yield f"data: {json.dumps({'type': 'message', 'content': chat_message.model_dump()})}\n\n"

            if stream_mode == "messages":
                if not user_input.stream_tokens:
                    continue
                msg, metadata = event
                if "skip_stream" in metadata.get("tags", []):
                    continue
                # astream("messages") 会让一些非 LLM 节点也发消息（例如工具节点），这里简单过滤掉
                if not isinstance(msg, AIMessageChunk):
                    continue
                content = remove_tool_calls(msg.content)
                if content:
                    # Empty content in the context of OpenAI usually means
                    # that the model is asking for a tool to be invoked.
                    # So we only print non-empty content.
                    yield f"data: {json.dumps({'type': 'token', 'content': convert_message_content_to_string(content)})}\n\n"
    except Exception as e:
        logger.error(f"Error in message generator: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Internal server error'})}\n\n"
    finally:
        yield "data: [DONE]\n\n"


def _create_ai_message(parts: dict) -> AIMessage:
    sig = inspect.signature(AIMessage)
    valid_keys = set(sig.parameters)
    filtered = {k: v for k, v in parts.items() if k in valid_keys}
    return AIMessage(**filtered)


def _sse_response_example() -> dict[int | str, Any]:
    return {
        status.HTTP_200_OK: {
            "description": "Server Sent Event Response",
            "content": {
                "text/event-stream": {
                    "example": "data: {'type': 'token', 'content': 'Hello'}\n\ndata: {'type': 'token', 'content': ' World'}\n\ndata: [DONE]\n\n",
                    "schema": {"type": "string"},
                }
            },
        }
    }


@router.post(
    "/{agent_id}/stream",
    response_class=StreamingResponse,
    responses=_sse_response_example(),  # 在 OpenAPI 文档中展示 SSE 示例
    operation_id="stream_with_agent_id",
)
@router.post(
    "/stream",
    response_class=StreamingResponse,
    responses=_sse_response_example(),
)
async def stream(user_input: StreamInput, agent_id: str = DEFAULT_AGENT) -> StreamingResponse:
    """
    Stream an agent's response to a user input, including intermediate messages and tokens.

    If agent_id is not provided, the default agent will be used.
    Use thread_id to persist and continue a multi-turn conversation. run_id kwarg
    is also attached to all messages for recording feedback.
    Use user_id to persist and continue a conversation across multiple threads.

    Set `stream_tokens=false` to return intermediate messages but not token-by-token.
    """
    return StreamingResponse(
        message_generator(user_input, agent_id),
        media_type="text/event-stream",
    )


@router.post("/feedback")
async def feedback(feedback: Feedback) -> FeedbackResponse:
    """
    Record feedback for a run to LangSmith.

    This is a simple wrapper for the LangSmith create_feedback API, so the
    credentials can be stored and managed in the service rather than the client.
    See: https://api.smith.langchain.com/redoc#tag/feedback/operation/create_feedback_api_v1_feedback_post
    """
    # Check if LangSmith is configured
    if not settings.LANGCHAIN_API_KEY:
        logger.warning("LangSmith API key not configured. Feedback will not be recorded.")
        # Return success to avoid breaking the UI, but log the warning
        return FeedbackResponse()

    try:
        client = LangsmithClient()  # 使用 LangSmith 官方客户端上报反馈
        kwargs = feedback.kwargs or {}
        client.create_feedback(
            run_id=feedback.run_id,
            key=feedback.key,
            score=feedback.score,
            **kwargs,
        )
        logger.debug(f"Feedback recorded for run_id: {feedback.run_id}")
        return FeedbackResponse()
    except Exception as e:
        # 仅记录错误，不抛异常：即使 LangSmith 出问题，整个服务仍可正常使用
        logger.error(f"Failed to record feedback to LangSmith: {e}")
        # Return success to avoid breaking the UI
        return FeedbackResponse()


@router.post("/history")
async def history(input: ChatHistoryInput) -> ChatHistory:
    """
    Get chat history.
    """
    # TODO: Hard-coding DEFAULT_AGENT here is wonky
    agent: AgentGraph = get_agent(DEFAULT_AGENT)
    try:
        state_snapshot = await agent.aget_state(
            config=RunnableConfig(configurable={"thread_id": input.thread_id})
        )
        messages: list[AnyMessage] = state_snapshot.values["messages"]
        chat_messages: list[ChatMessage] = [langchain_to_chat_message(m) for m in messages]
        return ChatHistory(messages=chat_messages)
    except Exception as e:
        logger.error(f"An exception occurred: {e}")
        raise HTTPException(status_code=500, detail="Unexpected error")


@app.get("/health")
async def health_check():
    """Health check endpoint."""

    health_status = {"status": "ok"}

    if settings.LANGFUSE_TRACING:
        try:
            langfuse = Langfuse()
            health_status["langfuse"] = "connected" if langfuse.auth_check() else "disconnected"
        except Exception as e:
            logger.error(f"Langfuse connection error: {e}")
            health_status["langfuse"] = "disconnected"

    return health_status


app.include_router(router)  # 把上面定义的所有路由挂载到 FastAPI 应用上
