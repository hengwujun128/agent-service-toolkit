# src/client/__init__.py
# __init__.py 使目录成为包
# 可以在 __init__.py 中导入子模块，简化外部导入
# __all__ 定义 from package import * 时导入的内容
# 从 client.client 模块导入 AgentClient 和 AgentClientError 类


# 1. 导入子模块，简化外部导入
from client.client import AgentClient, AgentClientError

# 2. 定义 __all__，定义 from package import * 时导入的内容
__all__ = ["AgentClient", "AgentClientError"]


# 3. 包级别的初始化代码
print("Package initialized")


# 4. 定义包级别的变量
VERSION = "1.0.0"


# 5. 最佳实践：1. 标准库 ---> 2. 第三方库  ---> 3. 项目内模块