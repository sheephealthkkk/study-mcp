# 模块 3 改进内容

> 目标：★★★★☆ → ★★★★★  
> 五个任务：Go SDK 实战 / 健壮 Client / 错误处理中间件 / Mock 测试 / SDK 迁移与跨语言差异

---

## 任务 1：Go SDK 实战示例 + 面试应对（扩展 §1.1）

**修改位置**：现有 §1.1「SDK 全景图」末尾的社区 SDK 列表之后。将现有的 ASCII 社区 SDK 图替换为含 Go 实战代码的完整小节。

### 改写后内容（替换 §1.1 末尾的社区 SDK 部分）

**社区 SDK 生态**——官方 Python 和 TypeScript SDK 之外，社区维护了以下高质量实现：

| 语言 | 仓库 | 成熟度 | 特点 |
|------|------|--------|------|
| **Go** | `mark3labs/mcp-go` | 高（1k+ stars） | 标准 `net/http`，天然高并发，适合微服务 |
| **Kotlin** | `modelcontextprotocol/kotlin-sdk` | 中 | Kotlin 协程，Android 友好 |
| **C#** | `modelcontextprotocol/csharp-sdk` | 中 | .NET 生态，Azure 集成 |
| **Rust** | `modelcontextprotocol/rust-sdk` | 中 | 零成本抽象，适合性能敏感场景 |

其中 **Go SDK 值得重点关注**——大量企业后端使用 Go 技术栈，面试中可能被问及。

### Go SDK 最小可运行 Server 示例

```go
// main.go —— Go MCP Server 最小示例
// 依赖: go get github.com/mark3labs/mcp-go
package main

import (
    "context"
    "fmt"
    "github.com/mark3labs/mcp-go/mcp"
    "github.com/mark3labs/mcp-go/server"
)

func main() {
    // 1. 创建 Server
    s := server.NewMCPServer(
        "go-weather-server",
        "1.0.0",
        server.WithToolCapabilities(true),
    )

    // 2. 注册工具
    s.AddTool(
        mcp.NewTool("get_weather",
            mcp.WithDescription("获取指定城市的天气信息"),
            mcp.WithString("city",
                mcp.Required(),
                mcp.Description("城市名称，如'北京'"),
            ),
        ),
        func(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
            city := request.Params.Arguments["city"].(string)
            return mcp.NewToolResultText(
                fmt.Sprintf("%s 的天气：晴，22°C", city),
            ), nil
        },
    )

    // 3. 注册资源
    s.AddResource(
        mcp.NewResource("system://status", "系统状态",
            mcp.WithResourceDescription("当前系统的运行状态"),
        ),
        func(ctx context.Context, request mcp.ReadResourceRequest) ([]mcp.ResourceContents, error) {
            return []mcp.ResourceContents{
                mcp.TextResourceContents{
                    URI:      "system://status",
                    MIMEType: "application/json",
                    Text:     `{"status":"healthy","uptime":"72h"}`,
                },
            }, nil
        },
    )

    // 4. 以 stdio 模式启动
    if err := server.ServeStdio(s); err != nil {
        panic(err)
    }
}
```

### 面试追问："公司后端是 Go 技术栈，你会如何用 Go SDK 构建 MCP Server？有什么注意事项？"

<details>
<summary>应对要点</summary>

**回答框架**：

1. **选型**：Go 社区首选 `mark3labs/mcp-go`（Stars 最多、更新最活跃），备选 `thinkgt/mcp-go`。两者都实现了 Tools/Resources/Prompts 三种原语和 stdio 传输。

2. **注意事项**：
   - **类型安全与 JSON Schema 的手写成本**：Go 不像 Python FastMCP 那样能从类型注解自动推导 JSON Schema，参数定义需要手写 `mcp.WithString()`、`mcp.WithNumber()` 等 builder，容易遗漏 `Required()` 或 `Description()`。**建议**：对于有 10+ 个工具的 Server，编写一个代码生成工具从 Go struct tag 生成 Tool 定义
   - **Context 传递**：Go SDK 的 handler 接收 `context.Context`，这是做超时控制和取消传播的关键。务必在工具函数中检查 `ctx.Done()` 以支持 MCP 的 Cancelled 通知
   - **并发安全**：Go 的 goroutine 模型天然适合 MCP 的并发调用场景。但需注意 handler 中共享状态的并发安全——如果多个 tools/call 并发读写同一个 map，需要加 `sync.Mutex`
   - **部署**：Go 编译为单一二进制文件，`COPY` 到 Docker scratch 镜像即可，镜像体积 < 10MB，远小于 Python 的 100MB+

3. **对比 Python**：Go 的优势是部署简单（单二进制）+ 并发性能好，劣势是工具定义的样板代码更多。对于工具数量 < 10 的小型 Server，Python FastMCP 开发效率更高；对于需要高并发或微服务部署的大型 Server，Go 是更好的选择。

</details>

---

## 任务 2：构建健壮的 MCP Client（新增 §3.5.2）

**插入位置**：现有 §3.5「构建 MCP Client」之后（原文件约第 658 行之后），§3.6「TypeScript SDK 等价实现」之前。

### §3.5.2 构建健壮的 MCP Client

基础 Client 代码能跑通"happy path"，但生产环境需要处理以下四个维度。

#### 维度一：重连策略

```python
# robust_client.py —— 带自动重连的 MCP Client
import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class RobustMCPClient:
    """支持自动重连的 MCP Client

    重连策略：
    - 指数退避：初始 1s，每次翻倍，最大 30s
    - 最大重试：10 次（之后抛出异常）
    - 重连成功后自动重新 initialize + 恢复工具列表缓存
    """

    def __init__(
        self,
        server_params: StdioServerParameters,
        max_retries: int = 10,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ):
        self.server_params = server_params
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self._session: ClientSession | None = None
        self._tool_cache: list | None = None
        self._resource_cache: list | None = None
        self._read = None
        self._write = None

    async def connect(self):
        """建立连接，带自动重试"""
        for attempt in range(self.max_retries):
            try:
                self._read, self._write = await stdio_client(
                    self.server_params
                ).__aenter__()
                self._session = ClientSession(self._read, self._write)
                await self._session.initialize()
                # 恢复缓存
                await self._refresh_caches()
                logger.info(f"连接成功 (attempt {attempt + 1})")
                return
            except Exception as e:
                logger.warning(f"连接失败 (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    await asyncio.sleep(delay)
                else:
                    raise ConnectionError(
                        f"重连失败，已重试 {self.max_retries} 次"
                    ) from e

    async def _refresh_caches(self):
        """刷新工具和资源列表缓存"""
        if self._session:
            tools_result = await self._session.list_tools()
            self._tool_cache = tools_result.tools
            try:
                resources_result = await self._session.list_resources()
                self._resource_cache = resources_result.resources
            except Exception:
                self._resource_cache = []  # Server 可能不支持 Resources

    async def call_tool(self, name: str, arguments: dict) -> dict:
        """调用工具，失败时自动重连后重试一次"""
        for attempt in range(2):  # 最多试 2 次：正常 + 重连后重试
            try:
                result = await self._session.call_tool(name, arguments)
                return result
            except (ConnectionError, OSError) as e:
                if attempt == 0:
                    logger.warning(f"调用失败，尝试重连: {e}")
                    await self.connect()
                else:
                    raise

    async def close(self):
        if self._read and self._write:
            # 清理 stdio 资源
            pass
```

#### 维度二：超时处理

```python
import asyncio
from contextlib import asynccontextmanager
from enum import Enum

class TransportType(str, Enum):
    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"

# 各传输方式的推荐超时设置（秒）
RECOMMENDED_TIMEOUTS = {
    TransportType.STDIO: {
        "connect": 10,       # 进程启动超时
        "initialize": 5,     # 初始化协商超时
        "tool_call": 30,     # 工具调用总超时
        "idle": 300,         # 空闲连接保持时间
    },
    TransportType.SSE: {
        "connect": 15,       # HTTP 连接 + SSE 流建立
        "initialize": 10,
        "tool_call": 60,     # SSE 可能跨网络，放宽超时
        "idle": 600,
        "sse_reconnect": 5,  # SSE 流重连超时
    },
    TransportType.STREAMABLE_HTTP: {
        "connect": 10,
        "initialize": 10,
        "tool_call": 60,
        "idle": 300,
        "request_total": 30, # 单次 HTTP 请求总超时
    },
}


class TimeoutManager:
    """MCP Client 超时管理器"""

    def __init__(self, transport: TransportType):
        self.timeouts = RECOMMENDED_TIMEOUTS[transport]

    @asynccontextmanager
    async def with_timeout(self, operation: str):
        """为操作设置超时的上下文管理器"""
        timeout = self.timeouts.get(operation, 30)
        try:
            async with asyncio.timeout(timeout):
                yield
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"操作 '{operation}' 超时 ({timeout}s)。"
                f"传输方式: {self.timeouts}。"
                f"建议：如果是 tool_call 超时，检查工具执行逻辑；"
                f"如果是 connect 超时，检查 Server 是否正常启动。"
            )
```

**超时设置的原则**：

| 原则 | 说明 |
|------|------|
| **区分操作类型** | connect 和 tool_call 的超时应不同——连接超时短（快速失败），工具超时根据业务特征设置 |
| **远程 > 本地** | SSE/Streamable HTTP 的超时通常比 stdio 长 2-3 倍，因为网络延迟不确定 |
| **给 LLM 留余量** | tool_call 超时应明显小于 LLM 请求的总体超时，确保超时时 LLM 还能收到错误信息并做下一步决策 |
| **支持取消传播** | 超时触发后应通过 `notifications/cancelled` 通知 Server 取消正在执行的操作 |

#### 维度三：并发调用管理

```python
import asyncio
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class ConcurrencyConfig:
    max_concurrent_tools: int = 10     # 同一时刻最多并发工具调用数
    max_per_session: int = 5           # 单 session 最大并发
    tool_specific: dict[str, int] = None  # 特定工具的并发限制

    def __post_init__(self):
        if self.tool_specific is None:
            self.tool_specific = {}


class ConcurrencyManager:
    """MCP Client 并发调用管理器

    MCP Client 可以同时发起多个 tools/call——每个调用有独立的 id，
    JSON-RPC 的响应通过 id 匹配。但需要做好并发控制。
    """

    def __init__(self, config: ConcurrencyConfig = ConcurrencyConfig()):
        self.config = config
        self._global_semaphore = asyncio.Semaphore(config.max_concurrent_tools)
        self._tool_semaphores: dict[str, asyncio.Semaphore] = {}
        self._active_calls: dict[str, int] = defaultdict(int)

    async def acquire(self, tool_name: str):
        """获取调用许可"""
        # 全局并发限制
        await self._global_semaphore.acquire()
        # 工具级并发限制
        limit = self.config.tool_specific.get(tool_name, self.config.max_per_session)
        sem = self._tool_semaphores.setdefault(tool_name, asyncio.Semaphore(limit))
        await sem.acquire()
        self._active_calls[tool_name] += 1

    def release(self, tool_name: str):
        """释放调用许可"""
        self._active_calls[tool_name] -= 1
        self._global_semaphore.release()
        sem = self._tool_semaphores.get(tool_name)
        if sem:
            sem.release()

    @asynccontextmanager
    async def guard(self, tool_name: str):
        """并发控制的上下文管理器"""
        await self.acquire(tool_name)
        try:
            yield
        finally:
            self.release(tool_name)

    def get_active_count(self, tool_name: str = None) -> int:
        """获取当前正在执行的调用数"""
        if tool_name:
            return self._active_calls.get(tool_name, 0)
        return sum(self._active_calls.values())


# 使用示例
concurrency_mgr = ConcurrencyManager(ConcurrencyConfig(
    max_concurrent_tools=10,
    tool_specific={
        "deploy": 1,         # 部署操作串行执行
        "search_db": 20,     # 查询操作可以高并发
    }
))

async def call_tool_safe(session, tool_name: str, args: dict):
    async with concurrency_mgr.guard(tool_name):
        return await session.call_tool(tool_name, args)
```

> **关键认知**：MCP Client 是否支持并发调用取决于底层传输。stdio 传输的请求是串行处理的（单线程读 stdout），并发请求可能导致响应乱序。Streamable HTTP 天然支持并发（每个请求独立 HTTP 连接）。如果你需要并发调用能力，优先选择 Streamable HTTP 传输。

#### 维度四：Client 端缓存

```python
import time
import asyncio
from typing import Optional

class MCPClientCache:
    """MCP Client 端缓存

    缓存策略：
    - tools/list: 缓存直到收到 tools/list_changed 通知
    - resources/list: 缓存直到收到 resources/list_changed 通知
    - resources/read: 按 TTL 缓存（默认 60s），可通过订阅更新主动失效

    失效机制：
    1. 主动失效：收到 list_changed 通知 → 删除对应缓存，下次调用时重新拉取
    2. TTL 失效：超过 TTL 自动过期
    3. 手动失效：调用方显式调用 invalidate()
    """

    def __init__(self, resource_ttl: int = 60):
        self.resource_ttl = resource_ttl
        self._tools: Optional[list] = None
        self._tools_valid: bool = False
        self._resources: Optional[list] = None
        self._resources_valid: bool = False
        self._resource_content: dict[str, tuple[float, str]] = {}  # uri → (expiry, content)

    # ---- tools/list 缓存 ----
    def get_tools(self) -> list | None:
        return self._tools if self._tools_valid else None

    def set_tools(self, tools: list):
        self._tools = tools
        self._tools_valid = True

    def invalidate_tools(self):
        """收到 tools/list_changed 通知时调用"""
        self._tools_valid = False

    # ---- resources/list 缓存 ----
    def get_resources(self) -> list | None:
        return self._resources if self._resources_valid else None

    def set_resources(self, resources: list):
        self._resources = resources
        self._resources_valid = True

    def invalidate_resources(self):
        """收到 resources/list_changed 通知时调用"""
        self._resources_valid = False

    # ---- resources/read 缓存 (TTL-based) ----
    def get_resource_content(self, uri: str) -> str | None:
        entry = self._resource_content.get(uri)
        if entry:
            expiry, content = entry
            if time.monotonic() < expiry:
                return content
            del self._resource_content[uri]
        return None

    def set_resource_content(self, uri: str, content: str, ttl: int = None):
        self._resource_content[uri] = (
            time.monotonic() + (ttl or self.resource_ttl),
            content
        )

    def invalidate_resource_content(self, uri: str):
        """收到 resources/updated 通知时调用"""
        self._resource_content.pop(uri, None)


class CachedMCPClient:
    """带缓存的 MCP Client"""

    def __init__(self, session: ClientSession):
        self.session = session
        self.cache = MCPClientCache()

    async def list_tools(self, force_refresh: bool = False):
        if not force_refresh:
            cached = self.cache.get_tools()
            if cached is not None:
                return cached
        result = await self.session.list_tools()
        self.cache.set_tools(result.tools)
        return result.tools

    async def read_resource(self, uri: str):
        cached = self.cache.get_resource_content(uri)
        if cached is not None:
            return cached
        content, mime_type = await self.session.read_resource(uri)
        self.cache.set_resource_content(uri, content)
        return content

    async def handle_notification(self, notification: dict):
        """处理 Server 推送的通知，更新缓存"""
        method = notification.get("method", "")
        if method == "notifications/tools/list_changed":
            self.cache.invalidate_tools()
        elif method == "notifications/resources/list_changed":
            self.cache.invalidate_resources()
        elif method == "notifications/resources/updated":
            uri = notification.get("params", {}).get("uri", "")
            self.cache.invalidate_resource_content(uri)
```

**面试常见追问**："MCP Client 的 tools/list 应该缓存多久？何时刷新？"

**回答要点**：
- `tools/list` **没有 TTL**——它不是时间敏感的，而是事件敏感的。缓存应该一直有效，直到收到 Server 的 `notifications/tools/list_changed` 通知才失效
- 但要注意：Server 声明 `tools.listChanged: false`（或不声明）时，Client 可以在整个 session 期间永久缓存
- 如果 Server 声明了 `tools.listChanged: true`，Client 必须注册对应的 notification handler，在收到通知时主动失效缓存
- 面试加分项：提一句 "类似 HTTP 的 stale-while-revalidate 策略也可用于 Resource 缓存"

---

## 任务 3：全局错误处理中间件（新增 §3.3.5）

**插入位置**：现有 §3.3.4「工具编写的十大准则」之后，§3.4「Resource 的暴露方式」之前。

### §3.3.5 全局错误处理中间件

Tool 函数的异常如果未在内部 catch，会变成 JSON-RPC `-32603 Internal Error` 抛给 Client。LLM 收到的是"冷冰冰"的错误码，无法做出有效的下一步决策。以下是一个全局中间件方案。

#### 全局异常拦截装饰器

```python
# error_middleware.py —— MCP 全局错误处理中间件
import functools
import traceback
import logging
from typing import Callable, Any

logger = logging.getLogger(__name__)


class LLMFriendlyError(Exception):
    """面向 LLM 的友好异常

    与普通 Exception 的区别：
    - 包含 recovery_hint（告诉 LLM 是否可重试、如何重试）
    - message 使用自然语言，LLM 可以直接展示给用户或据此决策
    """

    def __init__(self, message: str, recovery_hint: str = "DO_NOT_RETRY"):
        self.message = message
        self.recovery_hint = recovery_hint  # RETRY | RETRY_WITH_FIX | DO_NOT_RETRY
        super().__init__(message)


# 预定义的友好异常类型
class ToolNotFoundError(LLMFriendlyError):
    def __init__(self, tool_name: str):
        super().__init__(
            f"未找到名为 '{tool_name}' 的数据。"
            f"建议：1) 检查名称拼写是否正确 2) 尝试用 search 工具先搜索",
            "RETRY_WITH_FIX"
        )

class ExternalServiceError(LLMFriendlyError):
    def __init__(self, service: str, detail: str = ""):
        super().__init__(
            f"{service} 服务暂时不可用{': ' + detail if detail else ''}。"
            f"建议：稍后重试或联系系统管理员",
            "RETRY_LATER"
        )

class ValidationError(LLMFriendlyError):
    def __init__(self, field: str, reason: str):
        super().__init__(
            f"参数 '{field}' 不正确：{reason}。请修正后重试",
            "RETRY_WITH_FIX"
        )


def mcp_error_handler(func: Callable) -> Callable:
    """MCP Tool 全局错误处理装饰器

    三层处理逻辑：
    Layer 1: LLMFriendlyError → 以 isError: true 返回友好提示（LLM 可据此决策）
    Layer 2: 预期内的业务异常（ValueError 等） → 包装为友好提示
    Layer 3: 未预期的异常 → 记录详细日志，向 LLM 返回脱敏后的错误（不暴露堆栈）
    """

    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> str:
        import json

        try:
            return await func(*args, **kwargs)

        except LLMFriendlyError as e:
            # Layer 1：已包装好的友好异常，直接返回
            logger.warning(f"工具调用友好异常: {func.__name__} - {e.message}")
            return json.dumps({
                "success": False,
                "error": {
                    "message": e.message,
                    "recovery": e.recovery_hint
                }
            }, ensure_ascii=False)

        except ValueError as e:
            # Layer 2：参数校验类异常，包装为友好提示
            logger.warning(f"工具调用参数错误: {func.__name__} - {e}")
            return json.dumps({
                "success": False,
                "error": {
                    "message": f"参数错误：{e}。请检查传入的参数格式和取值范围。",
                    "recovery": "RETRY_WITH_FIX"
                }
            }, ensure_ascii=False)

        except Exception as e:
            # Layer 3：未预期的内部错误——这是最需要谨慎处理的情况
            # 详细堆栈只记录到日志，不返回给 LLM（安全考虑）
            error_id = _generate_error_id()
            logger.error(
                f"工具调用内部错误 [error_id={error_id}] "
                f"{func.__name__}: {e}\n{traceback.format_exc()}"
            )
            return json.dumps({
                "success": False,
                "error": {
                    "message": (
                        f"内部处理错误（错误 ID: {error_id}）。"
                        f"请稍后重试。如果问题持续，请向管理员提供此错误 ID。"
                    ),
                    "recovery": "DO_NOT_RETRY",
                    "error_id": error_id
                }
            }, ensure_ascii=False)

    return wrapper


import uuid

def _generate_error_id() -> str:
    return uuid.uuid4().hex[:8]


# ============================================================
# 使用方式
# ============================================================

@mcp.tool()
@mcp_error_handler  # ← 只需加一行装饰器
async def search_employees(query: str, search_by: str = "name") -> str:
    """搜索员工"""
    if len(query) < 2:
        raise ValidationError("query", "搜索关键词至少 2 个字符")

    try:
        results = await db.search(query, search_by)
    except ConnectionError:
        raise ExternalServiceError("数据库")

    if not results:
        raise ToolNotFoundError(query)

    return json.dumps({"success": True, "data": results})
```

#### 面向 LLM 的错误消息设计原则

核心原则：**LLM 需要的是"可操作的信息"，不是"技术故障码"**。

**正反例对比：**

```python
# ❌ 面向人类开发者的错误（LLM 无法有效利用）
"ERROR: SQLSTATE[HY000] Connection refused to 10.0.1.5:5432"
"IndexError: list index out of range at employee_service.py:147"
"500 Internal Server Error"

# ✅ 面向 LLM 的友好错误（LLM 能理解并做出下一步决策）
"数据库暂时不可用，建议稍后重试。如果问题持续，请向管理员提供错误 ID: a1b2c3d4"
"未找到匹配的员工 '张三'。建议：1) 尝试只搜姓氏 '张' 2) 按邮箱搜索 3) 确认部门名称正确"
"处理请求时遇到内部错误（错误 ID: x9k2m7q4）。此问题已自动记录，请稍后重试"
```

**设计规则：**

| 规则 | 说明 | 示例 |
|------|------|------|
| **自然语言优先** | 用自然语言描述而非错误码 | "数据库连接失败" 而非 "ECONNREFUSED" |
| **告诉 LLM 下一步做什么** | 每个错误附带 recovery hint | "RETRY_LATER" / "RETRY_WITH_FIX" |
| **提供替代方案** | 给出具体的回退建议 | "尝试用 search 工具先搜索" |
| **隐藏实现细节** | 不暴露堆栈、IP、文件路径、SQL 语句 | 脱敏后展示 |
| **区分内部 vs 外部** | 内部错误给 error_id（可追溯），外部错误给建议 | 如上 |

#### isError: true 与 JSON-RPC error 的选择决策树

```
发生异常
    │
    ├── 异常的根因是通信/协议问题？
    │   ├── YES → JSON-RPC Error
    │   │   例：无效 JSON、Method Not Found、Invalid Params
    │   │   特征：问题发生在 MCP 协议层，重试无法修复
    │   │
    │   └── NO → 继续判断
    │
    ├── 异常的根因是工具业务逻辑？
    │   ├── YES → result.isError: true
    │   │   例：数据未找到、外部服务超时、参数校验失败
    │   │   特征：问题发生在业务层，LLM 可以根据错误信息调整策略
    │   │
    │   └── 无法确定 → result.isError: true（保守策略）
    │
    └── 经验法则：
        如果连"请求是否到达了正确的工具函数"都不确定 → JSON-RPC Error
        如果工具函数正确执行但业务上失败了 → result.isError: true
```

---

## 任务 4：Mock Transport 轻量级测试（新增 §3.7.5）

**插入位置**：现有 §3.7.4「调试技巧汇总」之后，§四「底层原理」之前。

### §3.7.5 使用 Mock Transport 进行轻量级测试

启动真实 Server 进程的集成测试是必要的，但成本高（进程启动开销大、依赖外部环境）。对于工具函数的单元测试，Mock Transport 是更好的选择。

#### Mock Transport 实现

```python
# tests/mock_transport.py —— MCP Mock Transport
import asyncio
import json
from typing import Optional
from mcp import ClientSession
from mcp.shared.message import SessionMessage


class MockTransport:
    """Mock MCP Transport —— 不启动真实 Server 进程的轻量级测试方案

    核心思路：
    - 模拟 Transport 的两个流（read_stream / write_stream）
    - Client 发送的 JSON-RPC 消息进入 _client_requests 队列
    - 测试代码向 _server_responses 队列写入预期的响应
    - 完全在内存中运行，毫秒级完成

    适用场景：
    - 工具函数的单元测试（验证参数校验、返回格式、错误处理）
    - Client 缓存逻辑测试（tools/list_changed 通知模拟）
    - 重连逻辑测试（模拟连接断开和恢复）
    """

    def __init__(self):
        self._client_requests: asyncio.Queue = asyncio.Queue()
        self._server_responses: asyncio.Queue = asyncio.Queue()
        self._request_id = 0

    async def read(self):
        """Client 读取来自 'Server' 的消息（测试注入的响应）"""
        return await self._server_responses.get()

    async def write(self, message: dict):
        """Client 发送消息到 'Server'（被测试代码捕获）"""
        await self._client_requests.put(message)

    # ---- 测试辅助方法 ----

    async def get_client_request(self, timeout: float = 1.0) -> dict:
        """获取 Client 发送的请求（测试验证用）"""
        return await asyncio.wait_for(
            self._client_requests.get(), timeout=timeout
        )

    async def send_server_response(self, response: dict):
        """向 Client 发送 Server 响应"""
        await self._server_responses.put(response)

    async def simulate_initialize(self):
        """模拟完整的 initialize 握手"""
        # 获取 Client 的 initialize 请求
        init_req = await self.get_client_request()
        assert init_req["method"] == "initialize"

        # 返回 Server 的 initialize 响应
        await self.send_server_response({
            "jsonrpc": "2.0",
            "id": init_req["id"],
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": True, "listChanged": True}
                },
                "serverInfo": {"name": "mock-server", "version": "1.0.0"}
            }
        })

        # 接收 initialized 通知
        notification = await self.get_client_request()
        assert notification["method"] == "notifications/initialized"

    async def simulate_tool_response(
        self, request_id: int, content: str, is_error: bool = False
    ):
        """向 Client 发送工具调用结果"""
        await self.send_server_response({
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "content": [{"type": "text", "text": content}],
                "isError": is_error
            }
        })

    async def simulate_disconnect(self):
        """模拟连接断开"""
        await self._server_responses.put(EOFError("Connection closed"))

    async def simulate_timeout(self):
        """模拟超时"""
        await self._server_responses.put(asyncio.TimeoutError("Request timed out"))
```

#### 使用 Mock Transport 编写单元测试

```python
# tests/test_client_with_mock.py
import pytest
import asyncio
from mcp import ClientSession
from .mock_transport import MockTransport


@pytest.fixture
async def mock_session():
    """创建使用 Mock Transport 的 ClientSession"""
    transport = MockTransport()
    session = ClientSession(transport, transport)

    # 在后台启动 session 的初始化
    async def init_session():
        await transport.simulate_initialize()

    # 同时运行 init 和 session 的 initialize
    await asyncio.gather(
        session.initialize(),
        init_session()
    )

    yield session, transport
    # session 不需要显式关闭（Mock Transport 无真实资源）


# ---- 测试 1：正常工具调用 ----

@pytest.mark.asyncio
async def test_tool_call_success(mock_session):
    session, transport = mock_session

    # 发起工具调用（异步，不等待结果）
    call_task = asyncio.create_task(
        session.call_tool("get_weather", {"city": "北京"})
    )

    # 获取 Client 发送的请求
    request = await transport.get_client_request()
    assert request["method"] == "tools/call"
    assert request["params"]["name"] == "get_weather"
    assert request["params"]["arguments"] == {"city": "北京"}

    # 模拟 Server 返回成功
    await transport.simulate_tool_response(
        request["id"], "北京：晴，22°C"
    )

    # 验证结果
    result = await call_task
    assert result.content[0].text == "北京：晴，22°C"
    assert result.isError is False


# ---- 测试 2：工具调用返回业务错误 ----

@pytest.mark.asyncio
async def test_tool_call_business_error(mock_session):
    session, transport = mock_session

    call_task = asyncio.create_task(
        session.call_tool("get_weather", {"city": "不存在的城市"})
    )

    request = await transport.get_client_request()
    await transport.simulate_tool_response(
        request["id"],
        "未找到该城市的天气数据。请检查城市名称拼写。",
        is_error=True  # ← 业务错误
    )

    result = await call_task
    assert result.isError is True
    assert "未找到" in result.content[0].text


# ---- 测试 3：模拟网络故障 ----

@pytest.mark.asyncio
async def test_connection_error_handling(mock_session):
    session, transport = mock_session

    call_task = asyncio.create_task(
        session.call_tool("get_weather", {"city": "北京"})
    )

    # 消耗 Client 的请求
    await transport.get_client_request()

    # 模拟连接断开
    await transport.simulate_disconnect()

    # Client 应该抛出异常
    with pytest.raises(Exception):
        await call_task


# ---- 测试 4：模拟超时 ----

@pytest.mark.asyncio
async def test_timeout_handling(mock_session):
    session, transport = mock_session

    call_task = asyncio.create_task(
        session.call_tool("slow_tool", {})
    )

    await transport.get_client_request()
    await transport.simulate_timeout()

    with pytest.raises(asyncio.TimeoutError):
        await call_task


# ---- 测试 5：tools/list 缓存 ----

@pytest.mark.asyncio
async def test_tool_list_cache(mock_session):
    from ..robust_client import CachedMCPClient

    session, transport = mock_session
    cached_client = CachedMCPClient(session)

    # 第一次调用 → 应该发送 tools/list 请求
    task1 = asyncio.create_task(cached_client.list_tools())
    req1 = await transport.get_client_request()
    assert req1["method"] == "tools/list"
    await transport.simulate_tool_response(
        req1["id"],
        json.dumps({"tools": [{"name": "get_weather"}]})
    )
    tools1 = await task1
    assert len(tools1) == 1

    # 第二次调用 → 缓存命中，不应该发送请求
    tools2 = await cached_client.list_tools()
    assert tools2 == tools1  # 返回缓存结果
    assert transport._client_requests.empty()  # 没有新的请求

    # 模拟收到 tools/list_changed 通知 → 缓存失效
    cached_client.cache.invalidate_tools()

    # 第三次调用 → 缓存已失效，应该重新发送 tools/list
    task3 = asyncio.create_task(cached_client.list_tools())
    req3 = await transport.get_client_request()
    assert req3["method"] == "tools/list"
```

**测试策略总结**：

| 测试类型 | 使用的 Transport | 耗时 | 覆盖场景 |
|----------|-----------------|------|----------|
| **Mock Transport** | 内存队列 | 毫秒级 | 参数校验、返回格式、错误处理、缓存逻辑、重连逻辑 |
| **stdio 集成测试** | 真实子进程 | 秒级 | Client-Server 端到端、进程生命周期、版本协商 |
| **远程集成测试** | SSE / Streamable HTTP | 秒级 | 网络延迟、TLS、认证、超时 |

---

## 任务 5：SDK 版本迁移与跨语言差异（新增 §1.4）

**插入位置**：现有 §1.3「版本对照表」之后，§二「为什么需要」之前。

### §1.4 跨语言 SDK 行为差异注意事项

当项目需要同时使用 Python 和 TypeScript SDK，或从旧版本迁移时，了解差异点是避免踩坑的关键。

#### 5.1 `server.run()` 废弃后的完整迁移 checklist

```
从 server.run() → FastMCP 的迁移清单：

□ 步骤 1：检查当前 SDK 版本
    pip show mcp | grep Version
    如果 < 1.2.0 → 先升级: pip install mcp>=1.3.0

□ 步骤 2：替换 Server 创建方式
    [旧] from mcp.server import Server
         server = Server("my-server")
         @server.list_tools() ...
         server.run()

    [新] from mcp.server.fastmcp import FastMCP
         mcp = FastMCP("my-server")
         @mcp.tool() ...
         mcp.run(transport="stdio")

□ 步骤 3：检查工具注册装饰器
    [旧] @server.list_tools() + 手动返回 Tool 对象列表
    [新] @mcp.tool() 直接装饰函数（注意函数名 → tool name）

□ 步骤 4：检查 Resource 注册方式
    [旧] @server.list_resources() + @server.read_resource()
    [新] @mcp.resource("uri://path") 一个装饰器同时处理 list + read

□ 步骤 5：检查传输方式启动
    [旧] server.run() → 默认 stdio，其他传输需手动配置
    [新] mcp.run(transport="stdio")  明确指定传输，支持 "sse" / "streamable-http"

□ 步骤 6：检查能力声明
    [旧] 在 Server 构造时通过 capabilities 参数手动声明
    [新] FastMCP 从 @mcp.tool() / @mcp.resource() / @mcp.prompt()
         装饰器自动推断能力声明，无需手动设置

□ 步骤 7：运行测试
    python server.py          → 确认 Server 能启动
    npx @anthropic-ai/mcp-inspector python server.py  → 确认工具可被发现和调用
```

#### 5.2 Python SDK vs TypeScript SDK 关键行为差异

| 行为 | Python SDK | TypeScript SDK | 影响 |
|------|-----------|---------------|------|
| **工具参数处理** | 类型注解自动推导 JSON Schema | 需手动写 `z.object({...})`（Zod Schema） | TS 更显式但更繁琐 |
| **错误返回格式** | `isError: true` 在 result 对象上 | 同，但 TS 类型更严格（编译期检查） | Python 类型检查更宽松 |
| **异步支持** | `async def` + `asyncio` | `async/await` + Node.js Event Loop | 语言差异，非 SDK 差异 |
| **装饰器可用性** | `@mcp.tool()` 有类型推导 | `server.registerTool()` 函数式注册 | Python 更简洁 |
| **Pydantic vs Zod** | Pydantic BaseModel | Zod Schema | 都是运行时校验，API 风格不同 |
| **Resource 返回** | 返回 `str` 即可（自动包装） | 需显式返回 `{contents: [...]}` | TS 更接近协议规范 |
| **Transport 切换** | `mcp.run(transport="sse")` | 手动创建 `SSEServerTransport` | Python 的 FastMCP 抽象更高 |
| **社区工具数量** | ~1000+ PyPI 包 | ~2000+ npm 包 | TS 生态更多，Python 质量更高 |

**面试追问**："Python 和 TypeScript SDK 你更推荐哪个？为什么？"

**参考答案**：取决于团队技术栈和场景——
- **选 Python**：团队是数据/AI 背景、工具数量 < 20、快速原型验证。FastMCP 的开发效率是 TypeScript SDK 的 2-3 倍（类型自动推导、更少的样板代码）
- **选 TypeScript**：团队是前端/全栈背景、需要浏览器端 Client、工具定义需要编译期类型安全。Zod Schema 虽然写起来更繁琐，但在大型项目（50+ 工具）中类型安全的价值更大
- **两者混用**也是常见方案：Server 端用 Python FastMCP 快速开发，Client 端用 TypeScript SDK 在浏览器中连接

---

## 插入汇总：修改清单

| 序号 | 操作 | 位置 | 新增内容 |
|------|------|------|----------|
| 1 | **扩展** §1.1 | 社区 SDK 列表替换 | Go SDK 完整示例 + 面试应对 |
| 2 | **新增** §1.4 | §1.3 之后 | 迁移 checklist + Python/TS 差异对比 |
| 3 | **新增** §3.3.5 | §3.3.4 之后 | 全局错误处理中间件 + LLM 友好错误原则 + 决策树 |
| 4 | **新增** §3.5.2 | §3.5 之后 | 健壮 Client（重连/超时/并发/缓存四维度） |
| 5 | **新增** §3.7.5 | §3.7.4 之后 | Mock Transport 测试方案 + 5 个完整测试用例 |
| 6 | **新增** 面试题 | §6 内 | 2 道新题：Go SDK 选型 / 客户端健壮性设计 |
