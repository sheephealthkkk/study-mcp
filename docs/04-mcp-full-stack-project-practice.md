# 第四模块：MCP 全栈项目实战

> **学习周期**：7-9 天  
> **学习目标**：能从零设计并实现一个完整的 MCP 服务，涵盖 Tools、Resources、
> Prompts 三大原语，对接真实数据库和 API。掌握多业务场景的工具设计模式、
> 跨 Server 事务策略、性能基准测试和生产级部署方案。

---

## 目录

1. [一、是什么——全栈 MCP 项目的完整图景](#一是什么全栈-mcp-项目的完整图景)
2. [二、为什么需要——从 Demo 到生产的鸿沟](#二为什么需要从-demo-到生产的鸿沟)
3. [三、如何实现——全栈 MCP 项目实战](#三如何实现全栈-mcp-项目实战)
   - [3.10 不同业务领域的工具设计模式](#310-不同业务领域的工具设计模式)
   - [3.11 跨 Server 事务场景的设计策略](#311-跨-server-事务场景的设计策略)
   - [3.12 性能基准测试](#312-性能基准测试)
4. [四、底层原理——复合工具与多 Server 协作机制](#四底层原理复合工具与多-server-协作机制)
5. [五、企业级最佳实践](#五企业级最佳实践)
6. [六、常见面试题](#六常见面试题)

---

## 一、是什么——全栈 MCP 项目的完整图景

### 1.1 什么是"全栈 MCP 项目"

在模块三中，我们学会了写单个工具函数。但真实的企业场景远不止如此——你需要对接多种数据源，管理数十个工具，处理复杂的错误场景，还要确保 LLM 能高效地使用你提供的工具完成多步骤任务。

一个"全栈 MCP 项目"的完整图景：

```
┌─────────────────────────────────────────────────────────┐
│                    AI 应用层 (Host)                       │
│           Claude Desktop / VS Code / Cursor              │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP Protocol
┌──────────────────────▼──────────────────────────────────┐
│                 MCP Server 层                            │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Tools    │  │Resources │  │ Prompts  │              │
│  │ (15个)   │  │ (8个)    │  │ (5个)    │              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘              │
│       │              │              │                    │
│  ┌────▼──────────────▼──────────────▼─────┐              │
│  │         服务层 (Service Layer)          │              │
│  │  业务逻辑 · 权限校验 · 缓存 · 限流      │              │
│  └────┬──────────────┬──────────────┬─────┘              │
└───────┼──────────────┼──────────────┼────────────────────┘
        │              │              │
┌───────▼──────┐ ┌─────▼──────┐ ┌───▼──────────┐
│  PostgreSQL  │ │  REST API  │ │  File System  │
│  (业务数据)  │ │  (外部服务) │ │  (文档/日志)  │
└──────────────┘ └────────────┘ └───────────────┘
```

### 1.2 本项目实战目标

我们将构建一个**企业内部运维助手 MCP Server**，具备以下能力：

| 功能域 | 能力 | 原语类型 |
|--------|------|----------|
| 数据库查询 | 搜索员工、查询部门、统计人数 | Tool + Resource |
| API 集成 | 查询服务健康状态、触发部署 | Tool |
| 文件系统 | 读取日志、搜索配置文件 | Resource |
| 知识检索 | 搜索内部 Wiki 文档 | Tool |
| 提示词模板 | 故障排查、代码审查、周报生成 | Prompt |

---

## 二、为什么需要——从 Demo 到生产的鸿沟

### 2.1 Demo 和生产的距离

大多数 MCP 教程在 "写一个 get_weather 工具" 之后就结束了。但真实生产环境有截然不同的要求：

| 维度 | Demo 级别 | 生产级别 |
|------|-----------|----------|
| **工具数量** | 1-3 个 | 20-50+ 个 |
| **数据源** | 假数据 / return 字符串 | PostgreSQL, Redis, REST API, S3 |
| **错误处理** | print / 不处理 | 结构化错误码 + 可操作建议 |
| **调用效率** | 不关心 | N+1 问题是致命伤 |
| **安全性** | 无 | 最小权限、参数校验、审计日志 |
| **可观测性** | 无 | 日志、指标、链路追踪 |
| **部署方式** | 本地 stdio | Docker + K8s + Streamable HTTP |

### 2.2 核心痛点：N×M 之外还有 "N+1"

第一模块讲了 MCP 解决了 N×M 集成困境。但在实战中，还有另一个更隐蔽的问题——**工具调用的 N+1 问题**。

```
场景：用户问 "技术部有哪些人？他们都提交了哪些代码？"

┌─────────────────────────────────────────────────────┐
│  薄封装模式（Thin Wrapper）                          │
│                                                     │
│  LLM 调用 #1: get_department_id("技术部")            │
│  LLM 调用 #2: list_employees(dept_id=5)  → 20 人    │
│  LLM 调用 #3: get_commits(employee_id=1)             │
│  LLM 调用 #4: get_commits(employee_id=2)             │
│  ...                                                │
│  LLM 调用 #22: get_commits(employee_id=20)           │
│                                                     │
│  总计：22 次调用！耗时 30+ 秒，消耗大量 token         │
└─────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────┐
│  领域优化模式（Domain-Optimized Tool）               │
│                                                     │
│  LLM 调用 #1: get_department_overview("技术部")      │
│     返回：部门信息 + 成员列表 + 每个人的最近提交      │
│                                                     │
│  总计：1 次调用！耗时 <2 秒                            │
└─────────────────────────────────────────────────────┘
```

> 研究表明，采用简单 API 封装模式的 MCP Server，平均每完成一个任务所需的工具调用次数是领域优化方案的 **5.3 倍**。

**这不是 LLM 的错，而是工具设计的错。** LLM 只能使用你给它的工具。如果你的工具粒度太细，LLM 就不得不做大量的"来回调用"才能完成一个语义上完整的任务。

下面我从三个层面讲清楚：**N+1 问题是什么 → 为什么简单 API 封装会导致它 → 领域优化方案如何解决它**。

---

## 什么是“工具调用的 N+1 问题”？

“N+1”原本是数据库查询中的一个经典反模式：
- 你要查 100 个作者及其所有文章。
- 先执行 1 次查询获取 100 个作者（N=100）。
- 然后对 **每个作者** 执行 1 次查询获取其文章 → 额外 100 次查询。
- 总计 101 次查询，而不是 1 次连接查询。

**类比到 MCP 工具调用**：
- LLM 想完成一个用户任务（比如“分析公司过去三个月订单，找出利润最高的前三个产品，并生成报告”）。
- 如果提供的工具颗粒度非常细（例如 `get_order_list`、`get_order_detail`、`get_product_name`、`calculate_profit`…），LLM 就必须：
  1. 调用 `get_order_list` → 获得订单 ID 列表（假设 100 条）。
  2. 对每个订单 ID 调用 `get_order_detail`（100 次调用）。
  3. 对每个产品 ID 调用 `get_product_info`（可能又 100 次）。
  4. 再调用 `calculate_profit` 多次…
- 最终 **1 个用户意图 → 数百次工具调用**。其中第 1 次是“初始列表”，后续对每个条目逐一操作就是那“N 次”。

> **核心：N+1 问题的本质是“为了完成一个语义上完整的任务，不得不对每个细粒度元素分别发起工具调用”**。

---

## 为什么“简单 API 封装模式”容易产生 N+1？

很多 MCP Server 的开发者，第一反应是把现有的后端 API（REST、gRPC、数据库存储过程）直接暴露成 MCP Tools，每个 API 端点对应一个 Tool。

例如，有一个订单系统的 REST API：

```
GET /orders          → 返回订单列表（只含 id、时间、总金额）
GET /orders/{id}     → 返回单个订单的详细（包含产品列表）
GET /products/{id}   → 返回产品名称、成本价
POST /calculate-profit → 输入订单明细，返回利润
```

直接封装成 MCP Tools：

- `list_orders()`
- `get_order_detail(order_id)`
- `get_product(product_id)`
- `calculate_profit(order_lines)`

LLM 接到“分析利润前三的产品”任务时：

1. 调用 `list_orders` → 拿到 100 个订单 ID。
2. 对每个 ID 调用 `get_order_detail` → 拿到产品明细。
3. 对每个产品 ID 调用 `get_product` → 拿到成本价。
4. 再调用 `calculate_profit` 多次（或者自己算，但 LLM 数学不准，通常也要工具）。
5. 最后汇总排序。

LLM 并不知道这些底层 API 是“原子操作”，它只会按照工具签名去组合。因为工具粒度就是底层 API 的粒度，LLM 被迫做 **N+1 次往返**。

**为什么不是 LLM 的错？**  
LLM 只能用你给它定义的工具。如果你定义的工具只做“读一行”、“读一列”，它当然只能一行一行读。它没有能力把 100 个订单详情合并成一个请求，因为工具接口不支持。

---

## 领域优化方案如何解决 N+1？

领域优化方案（也叫“面向 LLM 的工具设计”）的核心原则是：**工具应该提供“任务级别的抽象”，而不是“API 级别的抽象”**。即：

> **一个工具应该能够一次性返回完成某个子任务所需的所有数据，而不是要求 LLM 多次调用拼凑。**

针对上面的例子，优化方案可以设计一个复合工具：

```
analyze_top_profit_products(
    start_date, 
    end_date, 
    top_n = 3
) -> 返回直接排序好的列表，每个元素含：产品名称、总利润、订单数
```

这个工具内部：
- 一次性查询数据库或调用多个内部 API。
- 完成聚合、排序、利润计算。
- 把最终结果（已经是前 N 个）返回给 LLM。

LLM **一次调用**就能拿到完整答案，不需要自己循环、排序、反复问细节。

**为什么能减少调用次数？**  
因为工具的设计者把“领域知识”（例如：分析利润需要订单明细、产品成本、计算公式、排序逻辑）封装在了工具内部，LLM 只需要表达意图（“分析前三利润”），而不是一步步编排原子操作。

## 总结

> **“工具调用的 N+1 问题”是指：由于 MCP 服务器的工具设计得过于细粒度（简单包装底层 API），LLM 不得不进行大量的来回调用（先获取列表，再对每个元素分别操作）才能完成一个完整任务。领域优化方案通过提供任务级的复合工具，将多次操作合并成一次，从而将平均调用次数降低 5 倍以上。这不是 LLM 的智能不足，而是工具接口设计缺陷。**

如果你正在开发 MCP Server，记住这条原则：**问自己“如果一个人类助手要完成这个任务，他需要几步操作？”然后把那几步操作封装成一个工具，而不是把数据库的每一个表都暴露成一个工具。**



---

## 三、如何实现——全栈 MCP 项目实战

### 3.1 项目架构设计

#### 3.1.1 分层架构

```
┌─────────────────────────────────────────────────┐
│              表示层 (Presentation Layer)          │
│  mcp.server.fastmcp.FastMCP                     │
│  @mcp.tool()  │  @mcp.resource()  │  @mcp.prompt()
├─────────────────────────────────────────────────┤
│              服务层 (Service Layer)               │
│  EmployeeService  │  DeploymentService           │
│  LogService       │  WikiService                │
│  业务逻辑 · 数据聚合 · 缓存 · 权限校验             │
├─────────────────────────────────────────────────┤
│              数据访问层 (Data Access Layer)        │
│  PostgresClient  │  ApiClient  │  FileManager    │
│  连接池管理 · 查询构造 · 参数化查询 · 限流          │
├─────────────────────────────────────────────────┤
│              基础设施层 (Infrastructure)            │
│  Config  │  Logger  │  Auth  │  Metrics         │
└─────────────────────────────────────────────────┘
```

#### 3.1.2 完整项目结构

```
ops-assistant-mcp/
├── pyproject.toml
├── .env.example
├── .env                          # 不提交到 Git
├── Dockerfile
├── docker-compose.yml
├── README.md
│
├── src/
│   └── ops_assistant/
│       ├── __init__.py
│       ├── server.py             # FastMCP 入口
│       │
│       ├── config/
│       │   ├── __init__.py
│       │   └── settings.py       # 配置中心
│       │
│       ├── tools/                # 工具层（表示层）
│       │   ├── __init__.py
│       │   ├── employee.py       # 员工相关工具
│       │   ├── deployment.py     # 部署相关工具
│       │   ├── log.py            # 日志分析工具
│       │   └── wiki.py           # Wiki 搜索工具
│       │
│       ├── resources/            # 资源层（表示层）
│       │   ├── __init__.py
│       │   ├── database.py       # 数据库资源
│       │   └── filesystem.py     # 文件系统资源
│       │
│       ├── prompts/              # 提示词层
│       │   ├── __init__.py
│       │   └── templates.py
│       │
│       ├── services/             # 服务层
│       │   ├── __init__.py
│       │   ├── employee.py
│       │   ├── deployment.py
│       │   ├── log.py
│       │   └── wiki.py
│       │
│       ├── data/                 # 数据访问层
│       │   ├── __init__.py
│       │   ├── postgres.py       # 数据库客户端
│       │   ├── api_client.py     # HTTP API 客户端
│       │   └── file_manager.py   # 文件系统管理
│       │
│       └── utils/                # 工具函数
│           ├── __init__.py
│           ├── errors.py         # 统一错误码
│           ├── logging.py        # 日志配置
│           └── cache.py          # 缓存工具
│
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_employee_tools.py
    ├── test_deployment_tools.py
    └── test_integration.py
```

### 3.2 配置管理

```python
# src/ops_assistant/config/settings.py
import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


@dataclass
class DatabaseSettings:
    """数据库连接配置"""
    host: str = "localhost"
    port: int = 5432
    name: str = "ops_db"
    user: str = "ops_user"
    password: str = ""  # 从环境变量读取，不设默认值

    @property
    def connection_string(self) -> str:
        return (
            f"postgresql+asyncpg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


@dataclass
class ApiSettings:
    """外部 API 配置"""
    deployment_api_url: str = "https://deploy.internal.example.com"
    health_check_url: str = "https://health.internal.example.com"
    api_key: str = ""
    request_timeout: int = 30
    max_retries: int = 3
    rate_limit_per_minute: int = 60


@dataclass
class FileSystemSettings:
    """文件系统配置"""
    allowed_paths: list[str] = field(default_factory=lambda: ["/var/log", "/etc/config"])
    max_file_size_mb: int = 50
    allowed_extensions: list[str] = field(default_factory=lambda: [
        ".log", ".txt", ".json", ".yaml", ".yml", ".conf", ".md"
    ])


@dataclass
class CacheSettings:
    """缓存配置"""
    resource_cache_ttl: int = 60       # 秒
    tool_result_cache_ttl: int = 30
    max_cache_entries: int = 1000


@dataclass
class AppSettings:
    """应用总配置"""
    server_name: str = "ops-assistant"
    server_version: str = "1.0.0"
    log_level: str = "INFO"
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    api: ApiSettings = field(default_factory=ApiSettings)
    filesystem: FileSystemSettings = field(default_factory=FileSystemSettings)
    cache: CacheSettings = field(default_factory=CacheSettings)


@lru_cache()
def get_settings() -> AppSettings:
    """从环境变量加载配置（单例模式）"""
    return AppSettings(
        server_name=os.getenv("MCP_SERVER_NAME", "ops-assistant"),
        server_version=os.getenv("MCP_SERVER_VERSION", "1.0.0"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        database=DatabaseSettings(
            host=os.getenv("DB_HOST", "localhost"),
            port=int(os.getenv("DB_PORT", "5432")),
            name=os.getenv("DB_NAME", "ops_db"),
            user=os.getenv("DB_USER", "ops_user"),
            password=os.getenv("DB_PASSWORD", ""),
        ),
        api=ApiSettings(
            deployment_api_url=os.getenv("DEPLOY_API_URL", ""),
            health_check_url=os.getenv("HEALTH_CHECK_URL", ""),
            api_key=os.getenv("API_KEY", ""),
        ),
        filesystem=FileSystemSettings(
            allowed_paths=os.getenv("ALLOWED_PATHS", "/var/log,/etc/config").split(","),
        ),
    )
```

```bash
# .env.example —— 环境变量模板，提交到 Git
# 复制为 .env 后填入真实值

# 数据库
DB_HOST=localhost
DB_PORT=5432
DB_NAME=ops_db
DB_USER=ops_user
DB_PASSWORD=<在此填入数据库密码>

# API
DEPLOY_API_URL=https://deploy.internal.example.com
HEALTH_CHECK_URL=https://health.internal.example.com
API_KEY=<在此填入 API Key>

# 文件系统
ALLOWED_PATHS=/var/log,/etc/config,/data/reports

# 日志
LOG_LEVEL=INFO
```

### 3.3 数据访问层

#### 3.3.1 PostgreSQL 客户端

```python
# src/ops_assistant/data/postgres.py
import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from ..config.settings import get_settings


class PostgresClient:
    """PostgreSQL 数据库客户端

    设计原则：
    1. 使用连接池而非单连接（支持并发工具调用）
    2. 所有查询必须参数化（防 SQL 注入）
    3. 读操作和写操作使用不同的连接池配置
    """

    def __init__(self):
        self._pool: asyncpg.Pool | None = None
        self._write_pool: asyncpg.Pool | None = None

    async def initialize(self):
        """初始化连接池（Server 启动时调用）"""
        settings = get_settings().database
        self._pool = await asyncpg.create_pool(
            settings.connection_string,
            min_size=2,
            max_size=10,
            command_timeout=10,  # 读查询超时短
            server_settings={"application_name": "ops-assistant-read"}
        )
        self._write_pool = await asyncpg.create_pool(
            settings.connection_string,
            min_size=1,
            max_size=3,          # 写连接少一些
            command_timeout=30,  # 写查询超时更长
            server_settings={"application_name": "ops-assistant-write"}
        )

    async def close(self):
        """关闭连接池（Server 关闭时调用）"""
        if self._pool:
            await self._pool.close()
        if self._write_pool:
            await self._write_pool.close()

    @property
    def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            raise RuntimeError("数据库连接池未初始化，请先调用 initialize()")
        return self._pool

    @property
    def write_pool(self) -> asyncpg.Pool:
        if self._write_pool is None:
            raise RuntimeError("数据库写连接池未初始化")
        return self._write_pool

    # ---- 安全的查询方法 ----

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """执行只读查询（使用参数化查询防 SQL 注入）"""
        _validate_read_query(query)
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> asyncpg.Record | None:
        """执行只读查询，返回单行"""
        _validate_read_query(query)
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        """执行只读查询，返回单个值（如 COUNT）"""
        _validate_read_query(query)
        async with self.pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args) -> str:
        """执行写操作"""
        _validate_write_query(query)
        async with self.write_pool.acquire() as conn:
            result = await conn.execute(query, *args)
            return result

    async def transaction(self):
        """返回事务上下文管理器"""
        conn = await self.write_pool.acquire()
        return conn.transaction()


# ---- SQL 安全校验 ----

FORBIDDEN_KEYWORDS = [
    "DROP", "TRUNCATE", "ALTER TABLE", "CREATE TABLE",
    "GRANT", "REVOKE", "COPY", "VACUUM"
]

def _validate_read_query(query: str):
    """确保查询是只读的"""
    q = query.strip().upper()
    if not q.startswith("SELECT") and not q.startswith("WITH") and not q.startswith("EXPLAIN"):
        raise ValueError(f"只读连接仅允许 SELECT/WITH/EXPLAIN 查询，收到: {query[:50]}")
    for keyword in FORBIDDEN_KEYWORDS:
        if keyword in q:
            raise ValueError(f"检测到禁止的关键字: {keyword}")


def _validate_write_query(query: str):
    """确保写查询不包含超危险操作"""
    q = query.strip().upper()
    for keyword in ["DROP TABLE", "DROP DATABASE", "TRUNCATE TABLE"]:
        if keyword in q:
            raise ValueError(f"检测到超危险关键字: {keyword}")


# 全局数据库客户端实例
_db_client: PostgresClient | None = None


async def get_db() -> PostgresClient:
    global _db_client
    if _db_client is None:
        _db_client = PostgresClient()
        await _db_client.initialize()
    return _db_client


async def close_db():
    global _db_client
    if _db_client:
        await _db_client.close()
        _db_client = None
```

#### 3.3.2 REST API 客户端

```python
# src/ops_assistant/data/api_client.py
import httpx
import time
from typing import Any
from dataclasses import dataclass
from collections import defaultdict
from ..config.settings import get_settings


class RateLimiter:
    """基于令牌桶的简单限流器

    确保不会超出外部 API 的频率限制，避免被拉黑。
    """

    def __init__(self, max_calls_per_minute: int):
        self.max_calls = max_calls_per_minute
        self._window_start = time.monotonic()
        self._call_count = 0

    async def acquire(self):
        now = time.monotonic()
        # 新时间窗口，重置计数
        if now - self._window_start >= 60:
            self._window_start = now
            self._call_count = 0

        self._call_count += 1
        if self._call_count > self.max_calls:
            # 超出限制，等待到下一个窗口
            wait_time = 60 - (now - self._window_start) + 0.1
            import asyncio
            await asyncio.sleep(wait_time)
            self._window_start = time.monotonic()
            self._call_count = 1


class ApiClient:
    """REST API 客户端

    设计原则：
    1. 自动附加认证头
    2. 请求重试（指数退避）
    3. 客户端级限流
    4. 统一错误处理
    """

    def __init__(self):
        settings = get_settings().api
        self._client: httpx.AsyncClient | None = None
        self._settings = settings
        self._rate_limiter = RateLimiter(settings.rate_limit_per_minute)

    async def initialize(self):
        self._client = httpx.AsyncClient(
            timeout=self._settings.request_timeout,
            headers={
                "Authorization": f"Bearer {self._settings.api_key}",
                "User-Agent": f"OpsAssistant/{get_settings().server_version}",
                "Content-Type": "application/json"
            },
            limits=httpx.Limits(
                max_connections=10,
                max_keepalive_connections=5
            )
        )

    async def close(self):
        if self._client:
            await self._client.aclose()

    async def get(self, path: str, params: dict = None) -> dict:
        """GET 请求，带重试和限流"""
        return await self._request_with_retry("GET", path, params=params)

    async def post(self, path: str, json_data: dict = None) -> dict:
        """POST 请求，带重试和限流"""
        return await self._request_with_retry("POST", path, json=json_data)

    async def _request_with_retry(
        self, method: str, path: str,
        params: dict = None, json: dict = None
    ) -> dict:
        """执行请求，带指数退避重试"""
        await self._rate_limiter.acquire()

        last_error = None
        for attempt in range(self._settings.max_retries):
            try:
                response = await self._client.request(
                    method, f"{self._settings.deployment_api_url}{path}",
                    params=params, json=json
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                # 4xx 错误不重试（客户端错误）
                if 400 <= e.response.status_code < 500:
                    raise ApiError(
                        status_code=e.response.status_code,
                        message=f"API 请求错误: {e.response.text}"
                    )
                last_error = e
            except httpx.TimeoutException as e:
                last_error = e

            # 指数退避：1s, 2s, 4s
            if attempt < self._settings.max_retries - 1:
                import asyncio
                await asyncio.sleep(2 ** attempt)

        raise ApiError(
            status_code=0,
            message=f"API 请求失败（已重试 {self._settings.max_retries} 次）: {last_error}"
        )


class ApiError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(message)


_api_client: ApiClient | None = None

async def get_api_client() -> ApiClient:
    global _api_client
    if _api_client is None:
        _api_client = ApiClient()
        await _api_client.initialize()
    return _api_client
```

#### 3.3.3 文件系统管理器

```python
# src/ops_assistant/data/file_manager.py
import os
import glob
import mimetypes
from pathlib import Path
from ..config.settings import get_settings


class FileManager:
    """文件系统管理器

    设计原则：
    1. 路径白名单——只能访问允许的目录
    2. 文件类型白名单——只能读取允许的扩展名
    3. 大小限制——防止读取超大文件撑爆 token
    4. 路径穿越防护——禁止 ../ 路径穿越攻击
    """

    def __init__(self):
        settings = get_settings().filesystem
        self._allowed_paths = [Path(p).resolve() for p in settings.allowed_paths]
        self._max_size = settings.max_file_size_mb * 1024 * 1024
        self._allowed_extensions = settings.allowed_extensions

    def _resolve_safe_path(self, file_path: str) -> Path:
        """安全解析路径——防止路径穿越"""
        # 转换为绝对路径并解析符号链接
        resolved = Path(file_path).resolve()

        # 检查是否在允许的目录中
        for allowed in self._allowed_paths:
            try:
                resolved.relative_to(allowed)
                break
            except ValueError:
                continue
        else:
            raise PermissionError(
                f"路径访问被拒绝: {file_path}。"
                f"允许的路径: {[str(p) for p in self._allowed_paths]}"
            )

        return resolved

    def search_files(self, pattern: str, directory: str = None) -> list[dict]:
        """搜索匹配模式的文件"""
        search_dir = Path(directory).resolve() if directory else self._allowed_paths[0]

        # 安全检查
        if directory:
            self._resolve_safe_path(directory)

        full_pattern = str(search_dir / pattern)
        results = []
        for file_path in glob.glob(full_pattern, recursive=True):
            p = Path(file_path)
            if p.is_file() and p.suffix in self._allowed_extensions:
                stat = p.stat()
                results.append({
                    "path": str(p),
                    "name": p.name,
                    "size": stat.st_size,
                    "size_display": self._format_size(stat.st_size),
                    "modified": stat.st_mtime
                })
        return results

    def read_file(self, file_path: str, max_lines: int = 500) -> str:
        """读取文件内容"""
        safe_path = self._resolve_safe_path(file_path)

        if not safe_path.exists():
            return f"[错误] 文件不存在: {file_path}"

        if not safe_path.is_file():
            return f"[错误] 路径不是文件: {file_path}"

        size = safe_path.stat().st_size
        if size > self._max_size:
            return (
                f"[警告] 文件过大 ({self._format_size(size)})，"
                f"仅返回前 {max_lines} 行。"
                f"如需完整内容，请使用分段读取。\n\n"
                + self._read_lines(safe_path, max_lines)
            )

        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def read_file_tail(self, file_path: str, lines: int = 100) -> str:
        """读取文件尾部（日志场景）"""
        safe_path = self._resolve_safe_path(file_path)
        if not safe_path.is_file():
            return f"[错误] 文件不存在: {file_path}"

        with open(safe_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
            return "".join(all_lines[-lines:])

    def _read_lines(self, path: Path, max_lines: int) -> str:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    lines.append(f"... (还有更多行未显示)")
                    break
                lines.append(line)
            return "".join(lines)

    @staticmethod
    def _format_size(size: int) -> str:
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


_file_manager: FileManager | None = None

def get_file_manager() -> FileManager:
    global _file_manager
    if _file_manager is None:
        _file_manager = FileManager()
    return _file_manager
```

### 3.4 服务层 — 业务逻辑 + 数据聚合

```python
# src/ops_assistant/services/employee.py
from typing import Optional
from ..data.postgres import get_db


class EmployeeService:
    """员工信息服务

    关键设计：提供"领域优化"的查询方法，而非"薄封装"的 SQL 代理。
    每个方法返回的是一个完整的语义单元，避免 LLM 做多次调用拼凑数据。
    """

    async def search_employees(
        self,
        query: str,
        search_by: str = "name",
        department: str = None,
        limit: int = 20
    ) -> list[dict]:
        """搜索员工 —— 一个方法完成搜索 + 结果格式化"""
        db = await get_db()

        if search_by == "name":
            rows = await db.fetch(
                """SELECT e.id, e.name, e.email, e.title,
                          d.name as department, e.status
                   FROM employees e
                   JOIN departments d ON e.dept_id = d.id
                   WHERE e.name ILIKE $1
                   LIMIT $2""",
                f"%{query}%", limit
            )
        elif search_by == "email":
            rows = await db.fetch(
                """SELECT e.id, e.name, e.email, e.title,
                          d.name as department, e.status
                   FROM employees e
                   JOIN departments d ON e.dept_id = d.id
                   WHERE e.email ILIKE $1
                   LIMIT $2""",
                f"%{query}%", limit
            )
        elif search_by == "department":
            rows = await db.fetch(
                """SELECT e.id, e.name, e.email, e.title,
                          d.name as department, e.status
                   FROM employees e
                   JOIN departments d ON e.dept_id = d.id
                   WHERE d.name ILIKE $1
                   ORDER BY e.name
                   LIMIT $2""",
                f"%{query}%", limit
            )
        else:
            raise ValueError(f"不支持的搜索维度: {search_by}")

        return [dict(row) for row in rows]

    async def get_department_overview(self, department_name: str) -> dict:
        """获取部门全景视图 —— 复合工具的核心示例

        这是"领域优化"的关键：一次查询返回部门的所有相关信息，
        包括成员列表、统计数据、最近的活跃情况。
        替代了传统的 N+1 次调用（查部门 → 查成员 → 逐个查提交）。
        """
        db = await get_db()

        # 1. 查部门基本信息
        dept = await db.fetchrow(
            """SELECT id, name, description, created_at
               FROM departments WHERE name ILIKE $1""",
            f"%{department_name}%"
        )
        if not dept:
            return {"error": f"未找到匹配的部门: {department_name}"}

        dept_id = dept["id"]

        # 2. 查成员列表（含最近活动）
        members = await db.fetch(
            """SELECT e.id, e.name, e.email, e.title, e.status,
                      COALESCE(
                        (SELECT COUNT(*) FROM commits c
                         WHERE c.author_id = e.id
                         AND c.created_at > NOW() - INTERVAL '7 days'),
                        0
                      ) as recent_commits,
                      COALESCE(
                        (SELECT MAX(c.created_at) FROM commits c
                         WHERE c.author_id = e.id),
                        NULL
                      ) as last_activity
               FROM employees e
               WHERE e.dept_id = $1
               ORDER BY e.name""",
            dept_id
        )

        # 3. 查部门统计
        stats = await db.fetchrow(
            """SELECT
                 COUNT(*) FILTER (WHERE status = 'active') as active_count,
                 COUNT(*) FILTER (WHERE status = 'inactive') as inactive_count,
                 COUNT(*) as total_count
               FROM employees WHERE dept_id = $1""",
            dept_id
        )

        return {
            "department": dict(dept),
            "members": [dict(m) for m in members],
            "stats": dict(stats),
            "_meta": {
                "query_time": "实时",
                "note": "recent_commits 统计的是近 7 天的提交数"
            }
        }
```

### 3.5 工具层 — 面向 LLM 的工具设计

```python
# src/ops_assistant/tools/employee.py
import json
from typing import Literal, Annotated
from mcp.server.fastmcp import FastMCP
from ..services.employee import EmployeeService
from ..utils.errors import (
    ToolError, ErrorCode,
    make_success_response, make_error_response
)

_employee_service = EmployeeService()


def register_employee_tools(mcp: FastMCP):
    """注册员工相关的所有工具"""

    # ============================================================
    # 工具 1：员工搜索（基础工具）
    # ============================================================
    @mcp.tool()
    async def search_employees(
        query: Annotated[str, "搜索关键词：可以是姓名、邮箱关键词或部门名称"],
        search_by: Annotated[
            Literal["name", "email", "department"],
            "指定搜索维度。name=按姓名搜索（支持模糊），email=按邮箱搜索，department=按部门搜索"
        ] = "name",
        limit: Annotated[int, "最大返回条数，默认20，上限50"] = 20
    ) -> str:
        """在员工数据库中搜索员工信息。

        支持按姓名、邮箱和部门三种维度进行模糊搜索。
        返回匹配员工的 ID、姓名、邮箱、职位、部门和在职状态。

        何时使用：
        - "帮我找一下张三" → 按姓名搜索
        - "技术部有哪些人" → 按部门搜索
        - "有没有 @example.com 邮箱的人" → 按邮箱搜索
        - "市场部有哪些在职员工" → 按部门搜索，然后在结果中筛选
        """
        try:
            results = await _employee_service.search_employees(
                query=query,
                search_by=search_by,
                limit=min(limit, 50)
            )
            if not results:
                return make_error_response(
                    ErrorCode.NOT_FOUND,
                    f"未找到匹配 '{query}' 的员工",
                    "建议：1) 尝试只搜姓氏 2) 用更短的关键词 3) 换一种搜索维度"
                )
            return make_success_response({
                "count": len(results),
                "employees": results
            })
        except Exception as e:
            return make_error_response(
                ErrorCode.INTERNAL,
                f"搜索失败: {str(e)}",
                "请稍后重试或联系管理员"
            )

    # ============================================================
    # 工具 2：部门全景视图（复合工具——核心优化）
    # ============================================================
    @mcp.tool()
    async def get_department_overview(
        department_name: Annotated[str, "部门名称，支持模糊匹配。如'技术部'、'市场'"]
    ) -> str:
        """获取部门的完整全景视图。

        一次性返回：部门基本信息 + 所有成员列表 + 每个成员的最近提交数
        + 部门统计（在职/离职人数）。

        这是一个复合工具，一次调用即可完成传统需要多次查询的信息聚合。
        当你需要了解一个部门的完整情况时，优先使用此工具而非逐个查询。

        何时使用：
        - "技术部的整体情况如何"
        - "帮我看看市场部有哪些人，最近活跃吗"
        - "产研部门的规模和工作情况"
        """
        try:
            overview = await _employee_service.get_department_overview(
                department_name
            )
            if "error" in overview:
                return make_error_response(
                    ErrorCode.NOT_FOUND,
                    overview["error"],
                    "建议：尝试不同的部门名称，如'技术'而非'技术部'"
                )
            return make_success_response(overview)
        except Exception as e:
            return make_error_response(
                ErrorCode.INTERNAL,
                f"查询失败: {str(e)}",
                "请稍后重试"
            )

    # ============================================================
    # 工具 3：部署状态查询
    # ============================================================
    @mcp.tool()
    async def check_service_health(
        service_name: Annotated[str, "服务名称，如 'api-gateway', 'user-service'"]
    ) -> str:
        """查询指定服务的健康状态。

        返回服务的运行状态、最近部署版本、CPU/内存使用率等信息。

        何时使用：
        - "api-gateway 服务正常吗"
        - "user-service 最新版本是多少"
        - "检查所有核心服务的状态"
        """
        try:
            from ..data.api_client import get_api_client, ApiError
            client = await get_api_client()
            data = await client.get(f"/v1/services/{service_name}/health")
            return make_success_response(data)
        except ApiError as e:
            return make_error_response(
                ErrorCode.EXTERNAL_SERVICE,
                f"健康检查失败 (HTTP {e.status_code}): {e.message}",
                f"建议：确认服务名 '{service_name}' 是否正确，或检查部署平台是否在线"
            )
```

### 3.6 统一错误处理

```python
# src/ops_assistant/utils/errors.py
from enum import Enum
from dataclasses import dataclass
import json


class ErrorCode(str, Enum):
    """统一的错误码枚举

    设计原则：
    1. 每个错误码对应一类明确的失败模式
    2. LLM 可以根据错误码决定下一步策略
    """
    INVALID_PARAM = "INVALID_PARAM"          # 参数错误 → 修正参数重试
    NOT_FOUND = "NOT_FOUND"                  # 未找到 → 换关键词或维度重试
    PERMISSION_DENIED = "PERMISSION_DENIED"  # 无权限 → 告知用户，不可重试
    EXTERNAL_SERVICE = "EXTERNAL_SERVICE"    # 外部服务故障 → 稍后重试
    RATE_LIMITED = "RATE_LIMITED"           # 被限流 → 等待后重试
    INTERNAL = "INTERNAL"                   # 内部错误 → 不可重试，通知管理员
    TIMEOUT = "TIMEOUT"                     # 超时 → 稍后重试或缩小查询范围


# 每个错误码对应的 LLM 决策建议
ERROR_RECOVERY_HINTS = {
    ErrorCode.INVALID_PARAM: "RETRY_WITH_FIX",
    ErrorCode.NOT_FOUND: "RETRY_WITH_DIFFERENT_INPUT",
    ErrorCode.PERMISSION_DENIED: "DO_NOT_RETRY_TELL_USER",
    ErrorCode.EXTERNAL_SERVICE: "RETRY_LATER",
    ErrorCode.RATE_LIMITED: "WAIT_AND_RETRY",
    ErrorCode.INTERNAL: "DO_NOT_RETRY_ESCALATE",
    ErrorCode.TIMEOUT: "RETRY_WITH_SMALLER_SCOPE",
}


def make_error_response(
    code: ErrorCode,
    message: str,
    suggestion: str = "",
    recovery: str = None
) -> str:
    """构造面向 LLM 的结构化错误响应

    关键设计：错误信息不仅告诉 LLM "失败了"，还告诉它：
    - 为什么失败（code + message）
    - 是否可以重试（recovery）
    - 如何重试（suggestion）
    """
    if recovery is None:
        recovery = ERROR_RECOVERY_HINTS.get(code, "DO_NOT_RETRY")

    return json.dumps({
        "success": False,
        "error": {
            "code": code.value,
            "message": message,
            "recovery": recovery,
            "suggestion": suggestion
        }
    }, ensure_ascii=False, indent=2)


def make_success_response(data: dict | list) -> str:
    """构造统一格式的成功响应"""
    return json.dumps({
        "success": True,
        "data": data
    }, ensure_ascii=False, indent=2, default=str)
```

### 3.7 主入口组装

```python
# src/ops_assistant/server.py
import sys
import asyncio
from mcp.server.fastmcp import FastMCP
from .config.settings import get_settings
from .tools.employee import register_employee_tools
from .tools.deployment import register_deployment_tools
from .tools.log import register_log_tools
from .tools.wiki import register_wiki_tools
from .resources.database import register_database_resources
from .resources.filesystem import register_filesystem_resources
from .prompts.templates import register_all_prompts
from .data.postgres import get_db, close_db
from .data.api_client import get_api_client, _api_client


def create_server() -> FastMCP:
    """创建完整配置的 MCP Server 实例"""
    settings = get_settings()

    mcp = FastMCP(
        name=settings.server_name,
    )

    # ---- 注册工具 ----
    register_employee_tools(mcp)
    register_deployment_tools(mcp)
    register_log_tools(mcp)
    register_wiki_tools(mcp)

    # ---- 注册资源 ----
    register_database_resources(mcp)
    register_filesystem_resources(mcp)

    # ---- 注册提示词模板 ----
    register_all_prompts(mcp)

    return mcp


async def on_startup():
    """Server 启动时的初始化逻辑"""
    print(f"[ops-assistant] 正在启动...", file=sys.stderr)
    await get_db()
    await get_api_client()
    print(f"[ops-assistant] 启动完成，所有连接就绪", file=sys.stderr)


async def on_shutdown():
    """Server 关闭时的清理逻辑"""
    print(f"[ops-assistant] 正在关闭...", file=sys.stderr)
    await close_db()
    if _api_client:
        await _api_client.close()
    print(f"[ops-assistant] 已关闭", file=sys.stderr)


# 创建全局 Server 实例
mcp = create_server()

if __name__ == "__main__":
    # 注册生命周期钩子
    import atexit
    asyncio.run(on_startup())
    atexit.register(lambda: asyncio.run(on_shutdown()))
    # 启动 Server
    mcp.run(transport="stdio")
```

### 3.8 提示词模板设计

```python
# src/ops_assistant/prompts/templates.py
from mcp.server.fastmcp import FastMCP
from mcp.types import Prompt, PromptArgument, PromptMessage, TextContent


def register_all_prompts(mcp: FastMCP):
    """注册所有提示词模板"""

    @mcp.list_prompts()
    async def list_prompts() -> list[Prompt]:
        return [
            Prompt(
                name="incident_investigation",
                description="系统故障排查：帮助运维人员系统地排查线上故障",
                arguments=[
                    PromptArgument(
                        name="service",
                        description="出现故障的服务名称",
                        required=True
                    ),
                    PromptArgument(
                        name="symptom",
                        description="观察到的故障现象（如：接口超时、错误率飙升、CPU 打满）",
                        required=True
                    ),
                ]
            ),
            Prompt(
                name="weekly_report",
                description="周报生成：基于部门活动数据自动生成周报",
                arguments=[
                    PromptArgument(
                        name="department",
                        description="部门名称",
                        required=True
                    ),
                ]
            ),
        ]

    @mcp.get_prompt()
    async def get_prompt(name: str, arguments: dict):
        if name == "incident_investigation":
            return {
                "messages": [
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=_incident_prompt(
                                arguments["service"],
                                arguments["symptom"]
                            )
                        )
                    )
                ]
            }
        elif name == "weekly_report":
            return {
                "messages": [
                    PromptMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=_weekly_report_prompt(arguments["department"])
                        )
                    )
                ]
            }


def _incident_prompt(service: str, symptom: str) -> str:
    return f"""你是一位资深的 SRE（站点可靠性工程师）。服务 **{service}** 出现了故障，症状是：**{symptom}**。

请按以下步骤系统化地排查问题：

**第一步：检查服务健康状态**
使用 check_service_health 工具查看 {service} 的当前状态。

**第二步：分析最近变更**
使用 search_logs 工具搜索 {service} 最近 30 分钟的错误日志。
关注：异常堆栈、超时记录、数据库连接错误。

**第三步：检查依赖服务**
确认 {service} 依赖的上游服务是否正常。

**第四步：检查资源使用**
查看 CPU、内存、磁盘是否正常。

**第五步：给出根因分析和修复建议**
综合以上信息，判断最可能的根因，并给出修复建议和回滚方案。

注意：
- 每一步的结果都要清楚地向用户汇报
- 如果某个步骤卡住了，先报告已知信息再做判断
- 优先考虑"先止损后排查"的原则"""


def _weekly_report_prompt(department: str) -> str:
    return f"""请为 **{department}** 生成本周的工作周报。

**数据来源：**
1. 使用 get_department_overview("{department}") 获取部门整体情况
2. 获取部门成员的 recent_commits 数据作为工作产出参考

**周报结构：**
1. 本周总体概况（1-2 句）
2. 重点工作产出（按成员列出关键成果）
3. 关键指标（提交数、部署次数）
4. 风险和问题
5. 下周计划建议

请基于实际数据撰写，不要编造信息。如果数据不足，请明确标注。"""
```

### 3.9 生产级部署

#### 3.9.1 多阶段 Docker 构建 + Secrets 管理

```dockerfile
# Dockerfile.prod —— 多阶段构建 + 非 root 运行
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

FROM python:3.12-slim AS runtime
RUN groupadd -r mcp && useradd -r -g mcp -d /app mcp
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY src/ src/
COPY prompts/ prompts/
USER mcp
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
EXPOSE 8000 9090
CMD ["python", "-c", "from ops_assistant.server import mcp; mcp.run(transport='streamable-http', host='0.0.0.0', port=8000)"]
```

#### 3.9.2 Docker Compose（生产配置 + Secrets + Fluentd 日志收集）

```yaml
# docker-compose.prod.yml
version: "3.8"
services:
  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.prod
    image: ops-assistant:${VERSION:-latest}
    environment:
      - DB_HOST=postgres
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD_FILE=/run/secrets/db_password
      - API_KEY_FILE=/run/secrets/api_key
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - LOG_FORMAT=json
      - PROMETHEUS_PORT=9090
    secrets: [db_password, api_key]
    ports: ["8000:8000", "9090:9090"]
    deploy:
      resources:
        limits: { memory: 512M, cpus: "1.0" }
        reservations: { memory: 256M, cpus: "0.5" }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s; timeout: 3s; retries: 3; start_period: 10s
    restart: unless-stopped
    logging:
      driver: "fluentd"
      options: { fluentd-address: localhost:24224, tag: mcp.server }

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets: [db_password]
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 5s; timeout: 3s; retries: 5

secrets:
  db_password: { file: ./secrets/db_password.txt }
  api_key: { file: ./secrets/api_key.txt }
volumes:
  pgdata:
```

#### 3.9.3 多环境配置 + Prometheus 指标 + 结构化日志

```
配置分层：config/{base,dev,staging,prod}.py  |  切换：export APP_ENV=prod
生产默认：JSON 日志 + DB_POOL_MIN=5, POOL_MAX=10 + 审计启用 + Fluentd 日志收集
```

```python
# ops_assistant/utils/metrics.py
from prometheus_client import Counter, Histogram, Gauge

tool_call_total = Counter("mcp_tool_call_total", "工具调用总次数", ["tool_name", "status"])
tool_call_duration = Histogram("mcp_tool_call_duration_seconds", "工具调用耗时", ["tool_name"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10])
db_pool_available = Gauge("mcp_db_pool_available", "连接池可用连接数")
```

```yaml
# prometheus/alerts.yml
groups:
  - name: mcp_alerts
    rules:
      - alert: HighErrorRate
        expr: rate(mcp_tool_call_total{status="error"}[5m]) / rate(mcp_tool_call_total[5m]) > 0.1
        for: 5m; labels: { severity: P1 }
      - alert: HighP99Latency
        expr: histogram_quantile(0.99, rate(mcp_tool_call_duration_seconds_bucket[5m])) > 5
        for: 5m; labels: { severity: P2 }
      - alert: PoolExhausted
        expr: mcp_db_pool_available < 1
        for: 2m; labels: { severity: P1 }
```

### 3.10 不同业务领域的工具设计模式

"运维助手"是单一场景。面试中可能要求你当场为电商/金融/办公场景设计工具列表。以下展示同一原则在不同约束下的展开。

#### 3.10.1 电商——高并发 + 库存一致性

```python
@mcp.tool()
async def place_order(user_id: str, items: list[dict], address_id: str) -> dict:
    """下单——内部编排：校验库存 → 锁定优惠券 → 创建订单。
    三步在单个工具内完成，LLM 的两次 tools/call 之间没有事务保证。"""
    ...

@mcp.tool()
async def search_products(query: str, category: str = None,
    sort_by: str = "relevance", page_size: int = 20) -> dict:
    """搜索——一次返回商品+价格+库存+评分+优惠（搜索是最高并发路径）"""
    ...
```

#### 3.10.2 金融——审计追踪 + 数据脱敏

```python
@mcp.tool()
@audit_log("COMPLIANCE_CHECK")     # 强制审计，Server 端保证
async def compliance_check(transaction_id: str) -> dict: ...

@mcp.tool()
async def assess_risk(customer_id: str, amount: float) -> dict:
    raw = await risk_engine.evaluate(customer_id, amount)
    return desensitize(raw, fields=["name", "id_number", "phone", "bank_account"])

@mcp.resource("fin://accounts/{id}/transactions")
async def get_transactions(account_id: str) -> str:
    """Resource 而非 Tool——只读+可缓存+支持订阅。风险评估是计算（Tool），交易记录是数据（Resource）"""
```

#### 3.10.3 办公——跨系统权限收敛

```python
@mcp.tool()
async def search_across_systems(query: str) -> dict:
    """跨系统搜索——Server 内部 asyncio.gather 并发请求各子系统。
    LLM 一次调用了解信息分布，无需感知多系统架构。"""
    tasks = [search_mail(query), search_docs(query), search_calendar(query)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return aggregate_results(query, results)
```

#### 3.10.4 三场景对比

| 维度 | 运维 | 电商 | 金融 | 办公 |
|------|------|------|------|------|
| 核心约束 | 数据源多样 | 高并发+一致性 | 审计+脱敏 | 跨系统权限 |
| 复合策略 | 聚合多数据源 | 事务内编排 | 审计内嵌 | 跨系统聚合 |
| Resource用法 | 日志/配置 | 商品详情(缓存) | 交易记录(只读) | 文档内容 |
| 安全要求 | 路径白名单 | 幂等Key防重 | 字段级脱敏 | OAuth代理 |

> **统一铁律**：一个工具 = 一个用户意图，而非一个 API 端点。

### 3.11 跨 Server 事务场景的设计策略

MCP 协议不提供分布式事务支持。核心原则：**不要让 LLM 成为分布式事务协调器**。

#### 3.11.1 策略一：避免跨 Server（首选——单工具内编排）

```python
@mcp.tool()
async def place_order(user_id, items, address_id):
    order = None
    try:
        order = await order_db.create(user_id, items, status="pending")
        result = await inventory_client.deduct(items)  # 内部 gRPC/HTTP
        if not result.success:
            await order_db.update(order.id, status="cancelled", reason=result.reason)
            return make_error("INSUFFICIENT_STOCK", result.reason, "RETRY_LATER")
        await order_db.update(order.id, status="confirmed")
        return make_success(order.to_dict())
    except Exception as e:
        if order: await order_db.update(order.id, status="cancelled")
        return make_error("ORDER_FAILED", str(e), "DO_NOT_RETRY")
```

#### 3.11.2 策略二：补偿事务（跨 2 个 Server 的兜底方案）

补偿四原则：①正向可撤销 ②补偿幂等 ③补偿不依赖外部故障资源 ④定时兜底（不 100% 依赖 LLM 执行补偿）。

```python
@mcp.tool()
async def create_order(user_id, items):          # 正向工具
    """创建 pending 订单——30 分钟未确认自动取消"""
    ...

@mcp.tool()
async def cancel_order(order_id, reason):         # 补偿工具——必须幂等
    order = await order_db.get(order_id)
    if order.status == "cancelled":
        return {"status": "already_cancelled"}    # 幂等响应
    await order_db.update(order_id, status="cancelled", reason=reason)
    return {"status": "cancelled"}

@mcp.tool()
async def expire_stale_orders():                  # 定时任务兜底
    expired = await order_db.expire_pending_orders()
    return {"expired_count": len(expired)}
```

#### 3.11.3 策略三：Saga 编排（3+ 个 Server）

```
Step 1: Order → create_order(pending)
Step 2: Inventory → deduct  (失败→Order cancel_order)
Step 3: Payment → charge    (失败→Inventory restore + Order cancel)
Step 4: 全部成功 → 三方 confirm

Saga 协调器内嵌在 place_order 工具中，LLM 始终只看到一次调用。
```

#### 3.11.4 决策树

```
跨 Server 调用必须？
  ├── NO → 策略一：单工具内编排（最优）
  └── YES → 2 个 Server → 策略二：补偿事务
            └── 3+ 个 → 策略三：Saga 编排
```

### 3.12 性能基准测试

面试追问："你的复合工具比薄封装快多少？有数据吗？"

#### 3.12.1 复合工具 vs 薄封装

```
场景：查询"技术部成员及其最近提交"

  成员数   薄封装调用次数   薄封装 mean    复合 mean    加速比
  ──────  ─────────────   ───────────    ────────    ──────
  10 人    12 次            380ms         45ms         8.4x [E]
  50 人    52 次           1,850ms        52ms        35.6x [E]
  200 人  202 次           7,400ms        65ms       113.8x [E]

  [E] stdio RTT ≈ 0.8ms/次, DB 查询 ≈ 15-30ms/次
  薄封装 = RTT×N + DB×N。复合 = RTT×1 + DB×1 (JOIN)。
  加速比随成员数线性增长，复合工具延迟几乎恒定。
```

#### 3.12.2 不同数据量查询延迟

```
  返回记录数   Mean    P99     建议
  ──────────  ──────  ──────   ──────────
  100         12ms    22ms    正常
  1,000       35ms    58ms    正常
  10,000     180ms   320ms   建议分页（瓶颈：JSON 序列化）
  100,000    850ms   1,500ms 必须分页/摘要
```

#### 3.12.3 连接池调优

```
并发 20 client:
  min=1,max=2  → mean 85ms, P99 420ms, 错误率 2.1%  [E]
  min=5,max=10 → mean 28ms, P99 85ms,  错误率 0.05% [E] ← 推荐
  推荐：pool_min = 并发数 × 0.3, pool_max = 并发数
```

#### 3.12.4 压测脚本

```python
import asyncio, time, statistics
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class ToolBenchmark:
    def __init__(self, cmd=["python", "-m", "ops_assistant.server"]):
        self.params = StdioServerParameters(command=cmd[0], args=cmd[1:])

    async def _session(self):
        r, w = await stdio_client(self.params).__aenter__()
        s = ClientSession(r, w); await s.initialize(); return s

    async def compare(self, dept, members, iters=50):
        s = await self._session()
        comp = []; thin = []
        for _ in range(iters):
            t0 = time.perf_counter()
            await s.call_tool("get_department_overview", {"department_name": dept})
            comp.append((time.perf_counter()-t0)*1000)
        for _ in range(iters):
            t0 = time.perf_counter(); s2 = await self._session()
            await s2.call_tool("get_department_id", {"name": dept})
            await s2.call_tool("list_employees", {"dept_id": 5})
            for i in range(members):
                await s2.call_tool("get_employee_commits", {"employee_id": i+1})
            thin.append((time.perf_counter()-t0)*1000)
        return {"speedup": statistics.mean(thin)/statistics.mean(comp)}

if __name__ == "__main__":
    async def main():
        b = ToolBenchmark()
        for n in [10, 50, 200]:
            r = await b.compare("技术部", n, 30)
            print(f"成员={n}: 加速比={r['speedup']:.1f}x")
    asyncio.run(main())
```

---

## 四、底层原理——复合工具与多 Server 协作机制

### 4.1 N+1 问题的数学分析

**问题根源：** LLM + 工具调用的执行模型是串行的——LLM 每次只能调用一个工具，拿到结果后再决定下一步。如果工具粒度按 "一个 API 端点 = 一个工具" 来设计，LLM 就不得不做大量的来回调用。

```
任务：了解一个部门（N 个成员）的概况

薄封装模式调用次数 = 1 (查部门) + N (逐个查成员) + N (逐个查提交)
                   = 2N + 1
                   ≈ 5.3N (经研究统计，还有额外的纠错/重试调用)

复合工具模式调用次数 = 1 (get_department_overview)

效率提升 = (2N + 1) / 1 ≈ 2N 倍
```

**为什么是 5.3 倍？** 研究发现，薄封装模式不仅有多余的独立调用，LLM 还需要额外的：
- 探索性调用（了解工具能力）
- 纠错性调用（参数填错了重试）
- 验证性调用（确认数据是否完整）

这些"隐形成本"使得实际调用次数比理论计算更高。

### 4.2 复合工具设计原则

```
薄封装（❌）                      领域优化（✅）
══════════════════              ══════════════════

get_user(id)                    get_department_overview(name)
list_users(dept_id)             └→ 部门信息 + 成员列表 + 统计
get_department(id)
get_user_commits(user_id)       search_employees(query, dept)
                                └→ 支持跨维度、分页、筛选
get_log_file(path)
read_lines(path, n)             analyze_recent_errors(service, mins)
                                └→ 自动找日志文件 + 过滤错误 + 统计
get_deploy_status(svc)          
get_deploy_history(svc)         get_service_health_full(service)
                                └→ 状态 + 最近部署 + 依赖状态
```

**设计复合工具的三步法：**

```
Step 1: 识别高频任务模式
  观察用户（或测试 LLM）最常执行的"任务链"是什么。
  例：查部门 → 查成员 → 查统计 → 生成报告

Step 2: 合并为语义化操作
  将 2-4 个连续的 API 调用合并为一个"语义化操作"。
  命名体现领域语义而非技术名词。

Step 3: 保留原子操作作为 fallback
  复合工具不替代原子操作，而是补充。
  LLM 可在标准场景用复合工具，特殊场景用原子工具。
```

### 4.3 多 Server 协作原理

```
┌──────────────────────────────────────────────────────────┐
│                      Host (Claude Desktop)                │
│                                                          │
│  ┌──────────────────────────────────────────────────┐   │
│  │              MCP Client Manager                   │   │
│  │                                                  │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐       │   │
│  │  │ Client 1 │  │ Client 2 │  │ Client 3 │       │   │
│  │  │(stdio)   │  │(stdio)   │  │(SSE)     │       │   │
│  │  └────┬─────┘  └────┬─────┘  └────┬─────┘       │   │
│  └───────┼─────────────┼─────────────┼─────────────┘   │
│          │             │             │                  │
└──────────┼─────────────┼─────────────┼──────────────────┘
           │             │             │
    ┌──────▼──────┐ ┌───▼──────┐ ┌───▼───────────┐
    │ Ops Server  │ │ DB Server│ │ Weather Server │
    │ (部署,日志) │ │ (员工,   │ │ (外部数据)     │
    │             │ │  部门)   │ │                │
    └─────────────┘ └──────────┘ └────────────────┘

关键隔离原则：
  - Ops Server 不能读取 DB Server 的数据
  - DB Server 不能触发 Ops Server 的部署
  - 每个 Server 只能看到自己的上下文
  - Host 负责跨 Server 的信息整合
```

**多 Server 配置：**

```json
{
    "mcpServers": {
        "ops-assistant": {
            "command": "python",
            "args": ["-m", "ops_assistant.server"],
            "transport": "stdio"
        },
        "database-explorer": {
            "command": "python",
            "args": ["-m", "db_explorer.server"],
            "transport": "stdio"
        },
        "weather-service": {
            "url": "https://weather-mcp.example.com/mcp",
            "transport": "sse"
        }
    }
}
```

**跨 Server 调用的 LLM 决策：**

```
用户: "技术部的员工最近活跃吗？部署情况如何？"

LLM 决策过程：

Step 1: 识别信息需求
  → 员工信息 → database-explorer Server
  → 部署状态 → ops-assistant Server

Step 2: 并行收集信息
  → 调用 database-explorer.get_department_overview("技术部")
  → 调用 ops-assistant.check_service_health("all")

Step 3: 整合结果
  → LLM 将两个 Server 的返回结果综合为统一的回答

关键点：LLM 做跨 Server 整合，而非 Server 之间互相调用。
这正是 MCP 的设计原则之一：Server 之间保持隔离。
```

---

## 五、企业级最佳实践

### 5.1 工具粒度选择决策矩阵

```
工具设计决策矩阵

┌──────────────────────────────────────────────────────┐
│                                                      │
│  这个操作是否经常和另一个操作连续使用？                │
│       │                                              │
│   YES ├──→ 考虑合并为复合工具                         │
│       │                                              │
│   NO  ├──→ 这个操作独立的语义是否完整？                │
│       │       │                                      │
│       │   YES ├──→ 做成独立工具                       │
│       │       │                                      │
│       │   NO  ├──→ 是否需要进一步拆分或重新抽象？       │
│                                                      │
├──────────────────────────────────────────────────────┤
│  经验法则：                                           │
│  - 一个工具 = 一个人类可理解的"任务"                  │
│  - 避免暴露底层 API 的 1:1 映射                       │
│  - 工具名应该是一个动词短语（get_weather ✅,            │
│    api_get_v1_weather_forecast ❌）                   │
└──────────────────────────────────────────────────────┘
```

### 5.2 面向 LLM 的错误消息模板

```python
# 每个错误响应都应该回答 LLM 的三个问题：
# 1. 出了什么问题？（错误类型 + 描述）
# 2. 我能做什么？（是否可重试）
# 3. 具体怎么做？（操作建议）

ERROR_TEMPLATES = {
    ErrorCode.NOT_FOUND: lambda resource, alternatives: {
        "code": "NOT_FOUND",
        "message": f"未找到: {resource}",
        "recovery": "RETRY_WITH_DIFFERENT_INPUT",
        "suggestion": f"请尝试: {alternatives}"
    },
    ErrorCode.TIMEOUT: lambda operation, scope: {
        "code": "TIMEOUT",
        "message": f"操作超时: {operation}",
        "recovery": "RETRY_WITH_SMALLER_SCOPE",
        "suggestion": f"建议缩小范围: {scope}"
    },
    ErrorCode.RATE_LIMITED: lambda retry_after: {
        "code": "RATE_LIMITED",
        "message": f"请求频率超限",
        "recovery": "WAIT_AND_RETRY",
        "suggestion": f"请在 {retry_after} 秒后重试"
    },
}
```

### 5.3 性能优化全景

| 优化层级 | 手段 | 效果 |
|----------|------|------|
| **工具设计层** | 复合工具减少调用次数 | 减少 N× 次 RPC |
| **数据访问层** | 连接池复用、查询优化 | 每次调用减少 50-200ms |
| **服务层** | 结果缓存（读多写少场景） | 缓存命中时 0 次 DB 查询 |
| **传输层** | Streamable HTTP 连接复用 | 减少 TCP 握手开销 |
| **LLM 层** | 工具描述精准 → 减少探索和纠错 | 减少 20-40% 的无效调用 |

### 5.4 安全检查清单

```
□ SQL 注入防护
  □ 所有数据库查询使用参数化查询（$1, $2）
  □ 从不拼接用户输入到 SQL 字符串
  □ 区分读写连接池

□ 命令注入防护
  □ 从不使用 os.system() 或 subprocess(shell=True)
  □ 文件路径做白名单校验

□ 文件系统安全
  □ 路径白名单（只能访问指定目录）
  □ 路径穿越防护（resolve + relative_to 检查）
  □ 文件类型白名单
  □ 文件大小上限

□ API 安全
  □ API Key 从环境变量读取，不硬编码
  □ 请求限流（保护外部 API 不被 LLM 打爆）
  □ 请求重试要有上限

□ 数据安全
  □ 不在工具返回结果中暴露数据库连接字符串
  □ 不在错误信息中暴露堆栈跟踪
  □ 日志中脱敏敏感字段（密码、token）

□ 认证与授权
  □ 生产环境使用 mTLS 或 API Key 认证
  □ 工具级别的权限控制（只读 vs 读写）
```

### 5.5 可观测性建议

```python
# 关键指标监控
METRICS = {
    "tool_call_total": Counter,        # 每个工具的调用总次数
    "tool_call_duration": Histogram,   # 每个工具的调用耗时分布
    "tool_call_errors": Counter,       # 每个工具的错误次数
    "db_query_duration": Histogram,    # 数据库查询耗时
    "api_call_duration": Histogram,    # 外部 API 调用耗时
    "resource_read_total": Counter,    # 资源读取次数
}

# 告警规则
ALERTS = {
    "tool_error_rate > 10%": "P2 告警",
    "tool_call_p99 > 5s": "P3 告警",
    "db_connection_pool_exhausted": "P1 告警",
}
```

---

## 六、常见面试题

### 项目架构

**Q1: 一个企业级 MCP Server 应该采用怎样的分层架构？每一层负责什么？**

<details>
<summary>参考答案</summary>

推荐四层架构：

| 层级 | 职责 | 示例 |
|------|------|------|
| **表示层** | 定义 Tools/Resources/Prompts 的 MCP 接口 | `@mcp.tool()` 装饰的函数 |
| **服务层** | 业务逻辑、数据聚合、权限校验、缓存 | `EmployeeService` |
| **数据访问层** | 数据库/API/文件系统的具体访问 | `PostgresClient`, `ApiClient` |
| **基础设施层** | 配置、日志、认证、监控 | `Config`, `Logger` |

核心原则：
- 表示层的工具函数只做参数校验和结果格式化，不写业务逻辑
- 数据访问层封装连接管理和查询细节，服务层不关心用的是 PostgreSQL 还是 MySQL
- 每层可以独立测试和替换

</details>

---

**Q2: 什么是 MCP 中的 N+1 问题？如何解决？**

<details>
<summary>参考答案</summary>

**N+1 问题**：当工具设计为"薄 API 封装"（一个 API 端点 = 一个工具）时，LLM 完成一个多步骤任务需要 N+1 次甚至更多次工具调用。

例如，查询"技术部的成员及其最近提交"，薄封装需要：
1. 查部门 ID
2. 查成员列表（1 次）
3. 逐个查每个成员的提交（N 次）
合计 2N+1 次调用。

**解决方案：复合工具（Composite Tool）**
将多次 API 调用合并为一个语义化操作：
- `get_department_overview(name)` 一次性返回部门信息 + 成员列表 + 每人最近提交数 + 统计

**设计方法：**
1. 识别高频任务链（观察哪些工具常被连续调用）
2. 合并为语义化操作（用领域语言命名）
3. 保留原子操作作为 fallback

**数据支撑**：研究显示薄封装模式的调用次数是领域优化的 5.3 倍。

</details>

---

**Q3: 面向 LLM 的错误响应应该如何设计？和普通 API 的错误响应有什么不同？**

<details>
<summary>参考答案</summary>

普通 API 的错误响应只要告诉**开发者**错误码和描述即可。但 MCP 工具的错误响应需要告诉**LLM**——LLM 需要根据错误信息决定下一步策略。

**错误响应应包含三个要素：**

```json
{
    "success": false,
    "error": {
        "code": "NOT_FOUND",
        "message": "未找到匹配的员工",
        "recovery": "RETRY_WITH_DIFFERENT_INPUT",
        "suggestion": "请尝试：1) 只搜姓氏 2) 用更短的关键词 3) 按邮箱搜索"
    }
}
```

- `code`：错误分类，让 LLM 理解失败类型
- `recovery`：告诉 LLM 是否可重试、如何重试
- `suggestion`：具体的可操作建议

**LLM 据此做出的决策：**
- `RETRY_WITH_FIX` → 修正参数后重新调用
- `DO_NOT_RETRY_TELL_USER` → 向用户说明错误原因
- `WAIT_AND_RETRY` → 等待后再试

</details>

---

### 数据源对接

**Q4: 在做数据库对接时，有哪些安全措施是必须实施的？**

<details>
<summary>参考答案</summary>

1. **参数化查询**：100% 使用参数化查询（`$1`, `$2`），绝不拼接 SQL 字符串
2. **读写分离**：读操作和写操作使用不同的连接池，读连接只允许 SELECT
3. **关键字黑名单**：拦截 DROP、TRUNCATE、ALTER TABLE 等危险操作
4. **最小权限数据库用户**：MCP Server 使用的数据库账号只授予必要的权限（如只读账号用于查询工具）
5. **查询结果限制**：强制添加 LIMIT，防止全表扫描返回百万行数据
6. **敏感字段脱敏**：在工具返回结果前，过滤掉密码哈希、密钥等敏感字段

</details>

---

**Q5: 如果 LLM 通过你的文件系统 Resource 请求 `/etc/passwd`，你如何防护？**

<details>
<summary>参考答案</summary>

多层防护策略：

```python
def _resolve_safe_path(self, file_path: str) -> Path:
    # 第 1 层：解析真实路径（消除符号链接和 ../
    resolved = Path(file_path).resolve()

    # 第 2 层：白名单校验——必须在允许的目录内
    for allowed in self._allowed_paths:
        try:
            resolved.relative_to(allowed)
            break
        except ValueError:
            continue
    else:
        raise PermissionError(f"路径被拒绝: {file_path}")

    # 第 3 层：文件类型白名单
    if resolved.suffix not in self._allowed_extensions:
        raise PermissionError(f"文件类型不允许: {resolved.suffix}")

    return resolved
```

关键措施：
1. `Path.resolve()` 消除所有 `../` 和符号链接
2. `relative_to()` 确保路径在允许的目录树下
3. 文件扩展名白名单（只允许 `.log`, `.txt`, `.json` 等）
4. 文件大小上限（防止读取超大文件导致 token 溢出）

</details>

---

### 多 Server 协作

**Q6: 一个 Host 可以连接多个 MCP Server 吗？Server 之间可以互相通信吗？**

<details>
<summary>参考答案</summary>

**可以连接多个 Server。** Host（如 Claude Desktop）支持同时连接多个 MCP Server，每个 Server 通过独立的 Client 实例进行通信。

**Server 之间不能（也不应该）互相通信。** 这是 MCP 的设计原则之一：

1. **安全隔离**：每个 Server 只能看到自己的上下文，不能窥视其他 Server 的数据
2. **权限边界**：不同 Server 有不同的权限级别（如只读 vs 读写）
3. **Host 负责整合**：跨 Server 的信息整合由 Host 中的 LLM 来完成

LLM 收到两个 Server 的结果后，在生成回复时进行自然语言层面的整合。这类似微服务架构中 API Gateway 负责聚合多个服务的响应。

</details>

---

### 设计理解

**Q7: "不要做薄 API 封装"是什么意思？请举例说明。**

<details>
<summary>参考答案</summary>

"薄 API 封装"是指将底层 API 端点 1:1 地映射为 MCP 工具，不做任何领域抽象。

**薄封装（不好的设计）：**
```python
# 把 REST API 端点直接翻译为工具
@mcp.tool()
def api_get_department(dept_id: int): ...     # GET /api/departments/{id}
@mcp.tool()
def api_list_employees(dept_id: int): ...     # GET /api/departments/{id}/employees
@mcp.tool()
def api_get_employee(user_id: int): ...       # GET /api/employees/{id}
@mcp.tool()
def api_get_commits(user_id: int): ...        # GET /api/employees/{id}/commits
```

**领域优化（好的设计）：**
```python
@mcp.tool()
def get_department_overview(dept_name: str): ...
    # 内部聚合了以上 4 个 API 调用
    # 返回 LLM 真正需要的"部门全景视图"
```

**核心认知**：LLM 需要的是**上下文信息**，不是**原始数据**。薄封装给的是原始 API 数据，让 LLM 自己去理解关系；领域优化直接给出 LLM 所需的完整上下文。

</details>

---

**Q8: 设计 MCP Server 时，工具粒度应该如何把握？**

<details>
<summary>参考答案</summary>

**核心原则：一个工具 = 一个人类可理解的"任务"。**

粒度判断标准：
1. **语义完整性**：一次调用能否完成一个有意义的用户意图？"查天气"是一个任务，"获取天气 API 的 JSON 响应"不是。
2. **独立使用频率**：这个操作是否经常被单独使用？高频独立操作应独立成工具。
3. **组合使用频率**：两个操作是否几乎总是一起使用？如果是，合并为复合工具。
4. **返回数据量**：单次返回的数据量是否在 LLM 的 comfortable zone（通常 2000-10000 tokens）？

**经验法则：**
- 15-40 个工具是最佳范围
- < 10 个：可能过于粗粒度，LLM 拿到的数据噪音太多
- > 50 个：可能过于细粒度，LLM 选择困难且 N+1 风险高

</details>

---

**Q9: 如果 LLM 调用 Server A 的 `create_order` 成功，但 Server B 的 `deduct_inventory` 失败，如何保证数据一致性？**

<details>
<summary>参考答案</summary>

MCP 协议不提供分布式事务支持。核心原则：**不要让 LLM 成为分布式事务协调器**。

三种策略按优先级递进：
1. **首选：避免跨 Server（单工具内编排）**——将两步合并为一个 `place_order` 工具，事务由 Server 代码保证。LLM 始终只调一个工具。这是成本最低、一致性最强的方案
2. **兜底：补偿事务（跨 2 个 Server）**——`create_order` 创建 pending 状态订单（30 分钟自动过期），`cancel_order` 作为补偿工具（必须幂等——多次取消返回相同结果）。加定时任务 `expire_stale_orders` 兜底，不 100% 依赖 LLM 执行补偿
3. **扩展：Saga（3+ 个 Server）**——每步独立 + 对应补偿 + 协调器内嵌在工具中。LLM 始终只看到一次调用和最终结果

</details>

---

**Q10: 为电商/金融/办公场景分别设计 MCP 工具列表，你的设计思路是什么？**

<details>
<summary>参考答案</summary>

三个场景遵循统一铁律（一个工具 = 一个用户意图），但约束条件不同导致工具设计展开方式不同：

- **电商（高并发 + 一致性）**：搜索工具一次返回全部决策信息（价格+库存+评分+优惠，避免 N+1）；`place_order` 内部编排事务。关注幂等 Key 防重。典型工具数 20-35
- **金融（审计 + 脱敏）**：每个写操作内嵌 `@audit_log`（Server 端保证，不与 LLM 耦合）；返回数据自动脱敏（姓名→张**）；只读数据用 Resource 暴露（可缓存）；合规检查用独立 Tool（审计调用记录）。典型工具数 25-40
- **办公（跨系统权限）**：`search_across_systems` 内部 `asyncio.gather` 并发请求各子系统；Server 做 OAuth 代理，LLM 不感知多系统认证。典型工具数 15-20

**加分点**：能主动对比 Resource vs Tool 的选择标准——计算（Tool）vs 数据（Resource）。

</details>

---

**Q11: 你的 MCP Server 的生产部署方案是什么样的？**

<details>
<summary>参考答案</summary>

五要素：Docker 多阶段构建（非 root 运行）、Docker Secrets 管理敏感信息（`*_FILE` 环境变量读取路径）、JSON 结构化日志 → Fluentd → ELK、Prometheus Counter/Histogram/Gauge + 告警规则（错误率>10%=P1，P99>5s=P2）、GitHub Actions CI/CD（PR 触发 lint+test+security，Tag 触发 build+push 到 ghcr.io）。推荐连接池 `pool_min=并发数×0.3, pool_max=并发数`。

</details>

---

## 附录

### 项目初始化脚本

```bash
#!/bin/bash
# init-mcp-project.sh —— 快速创建 MCP 项目骨架

PROJECT_NAME=$1
if [ -z "$PROJECT_NAME" ]; then
    echo "用法: ./init-mcp-project.sh <project-name>"
    exit 1
fi

mkdir -p "$PROJECT_NAME/src/$PROJECT_NAME"/{config,tools,resources,prompts,services,data,utils}
mkdir -p "$PROJECT_NAME/tests"

# 创建空的 __init__.py
find "$PROJECT_NAME" -type d -exec touch {}/__init__.py \;

# 创建 pyproject.toml
cat > "$PROJECT_NAME/pyproject.toml" << PYPROJECT
[project]
name = "$PROJECT_NAME"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = [
    "mcp>=1.3.0",
    "asyncpg>=0.29",
    "httpx>=0.27",
    "pydantic>=2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]
PYPROJECT

# 创建 .env.example
cat > "$PROJECT_NAME/.env.example" << ENVFILE
DB_HOST=localhost
DB_PORT=5432
DB_NAME=mcp_db
DB_USER=mcp_user
DB_PASSWORD=
API_KEY=
LOG_LEVEL=INFO
ENVFILE

# 创建 .gitignore
cat > "$PROJECT_NAME/.gitignore" << GITIGNORE
__pycache__/
*.pyc
.env
.venv/
mcp-env/
dist/
*.egg-info/
.pytest_cache/
GITIGNORE

echo "✅ MCP 项目 $PROJECT_NAME 创建完成"
echo "  cd $PROJECT_NAME"
echo "  python -m venv mcp-env && source mcp-env/bin/activate"
echo "  pip install -e '.[dev]'"
```

### 推荐阅读

- [MCP 官方最佳实践](https://modelcontextprotocol.io/docs/best-practices)
- [Building Production MCP Servers](https://modelcontextprotocol.io/docs/server-development/production)
- [asyncpg 文档](https://magicstack.github.io/asyncpg/current/)
- [HTTPX 文档](https://www.python-httpx.org/)
- [Saga 分布式事务模式](https://microservices.io/patterns/data/saga.html)

### GitHub Actions CI/CD 配置

```yaml
# .github/workflows/ci.yml
name: MCP Server CI/CD

on:
  push: { branches: [main, develop] }
  pull_request: { branches: [main] }
  release: { types: [published] }

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install ruff mypy
      - run: ruff check src/ tests/
      - run: mypy src/ --ignore-missing-imports

  test:
    needs: lint
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_DB: test, POSTGRES_USER: test, POSTGRES_PASSWORD: test }
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - run: pytest tests/ -v --cov=src --cov-report=xml
        env: { DB_HOST: localhost, DB_USER: test, DB_PASSWORD: test, DB_NAME: test }

  security:
    needs: lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pypa/gh-action-pip-audit@v1
      - run: pip install bandit && bandit -r src/ -f json -o bandit-report.json

  build-push:
    if: github.event_name == 'release'
    needs: [test, security]
    runs-on: ubuntu-latest
    permissions: { contents: read, packages: write }
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with: { registry: ghcr.io, username: ${{ github.actor }}, password: ${{ secrets.GITHUB_TOKEN }} }
      - uses: docker/metadata-action@v5
        id: meta
        with: { images: ghcr.io/${{ github.repository }}, tags: type=semver,pattern={{version}} }
      - uses: docker/build-push-action@v5
        with: { context: ., file: ./Dockerfile.prod, push: true, tags: ${{ steps.meta.outputs.tags }} }
```

CI/CD 流程：PR → Lint → Test (含 PostgreSQL) → Security Scan → 合并通过。Tag 发布额外触发 → Build + Push Docker 镜像。
