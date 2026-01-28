# LangSmith 配置指南

LangSmith 是 LangChain 提供的追踪和监控平台，可以用于记录 Agent 的运行轨迹和用户反馈。

## 📋 前置要求

1. 注册 LangSmith 账户：访问 [https://smith.langchain.com/](https://smith.langchain.com/)
2. 获取 API Key：在 LangSmith 控制台创建 API Key

## 🔧 配置步骤

### 步骤 1：获取 LangSmith API Key

1. 登录 [LangSmith](https://smith.langchain.com/)
2. 进入 **Settings** → **API Keys**
3. 点击 **Create API Key**
4. 复制生成的 API Key（格式类似：`ls-xxxxx-xxxxx-xxxxx`）

### 步骤 2：配置环境变量

在项目根目录的 `.env` 文件中添加：

```bash
# LangSmith 配置
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls-your-api-key-here
LANGCHAIN_PROJECT=agent-service-toolkit  # 可选：自定义项目名称
LANGCHAIN_ENDPOINT=https://api.smith.langchain.com  # 默认值，通常不需要修改
LANGSMITH_WORKSPACE_ID=your-workspace-id  # 可选：如果使用组织级 API Key，需要指定
```

**重要提示**：
- `LANGCHAIN_TRACING_V2=true`：启用 LangSmith 追踪
- `LANGCHAIN_API_KEY`：你的 LangSmith API Key
- `LANGCHAIN_PROJECT`：在 LangSmith 中显示的项目名称（可选）
- `LANGSMITH_WORKSPACE_ID`：工作空间 ID（仅在使用组织级 API Key 时需要）

### 步骤 3：重启服务

配置完成后，重启 FastAPI 服务：

```bash
# 如果服务正在运行，先停止（Ctrl+C）
# 然后重新启动
python src/run_service.py
```

### 步骤 4：验证配置

#### 方法 1：检查服务日志

启动服务后，查看日志中是否有 LangSmith 相关的错误。如果配置正确，应该没有认证错误。

#### 方法 2：测试反馈功能

1. 在 Streamlit UI 中与 Agent 对话
2. 对 AI 回复进行评分（点击星星）
3. 检查服务日志，应该看到：
   ```
   DEBUG: Feedback recorded for run_id: xxxxx
   ```

#### 方法 3：查看 LangSmith 控制台

1. 登录 [LangSmith](https://smith.langchain.com/)
2. 进入你的项目（`agent-service-toolkit` 或你设置的项目名）
3. 应该能看到：
   - **Runs**：Agent 的执行轨迹
   - **Feedback**：用户反馈记录

## 🎯 功能说明

### 追踪功能（Tracing）

当 `LANGCHAIN_TRACING_V2=true` 时，所有 Agent 的执行都会被记录到 LangSmith：

- **运行轨迹**：每个 Agent 调用的完整流程
- **工具调用**：所有工具的使用情况
- **LLM 调用**：模型请求和响应
- **性能指标**：延迟、token 使用等

### 反馈功能（Feedback）

用户可以通过 Streamlit UI 的星级评分功能提交反馈：

- **评分记录**：1-5 星评分
- **关联运行**：反馈会关联到对应的 `run_id`
- **分析统计**：在 LangSmith 中查看反馈统计

## ⚠️ 常见问题

### 问题 1：401 Unauthorized 错误

**错误信息**：
```
langsmith.utils.LangSmithAuthError: Authentication failed for /feedback
```

**原因**：
- API Key 未配置或配置错误
- API Key 已过期或被撤销

**解决方案**：
1. 检查 `.env` 文件中的 `LANGCHAIN_API_KEY` 是否正确
2. 确保没有多余的空格：`LANGCHAIN_API_KEY=ls-xxxxx`（不要写成 `LANGCHAIN_API_KEY = ls-xxxxx`）
3. 在 LangSmith 控制台重新生成 API Key

### 问题 2：反馈功能不工作，但没有报错

**原因**：
- `LANGCHAIN_API_KEY` 未配置，代码会静默失败（返回成功但不记录）

**解决方案**：
- 检查服务日志，应该看到警告：`LangSmith API key not configured. Feedback will not be recorded.`
- 按照上述步骤配置 API Key

### 问题 3：追踪数据没有出现在 LangSmith

**原因**：
- `LANGCHAIN_TRACING_V2` 未设置为 `true`
- 项目名称不匹配

**解决方案**：
1. 确保 `.env` 中有 `LANGCHAIN_TRACING_V2=true`
2. 检查 `LANGCHAIN_PROJECT` 是否与 LangSmith 中的项目名一致
3. 重启服务

### 问题 4：Workspace ID 错误（org-scoped API Key）

**错误信息**：
```
WARNING:langsmith.client:Failed to multipart ingest runs: langsmith.utils.LangSmithUserError: This API key is org-scoped and requires workspace specification. Please provide 'workspace_id' parameter, or set LANGSMITH_WORKSPACE_ID environment variable.
```

**原因**：
- 使用的是组织级别的 API Key（org-scoped），需要指定工作空间 ID
- 组织级 API Key 可以访问多个工作空间，因此需要明确指定使用哪个工作空间

**解决方案**：

1. **获取 Workspace ID**：
   - 登录 [LangSmith](https://smith.langchain.com/)
   - 在 URL 或设置页面中找到你的 Workspace ID
   - 通常格式类似：`xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`（UUID）

2. **配置环境变量**：
   在 `.env` 文件中添加：
   ```bash
   LANGSMITH_WORKSPACE_ID=your-workspace-id-here
   ```

3. **或者使用个人级 API Key**：
   - 如果不需要组织级权限，可以创建个人级 API Key
   - 个人级 API Key 不需要指定 workspace_id

### 问题 5：UUID v7 警告

**错误信息**：
```
UserWarning: LangSmith now uses UUID v7 for run and trace identifiers. This warning appears when passing custom IDs. Please use: from langsmith import uuid7
            id = uuid7()
Future versions will require UUID v7.
```

**原因**：
- LangSmith 现在要求使用 UUID v7 格式的 run_id
- 警告来自 LangChain 内部使用的 pydantic v1，它在验证 UUID 时检测到不是它认识的格式
- 虽然代码已使用 `uuid7()`，但 pydantic v1 不原生支持 UUID v7（只支持 v1, v3, v4, v5）

**解决方案**：
- ✅ **已修复**：
  1. 代码已更新为使用 `uuid7()` 生成 run_id（`src/service/service.py` 第 130 行）
  2. 添加了警告过滤器来抑制此警告（`src/service/service.py` 第 55-58 行）
- **重要**：需要**重启服务**才能生效
- 如果重启后仍有警告，可以安全忽略（不影响功能，只是 pydantic v1 的兼容性警告）

### 问题 6：403 Forbidden 错误

**错误信息**：
```
WARNING:langsmith.client:Failed to multipart ingest runs: langsmith.utils.LangSmithError: Failed to POST https://api.smith.langchain.com/runs/multipart in LangSmith API. HTTPError('403 Client Error: Forbidden for url: https://api.smith.langchain.com/runs/multipart', '{"error":"Forbidden"}\n')
```

**原因**：
- API Key 权限不足（可能是只读权限）
- Workspace ID 配置错误
- API Key 类型不匹配（个人级 vs 组织级）

**解决方案**：

1. **检查 API Key 权限**：
   - 登录 LangSmith 控制台
   - 进入 Settings → API Keys
   - 确保 API Key 有写入权限（Write access）

2. **检查 Workspace ID**：
   - 如果使用组织级 API Key，确保 `LANGSMITH_WORKSPACE_ID` 配置正确
   - 验证 Workspace ID 是否属于你的账户

3. **重新创建 API Key**：
   - 如果问题持续，尝试创建一个新的 API Key
   - 确保选择正确的权限级别（个人级或组织级）

4. **验证配置**：
   ```bash
   # 检查环境变量是否正确加载
   python -c "from core.settings import settings; print(f'API Key: {bool(settings.LANGCHAIN_API_KEY)}'); print(f'Workspace ID: {settings.LANGSMITH_WORKSPACE_ID}')"
   ```

## 🔗 相关资源

- [LangSmith 官方文档](https://docs.smith.langchain.com/)
- [LangSmith API 文档](https://api.smith.langchain.com/redoc)
- [LangChain 追踪文档](https://python.langchain.com/docs/langsmith)

## 📝 代码位置

- 反馈端点：`src/service/service.py` 第 374-391 行
- 配置定义：`src/core/settings.py` 第 110-115 行
- 追踪初始化：`src/service/service.py` 第 132-136 行
