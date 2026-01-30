'''
Author: 张泽全 hengwujun128@gmail.com
Date: 2026-01-20 11:16:30
LastEditors: 张泽全 hengwujun128@gmail.com
LastEditTime: 2026-01-28 17:22:37
Description: agents/__init__.py
FilePath: /agent-service-toolkit/src/agents/__init__.py
'''

# 1. 导入子模块，简化外部导入
from agents.agents import (
    DEFAULT_AGENT,
    AgentGraph,
    AgentGraphLike,
    get_agent,
    get_all_agent_info,
    load_agent,
)

# 2. 定义 __all__，定义 from package import * 时导入的内容
__all__ = [
    "get_agent",
    "load_agent",
    "get_all_agent_info",
    "DEFAULT_AGENT",
    "AgentGraph",
    "AgentGraphLike",
]
