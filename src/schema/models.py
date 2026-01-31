"""
模型定义模块：定义项目支持的所有 LLM 厂商（Provider）和模型名（ModelName）。

本文件的作用：
1. 统一管理所有支持的模型，便于类型检查和自动补全
2. 在 settings.py 中根据配置的 API Key 决定启用哪些 Provider/模型
3. 在 llm.py 中根据模型名选择对应的 LangChain 客户端（ChatOpenAI、ChatAnthropic 等）
4. 在 API 请求中做参数校验（Pydantic 会校验 model 字段是否在 AllModelEnum 中）

新增模型的步骤：
1. 在对应厂商的 StrEnum 里加一个成员（如 DEEPSEEK_CHAT = "deepseek-chat"）
2. 在 core/llm.py 的 get_model() 里加对应的初始化逻辑
3. 在 core/settings.py 的 model_post_init() 里确保该厂商的 API Key 被正确检测
"""

from enum import StrEnum, auto
from typing import TypeAlias


# =============================================================================
# Provider（厂商）枚举
# =============================================================================
# 用于 settings.py 中判断"哪些厂商被启用"（根据是否配置了对应 API Key）。
# auto() 会自动生成值（"openai"、"openai_compatible" 等小写字符串）。
class Provider(StrEnum):
    OPENAI = auto()             # OpenAI 官方 API
    OPENAI_COMPATIBLE = auto()  # 兼容 OpenAI 协议的第三方（百炼、通义等）
    AZURE_OPENAI = auto()       # Azure 托管的 OpenAI
    DEEPSEEK = auto()           # DeepSeek
    ANTHROPIC = auto()          # Anthropic (Claude)
    GOOGLE = auto()             # Google AI Studio (Gemini)
    VERTEXAI = auto()           # Google Cloud Vertex AI
    GROQ = auto()               # Groq（高速推理）
    AWS = auto()                # AWS Bedrock
    OLLAMA = auto()             # 本地 Ollama
    OPENROUTER = auto()         # OpenRouter（聚合多厂商）
    FAKE = auto()               # 测试用假模型


# =============================================================================
# 各厂商的模型名枚举
# =============================================================================
# 每个枚举成员的 **值** 是发给该厂商 API 的实际 model 参数。
# 例如 DEEPSEEK_CHAT = "deepseek-chat"，请求时会用 model="deepseek-chat"。


class OpenAIModelName(StrEnum):
    """OpenAI 官方模型 https://platform.openai.com/docs/models"""

    GPT_5_NANO = "gpt-5-nano"   # 最小、最快、最便宜
    GPT_5_MINI = "gpt-5-mini"   # 中等
    GPT_5_1 = "gpt-5.1"         # 最强


class AzureOpenAIModelName(StrEnum):
    """Azure OpenAI 模型（需要在 Azure 控制台部署后使用）"""

    AZURE_GPT_4O = "azure-gpt-4o"
    AZURE_GPT_4O_MINI = "azure-gpt-4o-mini"


class DeepseekModelName(StrEnum):
    """DeepSeek 模型 https://api-docs.deepseek.com/quick_start/pricing"""

    DEEPSEEK_CHAT = "deepseek-chat"  # 通用对话模型


class AnthropicModelName(StrEnum):
    """Anthropic Claude 模型 https://docs.anthropic.com/en/docs/about-claude/models"""

    HAIKU_45 = "claude-haiku-4-5"    # 快速、低成本
    SONNET_45 = "claude-sonnet-4-5"  # 平衡性能与成本


class GoogleModelName(StrEnum):
    """Google AI Studio Gemini 模型 https://ai.google.dev/gemini-api/docs/models/gemini"""

    GEMINI_15_PRO = "gemini-1.5-pro"
    GEMINI_20_FLASH = "gemini-2.0-flash"
    GEMINI_20_FLASH_LITE = "gemini-2.0-flash-lite"
    GEMINI_25_FLASH = "gemini-2.5-flash"
    GEMINI_25_PRO = "gemini-2.5-pro"
    GEMINI_30_PRO = "gemini-3-pro-preview"


class VertexAIModelName(StrEnum):
    """Google Cloud Vertex AI 模型 https://cloud.google.com/vertex-ai/generative-ai/docs/models
    
    注意：部分模型名带 "models/" 前缀，这是 Vertex AI API 的要求。
    """

    GEMINI_15_PRO = "gemini-1.5-pro"
    GEMINI_20_FLASH = "gemini-2.0-flash"
    GEMINI_20_FLASH_LITE = "models/gemini-2.0-flash-lite"
    GEMINI_25_FLASH = "models/gemini-2.5-flash"
    GEMINI_25_PRO = "gemini-2.5-pro"
    GEMINI_30_PRO = "gemini-3-pro-preview"


class GroqModelName(StrEnum):
    """Groq 模型（超快推理） https://console.groq.com/docs/models"""

    LLAMA_31_8B = "llama-3.1-8b"   # Llama 3.1 8B
    LLAMA_33_70B = "llama-3.3-70b" # Llama 3.3 70B

    # LlamaGuard 用于内容安全检测，在 research_assistant 等 Agent 中做输入/输出审核
    LLAMA_GUARD_4_12B = "meta-llama/llama-guard-4-12b"


class AWSModelName(StrEnum):
    """AWS Bedrock 模型 https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html"""

    BEDROCK_HAIKU = "bedrock-3.5-haiku"
    BEDROCK_SONNET = "bedrock-3.5-sonnet"


class OllamaModelName(StrEnum):
    """Ollama 本地模型 https://ollama.com/search
    
    这里只定义一个通用占位符，实际模型名在 .env 的 OLLAMA_MODEL 中配置。
    """

    OLLAMA_GENERIC = "ollama"


class OpenRouterModelName(StrEnum):
    """OpenRouter 聚合平台 https://openrouter.ai/models
    
    OpenRouter 支持很多模型，这里只列了一个示例；可按需添加。
    """

    GEMINI_25_FLASH = "google/gemini-2.5-flash"


class OpenAICompatibleName(StrEnum):
    """兼容 OpenAI 协议的第三方服务（百炼、通义、自建等）
    
    使用时在 .env 中配置：
    - COMPATIBLE_BASE_URL：API 地址（如 https://dashscope.aliyuncs.com/compatible-mode/v1）
    - COMPATIBLE_MODEL：实际模型名（如 qwen-plus）
    - COMPATIBLE_API_KEY：API Key
    
    请求里选 model="openai-compatible" 时会用上述配置。
    """

    OPENAI_COMPATIBLE = "openai-compatible"


class FakeModelName(StrEnum):
    """测试用假模型，不调用任何 API，直接返回固定响应。
    
    启用方式：在 .env 中设置 USE_FAKE_MODEL=true
    """

    FAKE = "fake"


# =============================================================================
# AllModelEnum：所有模型的联合类型
# =============================================================================
# 用于 Pydantic 类型校验。API 请求中的 model 字段必须是这些枚举值之一。
# 例如 UserInput.model: AllModelEnum | None
AllModelEnum: TypeAlias = (
    OpenAIModelName
    | OpenAICompatibleName
    | AzureOpenAIModelName
    | DeepseekModelName
    | AnthropicModelName
    | GoogleModelName
    | VertexAIModelName
    | GroqModelName
    | AWSModelName
    | OllamaModelName
    | OpenRouterModelName
    | FakeModelName
)
