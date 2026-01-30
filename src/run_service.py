"""
启动 FastAPI 服务的入口脚本（python src/run_service.py）。

它主要负责：
- 加载 .env 环境变量
- 配置日志
- Windows 下设置兼容的事件循环策略
- 启动 uvicorn 运行 FastAPI 应用（service:app）
"""

import asyncio  # 事件循环相关（Windows 兼容性设置会用到）
import logging  # 配置日志
import sys  # 判断平台（Windows 需要特殊处理）

import uvicorn
from dotenv import load_dotenv

from core import settings

# 加载 .env 到当前进程环境变量（os.environ）。
#
# 说明：本项目的 `core/settings.py` 中 Settings 已配置 `env_file=find_dotenv()`，
# 因而 `settings = Settings()` 也会读取 .env。这里再调用一次 load_dotenv() 的价值在于：
# - 让不通过 Settings、而是直接读 os.environ 的第三方库也能拿到环境变量
# - 在不同运行方式/调试方式下更稳妥
load_dotenv()

if __name__ == "__main__":
    # 只在直接运行脚本时启动服务；被 import 时不会启动，避免副作用。
    root_logger = logging.getLogger()
    if root_logger.handlers:
        # 如果根 logger 已经配置过 handler，basicConfig() 会被忽略。
        # 这里打印警告，避免误以为 LOG_LEVEL 没生效。
        print(
            f"Warning: Root logger already has {len(root_logger.handlers)} handler(s) configured. "
            f"basicConfig() will be ignored. Current level: {logging.getLevelName(root_logger.level)}"
        )

    # 根据 settings.LOG_LEVEL 设置全局日志级别
    logging.basicConfig(level=settings.LOG_LEVEL.to_logging_level())
    # Set Compatible event loop policy on Windows Systems.
    # On Windows systems, the default ProactorEventLoop can cause issues with
    # certain async database drivers like psycopg (PostgreSQL driver).
    # The WindowsSelectorEventLoopPolicy provides better compatibility and prevents
    # "RuntimeError: Event loop is closed" errors when working with database connections.
    # This needs to be set before running the application server.
    # Refer to the documentation for more information.
    # https://www.psycopg.org/psycopg3/docs/advanced/async.html#asynchronous-operations
    if sys.platform == "win32":
        # Windows 下切换为更兼容的事件循环策略（避免某些异步 DB 驱动问题）。
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    # 启动 uvicorn：
    # - "service:app" 表示导入 `service` 模块里的 `app`（FastAPI 实例）
    # - host/port/reload 等参数来自 settings（可通过 .env 覆盖）
    uvicorn.run(
        "service:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.is_dev(),
        timeout_graceful_shutdown=settings.GRACEFUL_SHUTDOWN_TIMEOUT,
    )
