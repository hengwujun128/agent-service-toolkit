# 10 - 入门 RAG：从 create_chroma_db 到 rag_assistant

## 📚 学习目标

读完本文档后，你将能够：
- ✅ 理解 RAG（Retrieval-Augmented Generation）的核心原理
- ✅ 掌握向量数据库的基本概念（Embedding、Chunk、Retriever）
- ✅ 创建自己的 Chroma 向量数据库
- ✅ 配置和使用 RAG Assistant

## 🎯 5 分钟验证

完成以下步骤后，你应该能：
1. 创建一个包含自己文档的向量数据库
2. 通过 RAG Assistant 查询文档内容
3. 理解检索结果是如何被 LLM 使用的

## 📖 RAG 核心概念

### 什么是 RAG？

**RAG = Retrieval-Augmented Generation（检索增强生成）**

简单来说：**先搜索，后回答**。

```
用户问题 → 搜索相关文档 → 将文档作为上下文 → LLM 生成回答
```

### 为什么需要 RAG？

| 问题 | 纯 LLM 的局限 | RAG 的解决方案 |
|------|--------------|---------------|
| 知识过时 | LLM 训练数据有截止日期 | 实时检索最新文档 |
| 私有数据 | LLM 不知道你的公司文档 | 从私有数据库检索 |
| 幻觉问题 | LLM 可能编造信息 | 基于真实文档生成 |
| 引用来源 | LLM 难以提供准确来源 | 可以返回文档出处 |

### 前端类比

如果你熟悉前端，RAG 可以这样理解：

```
RAG ≈ 搜索引擎 + AI 摘要
     ↓
用户搜索 → Elasticsearch/Algolia 返回结果 → AI 总结搜索结果
```

## 📊 RAG 工作流程

### 两个阶段

```
┌─────────────────────────────────────────────────────────────────────┐
│  阶段 1: 索引（离线，一次性）                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ 原始文档  │ →  │  分块    │ →  │ Embedding │ →  │ 向量数据库 │      │
│  │ PDF/Word │    │ Chunking │    │ 向量化    │    │ ChromaDB │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
├─────────────────────────────────────────────────────────────────────┤
│  阶段 2: 检索（在线，每次请求）                                       │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐      │
│  │ 用户问题  │ →  │ Embedding │ →  │ 相似度搜索 │ →  │ 返回文档   │      │
│  │ "什么是" │    │ 向量化    │    │ 在向量库中 │    │ Top K 个  │      │
│  └──────────┘    └──────────┘    └──────────┘    └──────────┘      │
│                                                        │            │
│                                                        ▼            │
│                                                  ┌──────────┐      │
│                                                  │   LLM    │      │
│                                                  │ 生成回答  │      │
│                                                  └──────────┘      │
└─────────────────────────────────────────────────────────────────────┘
```

## 🔧 核心概念详解

### 1. Embedding（向量化）

**定义**：将文本转换为数字向量（数组），使得语义相似的文本在向量空间中距离更近。

**类比**：
- 想象每段文本是一个点
- 语义相似的点在空间中聚集在一起
- "猫" 和 "狗" 的向量比 "猫" 和 "汽车" 更接近

**在本项目中**：

```python
# scripts/create_chroma_db.py
from langchain_openai import OpenAIEmbeddings

embeddings = OpenAIEmbeddings(api_key=os.environ["OPENAI_API_KEY"])
# OpenAI 的 text-embedding-ada-002 模型
# 输入: "Hello world" → 输出: [0.1, -0.3, 0.5, ...] (1536 维向量)
```

### 2. Chunk（分块）

**定义**：将长文档分割成小块，每块独立索引和检索。

**为什么需要分块？**
- LLM 上下文窗口有限（如 4K/8K/128K tokens）
- 太长的文档难以精确匹配
- 小块更容易定位相关内容

**在本项目中**：

```python
# scripts/create_chroma_db.py
from langchain.text_splitter import RecursiveCharacterTextSplitter

text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=2000,    # 每块最大 2000 字符
    chunk_overlap=500   # 块之间重叠 500 字符（避免切断句子）
)
chunks = text_splitter.split_documents(document)
```

**分块策略选择**：

| 场景 | chunk_size | overlap | 说明 |
|------|------------|---------|------|
| 技术文档 | 1500-2000 | 200-300 | 代码块通常较短 |
| 法律/合同 | 2000-3000 | 500-800 | 条款之间有关联 |
| 对话记录 | 500-1000 | 100-200 | 每轮对话较短 |
| 长文章 | 2000-4000 | 500-1000 | 保持段落完整性 |

### 3. Vector Store（向量数据库）

**定义**：专门存储和检索向量的数据库，支持相似度搜索。

**常见向量数据库**：
- **ChromaDB**：本项目使用，轻量级，适合原型
- **Pinecone**：云托管，适合生产
- **Weaviate**：开源，功能丰富
- **Milvus**：开源，高性能

**在本项目中**：

```python
# scripts/create_chroma_db.py
from langchain_chroma import Chroma

chroma = Chroma(
    embedding_function=embeddings,
    persist_directory="./chroma_db"  # 本地持久化
)

# 添加文档
chroma.add_documents([chunk])
```

### 4. Retriever（检索器）

**定义**：从向量数据库中检索相关文档的接口。

**在本项目中**：

```python
# src/agents/tools.py
def load_chroma_db():
    embeddings = OpenAIEmbeddings()
    chroma_db = Chroma(
        persist_directory="./chroma_db",
        embedding_function=embeddings
    )
    retriever = chroma_db.as_retriever(
        search_kwargs={"k": 5}  # 返回最相似的 5 个文档
    )
    return retriever
```

## 🚀 实战：创建 RAG 系统

### 步骤 1：准备文档

```bash
# 创建数据目录
mkdir -p data

# 添加你的文档（支持 PDF、Word）
cp your_document.pdf data/
cp your_document.docx data/
```

### 步骤 2：创建向量数据库

```bash
# 确保 OPENAI_API_KEY 已设置
python scripts/create_chroma_db.py
```

**脚本执行过程**：

```python
# scripts/create_chroma_db.py 核心流程

def create_chroma_db(folder_path, db_name="./chroma_db", chunk_size=2000, overlap=500):
    # 1. 初始化 Embedding 模型
    embeddings = OpenAIEmbeddings(api_key=os.environ["OPENAI_API_KEY"])
    
    # 2. 初始化向量数据库
    chroma = Chroma(embedding_function=embeddings, persist_directory=db_name)
    
    # 3. 初始化分块器
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap
    )
    
    # 4. 遍历文件
    for filename in os.listdir(folder_path):
        # 加载文档
        if filename.endswith(".pdf"):
            loader = PyPDFLoader(file_path)
        elif filename.endswith(".docx"):
            loader = Docx2txtLoader(file_path)
        
        # 分块
        document = loader.load()
        chunks = text_splitter.split_documents(document)
        
        # 添加到向量库
        for chunk in chunks:
            chroma.add_documents([chunk])
    
    return chroma
```

### 步骤 3：配置 RAG Tool

```python
# src/agents/tools.py

def database_search_func(query: str) -> str:
    """Searches chroma_db for information in the company's handbook."""
    retriever = load_chroma_db()
    documents = retriever.invoke(query)
    context_str = format_contexts(documents)
    return context_str
```

### 步骤 4：测试检索

```bash
# 测试 RAG Assistant
curl -X POST http://0.0.0.0:8080/rag-assistant/invoke \
  -H "Content-Type: application/json" \
  -d '{"message": "公司的使命和愿景是什么？"}'
```

## 📊 RAG Assistant 代码分析

### 与 Research Assistant 的区别

| 方面 | Research Assistant | RAG Assistant |
|------|-------------------|---------------|
| 工具 | web_search, calculator | database_search |
| 数据来源 | 互联网 | 本地向量数据库 |
| 适用场景 | 通用问答 | 私有知识库问答 |

### 代码对比

```python
# research_assistant.py
tools = [web_search, calculator]
instructions = "You are a helpful research assistant..."

# rag_assistant.py
tools = [database_search]
instructions = """
    You are AcmeBot, a helpful virtual assistant designed to support employees
    by retrieving and answering questions based on AcmeTech's Employee Handbook.
    ...
    Only use information from the database. Do not use information from outside sources.
"""
```

### 执行流程

```
用户问题: "公司的请假政策是什么？"
    │
    ▼
┌─────────────────────┐
│ RAG Assistant 收到   │
│ 消息后调用 LLM       │
└─────────────────────┘
    │
    │ LLM 决定调用 database_search
    ▼
┌─────────────────────┐
│ database_search     │
│ 1. 将问题向量化      │
│ 2. 在 ChromaDB 搜索  │
│ 3. 返回相似文档      │
└─────────────────────┘
    │
    │ 返回: "根据公司政策第5章..."
    ▼
┌─────────────────────┐
│ LLM 基于检索结果     │
│ 生成用户友好的回答   │
└─────────────────────┘
    │
    ▼
"根据公司员工手册，请假政策如下：
 1. 年假：每年 15 天...
 2. 病假：需提供医生证明..."
```

## ⚠️ 常见问题与优化

### Q1: 检索结果不相关

**可能原因**：
- chunk_size 太大，包含太多无关内容
- chunk_size 太小，丢失上下文
- k 值太小，错过相关文档

**解决方案**：
```python
# 调整分块参数
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,  # 减小块大小
    chunk_overlap=300
)

# 增加返回文档数量
retriever = chroma_db.as_retriever(search_kwargs={"k": 10})
```

### Q2: 回答不准确或产生幻觉

**可能原因**：
- 检索结果质量不高
- Prompt 没有强调"只使用检索内容"

**解决方案**：
```python
instructions = """
    ...
    IMPORTANT: Only use information from the database search results.
    If the database doesn't contain relevant information, say "I don't have information about that."
    DO NOT make up or infer information not found in the search results.
"""
```

### Q3: 检索速度慢

**可能原因**：
- 数据库太大
- 没有使用索引

**解决方案**：
- 使用云托管向量数据库（Pinecone、Weaviate）
- 实现分层检索（先粗筛再精选）
- 添加元数据过滤

### Q4: 向量数据库路径错误

**症状**：`database_search` 工具报错找不到数据库

**解决方案**：
```python
# 确保路径一致
# scripts/create_chroma_db.py
chroma = Chroma(persist_directory="./chroma_db", ...)

# src/agents/tools.py
chroma_db = Chroma(persist_directory="./chroma_db", ...)
```

## 🔧 进阶优化

### 1. 混合检索（Hybrid Search）

结合关键词搜索和向量搜索：

```python
from langchain.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever

# 关键词检索器
bm25_retriever = BM25Retriever.from_documents(documents)
bm25_retriever.k = 5

# 向量检索器
vector_retriever = chroma_db.as_retriever(search_kwargs={"k": 5})

# 混合检索器
ensemble_retriever = EnsembleRetriever(
    retrievers=[bm25_retriever, vector_retriever],
    weights=[0.3, 0.7]  # 70% 向量，30% 关键词
)
```

### 2. 重排序（Reranking）

对检索结果进行二次排序：

```python
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor

compressor = LLMChainExtractor.from_llm(llm)
compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=retriever
)
```

### 3. 元数据过滤

添加元数据实现精确过滤：

```python
# 添加文档时包含元数据
chunk.metadata["department"] = "HR"
chunk.metadata["date"] = "2024-01"

# 检索时过滤
retriever = chroma_db.as_retriever(
    search_kwargs={
        "k": 5,
        "filter": {"department": "HR"}
    }
)
```

## 📝 下一步

- **文档 11**：学习 MCP 工具编排
- **文档 12**：学习多 Agent 协作
- 尝试集成其他向量数据库（Pinecone、Weaviate）

## 🔗 相关代码文件

- 向量库创建脚本：[`scripts/create_chroma_db.py`](../scripts/create_chroma_db.py)
- 检索工具定义：[`src/agents/tools.py`](../src/agents/tools.py)
- RAG Assistant：[`src/agents/rag_assistant.py`](../src/agents/rag_assistant.py)
- 官方设置指南：[`docs/RAG_Assistant.md`](RAG_Assistant.md)

## 🔗 外部资源

- [LangChain RAG 教程](https://python.langchain.com/docs/tutorials/rag/)
- [ChromaDB 文档](https://docs.trychroma.com/)
- [OpenAI Embeddings](https://platform.openai.com/docs/guides/embeddings)
