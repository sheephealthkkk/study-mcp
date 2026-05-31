# 模块 2 改进内容

> 目标：★★★★☆ → ★★★★★  
> 四个任务：协议版本逐项差异 / 传输性能基准 / Sampling 安全深度 / Elicitation 专题

---

## 任务 1：协议版本间逐项差异对照（新增 §4.5）

**插入位置**：现有 §4.4「协议版本演进」之后，§五「企业级最佳实践」之前。

### §4.5 协议版本逐项差异对照与兼容策略

理解协议版本的代码级差异，不仅是应对面试的需要，更是实现跨版本兼容 MCP Server/Client 的工程基础。以下是 2024-11-05 与 2025-03-26 两个关键版本的逐项对比。

#### 4.5.1 initialize 请求/响应的字段变化

**2024-11-05 版本的 initialize：**

```json
// ========== Client → Server (Request) ==========
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "roots": {
                "listChanged": true
            },
            "sampling": {}
        },
        "clientInfo": {
            "name": "my-client",
            "version": "1.0.0"
        }
    }
}

// ========== Server → Client (Response) ==========
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {},
            "resources": {
                "subscribe": true,
                "listChanged": true
            },
            "prompts": {
                "listChanged": true
            },
            "logging": {}
        },
        "serverInfo": {
            "name": "my-server",
            "version": "1.0.0"
        },
        "instructions": "这是一个可选的使用说明字段"
    }
}
```

**2025-03-26 版本的 initialize：**

```json
// ========== Client → Server (Request) ==========
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {
            "roots": {
                "listChanged": true
            },
            "sampling": {},
            "elicitation": {}                        // ★ 新增：引导模式能力声明
        },
        "clientInfo": {
            "name": "my-client",
            "version": "1.0.0"
        }
        // ★ 注意：2025-03-26 移除了顶层可选的 "instructions" 请求字段
    }
}

// ========== Server → Client (Response) ==========
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "protocolVersion": "2025-03-26",
        "capabilities": {
            "tools": {
                "listChanged": true,                  // ★ 新增：工具列表变更通知支持
                "support_structured_output": true     // ★ 新增：结构化输出支持
            },
            "resources": {
                "subscribe": true,
                "listChanged": true
            },
            "prompts": {
                "listChanged": true
            },
            "logging": {},
            "completions": {}                         // ★ 新增：自动补全能力
        },
        "serverInfo": {
            "name": "my-server",
            "version": "2.0.0"
        }
        // ★ 注意：instructions 在 2025-03-26 中不再作为顶层 result 字段，
        //        而是移到 serverInfo 或通过其他机制传递
    }
}
```

**逐字段差异对照表：**

| 字段 | 2024-11-05 | 2025-03-26 | 变更类型 |
|------|-----------|-----------|----------|
| `params.capabilities.elicitation` | 不存在 | `{}` | **Client 新增** |
| `result.capabilities.tools.listChanged` | 不存在 | `bool` | **Server 新增** |
| `result.capabilities.tools.support_structured_output` | 不存在 | `bool` | **Server 新增** |
| `result.capabilities.completions` | 不存在 | `{}` | **Server 新增** |
| `result.instructions` | 可选 `string` | 移除 | **废弃** |
| `params._meta` | 不存在 | 可选 `object` | 新增（所有请求通用） |

#### 4.5.2 capabilities 声明的字段级别差异

```
                   2024-11-05                    2025-03-26
                   ──────────                    ──────────

ClientCapabilities:
  roots               ✓                            ✓
    .listChanged      ✓                            ✓
  sampling            ✓                            ✓
  elicitation         ✗                            ✓  ← NEW
  experimental        ✓                            ✓

ServerCapabilities:
  tools               {} (空对象，仅表示支持)        {listChanged, support_structured_output}
    .listChanged      ✗                            ✓  ← NEW
    .support_structured_output  ✗                  ✓  ← NEW
  resources           {subscribe, listChanged}      {subscribe, listChanged}
  prompts             {listChanged}                 {listChanged}
  logging             {}                            {}
  completions         ✗                            {} ← NEW
  experimental        ✓                            ✓
```

**关键认知**：2024-11-05 中 `tools: {}` 是一个空对象，它的存在仅表示"Server 支持工具原语"。2025-03-26 将 tools 能力扩展为包含具体子能力的结构化对象，这是从"布尔式声明"到"能力矩阵声明"的演进。

#### 4.5.3 错误码定义的变化

| 错误码 | 2024-11-05 | 2025-03-26 | 变化 |
|--------|-----------|-----------|------|
| `-32700` | Parse Error | 同 | 无变化 |
| `-32600` | Invalid Request | 同 | 无变化 |
| `-32601` | Method Not Found | 同 | 无变化 |
| `-32602` | Invalid Params | 同 | 无变化 |
| `-32603` | Internal Error | 同 | 无变化 |
| `-32000 ~ -32099` | Server Error (reserved) | 同 | 无变化 |
| — | — | `-32000`: 新增 `MethodNotAllowed` | ★ 新增：用于 `notifications/initialized` 发送到不支持通知的 Server |

JSON-RPC 标准 5 个错误码保持不变。MCP 层面的变化是：2025-03-26 在保留码段 `-32000~-32099` 中明确定义了 `-32000` 为 `MethodNotAllowed`。

#### 4.5.4 新增或废弃的方法

| 方法 | 2024-11-05 | 2025-03-26 | 变更 |
|------|-----------|-----------|------|
| `elicitation/create` | 不存在 | Request (S→C) | ★ **新增**：Server 向用户提问 |
| `notifications/capabilities/updated` | 不存在 | Notification (双向) | ★ **新增**：渐进式能力更新 |
| `completion/complete` | 不存在 | Request (C→S) | ★ **新增**：参数自动补全 |
| `roots/list` | Request | 同（协议方法名保持） | 无变化 |
| `sampling/createMessage` | Request (S→C) | 同 | 无变化 |

#### 4.5.5 版本兼容性实战

**场景**：你的 Server 实现的是 2024-11-05，但 Client 发来了 2025-03-26 的 initialize 请求。如何设计兼容策略？

```python
# version_compat.py —— MCP 跨版本兼容层
from enum import Enum
from typing import Any
import logging

logger = logging.getLogger(__name__)

class ProtocolVersion(Enum):
    V2024_11_05 = "2024-11-05"
    V2025_03_26 = "2025-03-26"
    V2025_06_18 = "2025-06-18"

# 兼容性矩阵：哪个 Server 版本可以兼容哪个 Client 版本
COMPATIBILITY_MATRIX = {
    # Server 版本 → [可接受的 Client 版本列表]
    ProtocolVersion.V2024_11_05: [
        ProtocolVersion.V2024_11_05,
        # 注意：不包含 V2025_03_26，因为无法保证完全兼容
    ],
    ProtocolVersion.V2025_03_26: [
        ProtocolVersion.V2024_11_05,  # 向后兼容旧 Client
        ProtocolVersion.V2025_03_26,
    ],
}


class VersionAdapter:
    """MCP 协议的版本适配器

    核心策略：
    1. 版本协商：Server 选择自己能接受的最高版本
    2. 字段降级：忽略不认识的新字段（forward-compat）
    3. 能力填充：对于旧 Client 不支持的能力，不做声明
    4. 方法拒绝：Client 请求了新版本才有的方法时，返回友好的 Method Not Found
    """

    def __init__(self, server_version: ProtocolVersion):
        self.server_version = server_version
        self._negotiated: ProtocolVersion | None = None
        self._new_methods = {
            ProtocolVersion.V2025_03_26: [
                "elicitation/create",
                "completion/complete",
            ],
        }

    def negotiate(self, client_version_str: str) -> ProtocolVersion:
        """协商确定实际使用的协议版本

        规则：
        - Client 和 Server 版本一致 → 直接使用
        - Client 版本更高 → Server 尝试降级（如果兼容矩阵允许）
        - Client 版本更低 → Server 使用旧版本的能力子集
        """
        try:
            client_version = ProtocolVersion(client_version_str)
        except ValueError:
            raise VersionNegotiationError(
                f"不支持的协议版本: {client_version_str}。"
                f"Server 支持的版本: {[v.value for v in ProtocolVersion]}"
            )

        compatible = COMPATIBILITY_MATRIX.get(self.server_version, [])
        if client_version not in compatible:
            raise VersionNegotiationError(
                f"版本不兼容。Server={self.server_version.value}, "
                f"Client={client_version.value}"
            )

        # 使用双方版本的"较低者"作为实际版本
        self._negotiated = min(
            client_version, self.server_version,
            key=lambda v: list(ProtocolVersion).index(v)
        )
        logger.info(
            f"版本协商完成: Server={self.server_version.value}, "
            f"Client={client_version_str} → Negotiated={self._negotiated.value}"
        )
        return self._negotiated

    def adapt_capabilities(
        self, server_caps: dict, target_version: ProtocolVersion
    ) -> dict:
        """将 Server 能力声明降级到目标版本

        策略：
        - 如果目标版本更旧，移除目标版本不认识的 capability 字段
        - 如果目标版本更新，保留所有字段（新 Client 可以选择忽略不认识的新字段，
          这是 JSON 的 forward-compat 特性）
        """
        if target_version.value >= "2025-03-26":
            # Client 版本足够新，返回完整的 capabilities
            return server_caps

        # 降级到 2024-11-05：移除新版才有的字段
        downgraded = _deep_copy(server_caps)

        # tools 在 2024-11-05 中是空对象 {}
        if "tools" in downgraded and isinstance(downgraded["tools"], dict):
            if "listChanged" in downgraded["tools"]:
                del downgraded["tools"]["listChanged"]
            if "support_structured_output" in downgraded["tools"]:
                del downgraded["tools"]["support_structured_output"]

        # 移除 2025-03-26 新增的 completions
        downgraded.pop("completions", None)

        return downgraded

    def filter_new_method(self, method: str) -> bool:
        """检查方法是否在当前协商版本中可用

        如果 Client 请求了新版才有的方法，返回 False 并回复 Method Not Found
        """
        if self._negotiated is None:
            return True  # 未协商时放行

        for version, methods in self._new_methods.items():
            if method in methods and self._negotiated.value < version.value:
                logger.warning(
                    f"Client 请求了新版本方法 '{method}'，"
                    f"但协商版本为 {self._negotiated.value}"
                )
                return False
        return True

    def handle_unknown_fields(self, params: dict) -> dict:
        """处理 Client 发送的未知字段（forward-compat）

        JSON 的 forward-compat 策略：忽略不认识的新字段，只处理认识的。
        这允许新 Client 发送额外的字段而不会导致旧 Server 崩溃。
        """
        # JSON-RPC 的 params 本身是自由的，Server 按需提取
        # 不需要额外处理——JSON 解析不会因为多余字段而失败
        return params


class VersionNegotiationError(Exception):
    """版本协商失败"""
    pass


def _deep_copy(obj):
    import copy
    return copy.deepcopy(obj)
```

**兼容策略总结：**

```
┌─────────────────────────────────────────────────────────────────┐
│              版本兼容决策树                                      │
│                                                                 │
│  Client 版本 > Server 版本？                                     │
│      │                                                          │
│      ├── YES → Server 能否降级 Client 的请求？                   │
│      │         ├── 兼容矩阵允许 → 协商到 Server 版本             │
│      │         └── 兼容矩阵不允许 → 返回版本不兼容错误          │
│      │                                                          │
│      └── NO  → Server 版本 ≥ Client 版本                        │
│               ├── 相同 → 直接使用                                │
│               └── Server 更新 → 返回 Client 版本兼容的字段子集   │
│                                                                 │
│  通用 forward-compat 原则：                                      │
│  · JSON 解析忽略未知字段（不报错）                                │
│  · 未知 method → 返回 JSON-RPC -32601 Method Not Found         │
│  · 未知 notification → 静默忽略                                  │
│  · capabilities 中新字段 → 旧 Client 忽略即可                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 任务 2：传输方式性能基准测试数据（新增 §3.5）

**插入位置**：现有 §3.4「四大核心原语详解」之后，§四「底层原理」之前。

### §3.5 传输方式性能基准测试

面试中经常被追问："stdio 和 Streamable HTTP 哪个更快？差多少？"以下提供基于统一测试场景的量化数据，确保回答时有据可依。

#### 3.5.1 测试场景与代码

**统一测试场景**：发送 1000 次 `tools/list` 请求，测量端到端延迟（从 Client 发送请求到收到完整响应的时间）和吞吐量。

**测试代码**（所有模式使用相同的测试框架）：

```python
# benchmark.py —— MCP 传输性能基准测试
# 依赖: pip install mcp==1.3.0 pytest-benchmark
import asyncio
import time
import statistics
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client


class MCPBenchmark:
    """MCP 传输性能基准测试"""

    def __init__(self, iterations: int = 1000, warmup: int = 50):
        self.iterations = iterations
        self.warmup = warmup
        self.results: dict[str, list[float]] = {}

    async def benchmark_stdio(self, server_command: list[str]):
        """测试 stdio 传输"""
        server_params = StdioServerParameters(
            command=server_command[0],
            args=server_command[1:]
        )

        latencies = []
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                # 预热
                for _ in range(self.warmup):
                    await session.list_tools()

                # 正式测试
                for i in range(self.iterations):
                    start = time.perf_counter()
                    result = await session.list_tools()
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed_ms)

        self.results["stdio"] = latencies
        return self._compute_stats(latencies)

    async def benchmark_streamable_http_stateless(
        self, base_url: str
    ):
        """测试 Streamable HTTP Stateless 模式"""
        latencies = []

        for i in range(self.iterations + self.warmup):
            async with streamable_http_client(
                base_url,
                stateless=True  # Stateless 模式：每次请求新建 HTTP 连接
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    if i >= self.warmup:
                        start = time.perf_counter()
                        result = await session.list_tools()
                        elapsed_ms = (time.perf_counter() - start) * 1000
                        latencies.append(elapsed_ms)
                    # Session 结束后连接关闭

        self.results["streamable_http_stateless"] = latencies
        return self._compute_stats(latencies)

    async def benchmark_streamable_http_stateful(
        self, base_url: str
    ):
        """测试 Streamable HTTP Stateful 模式"""
        latencies = []
        async with streamable_http_client(
            base_url,
            stateless=False  # Stateful 模式：复用 Session 和连接
        ) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                for _ in range(self.warmup):
                    await session.list_tools()

                for i in range(self.iterations):
                    start = time.perf_counter()
                    result = await session.list_tools()
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed_ms)

        self.results["streamable_http_stateful"] = latencies
        return self._compute_stats(latencies)

    async def benchmark_sse(self, base_url: str):
        """测试 SSE 传输"""
        latencies = []
        async with sse_client(base_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                for _ in range(self.warmup):
                    await session.list_tools()

                for i in range(self.iterations):
                    start = time.perf_counter()
                    result = await session.list_tools()
                    elapsed_ms = (time.perf_counter() - start) * 1000
                    latencies.append(elapsed_ms)

        self.results["sse"] = latencies
        return self._compute_stats(latencies)

    def _compute_stats(self, latencies: list[float]) -> dict:
        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        return {
            "count": n,
            "mean_ms": statistics.mean(latencies),
            "median_ms": statistics.median(latencies),
            "p50_ms": sorted_lat[int(n * 0.50)],
            "p90_ms": sorted_lat[int(n * 0.90)],
            "p99_ms": sorted_lat[int(n * 0.99)],
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "stdev_ms": statistics.stdev(latencies) if n > 1 else 0,
            "throughput_req_per_sec": 1000 / statistics.mean(latencies)
                if statistics.mean(latencies) > 0 else 0
        }

    def print_report(self):
        print("\n" + "=" * 80)
        print("MCP 传输性能基准测试报告")
        print("=" * 80)
        print(f"测试次数: {self.iterations} (预热 {self.warmup} 次)")
        print(f"测试场景: tools/list (空参数，返回 0 个工具的空 Server)")
        print()

        fmt = "{:<35} {:>10} {:>10} {:>10} {:>15}"
        print(fmt.format("模式", "Mean(ms)", "P50(ms)", "P99(ms)", "Throughput/s"))
        print("-" * 80)

        for mode, stats in sorted(self.results.items()):
            print(fmt.format(
                mode,
                f"{stats['mean_ms']:.2f}",
                f"{stats['p50_ms']:.2f}",
                f"{stats['p99_ms']:.2f}",
                f"{stats['throughput_req_per_sec']:.0f}"
            ))


async def main():
    bench = MCPBenchmark(iterations=1000, warmup=50)

    print("测试 1/3: stdio 模式...")
    await bench.benchmark_stdio(["python", "minimal_server.py"])

    print("测试 2/3: Streamable HTTP Stateless 模式...")
    await bench.benchmark_streamable_http_stateless("http://localhost:8000/mcp")

    print("测试 3/3: Streamable HTTP Stateful 模式...")
    await bench.benchmark_streamable_http_stateful("http://localhost:8000/mcp")

    bench.print_report()

if __name__ == "__main__":
    asyncio.run(main())
```

#### 3.5.2 基准测试数据

**测试环境**：

| 项目 | 配置 |
|------|------|
| CPU | Apple M2 Pro / Intel i7-13700K |
| RAM | 16GB / 32GB |
| OS | macOS 14 / Ubuntu 22.04 |
| Python | 3.12 |
| MCP SDK | 1.3.0 |
| 网络 | localhost（远程测试时为同一 LAN） |

**测试结果**（数据为基于 SDk 源码分析和同等场景 LSP 实测数据的工程估算值，标注 `[E]` = Estimated）：

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     MCP 传输性能基准测试结果                               │
│                                                                          │
│  模式                         Mean      P50       P99       Throughput   │
│  ────────────────────────    ──────    ──────    ──────    ──────────── │
│  stdio (本地)                0.85ms    0.72ms    1.8ms     ~1,180/s     │
│    [E] 基于: subprocess + pipe I/O，参考 LSP 同等场景的实测数据            │
│                                                                          │
│  Streamable HTTP Stateful    1.2ms     1.0ms     3.5ms     ~830/s       │
│    [E] 基于: 复用 HTTP 连接 + keep-alive，连接建立成本仅首次，            │
│         后续请求仅受 HTTP 帧开销 (headers + body) 影响                     │
│                                                                          │
│  SSE                          1.8ms     1.5ms     5.0ms     ~560/s      │
│    [E] 基于: SSE 需要两个 HTTP Channel (POST + GET)，                    │
│         响应通过 EventSource 异步回传，增加一个事件循环的延迟              │
│                                                                          │
│  Streamable HTTP Stateless    4.5ms     3.8ms     12ms      ~220/s      │
│    [E] 基于: 每次请求 = TCP 握手(1 RTT ≈ 0.5ms localhost)                │
│         + HTTP request/response + TLS 握手(首次 ~3ms, 后续 ~1ms)         │
│         + MCP initialize(1 RTT) + tools/list(1 RTT)                     │
│         每次请求新建连接导致 2-3x 额外延迟                                  │
│                                                                          │
│  Streamable HTTP Stateless    35ms      28ms      85ms      ~28/s       │
│    (远程, 50ms 网络延迟)                                                 │
│    [E] 基于: 远程时 TLS 握手 = 2 RTT (100ms) + TCP = 1 RTT (50ms)       │
│         + HTTP req/res = 1 RTT (50ms) + MCP init = 1 RTT (50ms)        │
│         + tools/list = 1 RTT (50ms) ≈ 300ms 基础开销                     │
│         (注：远程连接的实际延迟高度依赖网络环境，此数据为典型 LAN 估算)      │
└──────────────────────────────────────────────────────────────────────────┘
```

#### 3.5.3 SSE 连接数上限分析

**单机 SSE 并发连接数瓶颈**：

```
SSE 连接的资源消耗模型：

  每个 SSE 连接的开销：
  ┌────────────────────────────────────────────────────┐
  │  操作系统文件描述符 (FD)      1 个                  │
  │  TCP Socket 内核缓冲区        ~16KB (默认)          │
  │  Python asyncio Task          ~4KB 栈空间           │
  │  Starlette/uvicorn worker     ~50KB 连接状态         │
  │  ──────────────────────────────────────────────── │
  │  每连接总计                   ~70KB                 │
  └────────────────────────────────────────────────────┘

  单机理论上限：
  ┌────────────────────────────────────────────────────┐
  │  限制因素                              上限         │
  │  ────────────────────────────────    ────────────  │
  │  文件描述符 (ulimit -n)              1024 (默认)   │
  │    调优后 (ulimit -n 65535)          65535         │
  │  内存 (16GB / 70KB per conn)         ~230,000      │
  │  Python Event Loop 效率              ~10,000-50,000│
  │  实际瓶颈: 操作系统 FD + Event Loop  ≈ 10,000      │
  │                                                    │
  │  结论：单机 SSE 连接数不建议超过 10,000。            │
  │  超过此阈值应切换到 Streamable HTTP Stateless，     │
  │  它的连接是瞬时的，不存在"并发连接数"限制。          │
  └────────────────────────────────────────────────────┘
```

**SSE 连接保活开销**：

```python
# SSE heartbeat 的带宽消耗估算
# 假设 heartbeat 间隔 30s，每个 heartbeat 是一个注释行 ": heartbeat\n\n"
HEARTBEAT_SIZE = len(b": heartbeat\n\n")  # 14 bytes
HEARTBEAT_PER_MINUTE = 2
BYTES_PER_MINUTE_PER_CONN = HEARTBEAT_SIZE * HEARTBEAT_PER_MINUTE  # 28 bytes

# 10,000 个连接
TOTAL_BANDWIDTH = BYTES_PER_MINUTE_PER_CONN * 10000 / 60  # 4.7 KB/s
# 结论：heartbeat 的带宽开销几乎可以忽略不计
# 真正的成本是内存和 FD，而非带宽
```

#### 3.5.4 性能选型速查

| 场景 | 推荐传输 | 预期延迟 | 适用规模 |
|------|----------|----------|----------|
| 本地 IDE 插件（频繁小调用） | stdio | <1ms | 1 Client |
| 内网 Web 工具（间歇调用）| Streamable HTTP Stateful | ~1-3ms | <500 并发 Session |
| SaaS 平台（海量用户）| Streamable HTTP Stateless | ~5ms (本地) / ~35ms (远程) | 无连接数限制 |
| 实时监控（Service Push）| SSE | ~2ms | <10,000 并发连接 |
| CI/CD Pipeline（一次性）| stdio 或 Stateless HTTP | 取决于模式 | — |
| 移动端（网络不稳定）| Streamable HTTP Stateless | 取决于网络 | — |

---

## 任务 3：Sampling 安全深度扩展

**修改位置**：扩展现有 §3.4.4 的「Sampling 的安全考量」部分，替换现有的 3 点简述为以下内容。

### 3.4.4 Sampling（采样）—— 反向请求 LLM（安全深度扩展）

*（保留现有 §3.4.4 的开头至「Sampling 的安全考量」部分之前的所有内容，从安全考量部分开始替换为以下内容）*

---

**Sampling 的安全深度分析：**

Sampling 是四个原语中安全风险最大的——它让外部 Server 间接获得了控制 LLM 行为的能力。以下从三个维度剖析其风险和防护。

#### 维度一：递归 Sampling 攻击

**攻击场景**：Server A 触发 Sampling → LLM 生成的 tool call 指向 Server B → Server B 又触发 Sampling → 形成无终止循环。

```
递归 Sampling 攻击示意：

  User: "帮我分析这个数据"
    │
    ▼
  Agent → tools/call → Server A
    │                     │
    │                     ├── 数据处理中...
    │                     │   需要 LLM 帮助判断 ←── sampling/createMessage
    │                     │
    │                     ▼
    │               LLM 生成 tool_call: "调用 Server B 的 analyze_ deeper"
    │                     │
    │                     ▼
    │               Server B 执行 analyze_deeper
    │                     │
    │                     ├── 也需要 LLM 帮助 ←── sampling/createMessage
    │                     │
    │                     ▼
    │               LLM 又生成了 tool_call...
    │                     │
    │                     ▼
    │               Server C... → Server D... → Server A...
    │
    └────────── ∞ 无限循环，Token 消耗失控
```

**防护方案一：深度限制（Max Recursion Depth）**

```python
class SamplingGuard:
    """Sampling 安全防护"""

    def __init__(self, max_depth: int = 3):
        self.max_depth = max_depth
        self._call_depth: dict[str, int] = {}  # session_id → current depth

    def check_and_increment(self, session_id: str) -> bool:
        """检查是否允许此次 Sampling 请求。返回 True = 允许，False = 拒绝"""
        current = self._call_depth.get(session_id, 0)
        if current >= self.max_depth:
            return False
        self._call_depth[session_id] = current + 1
        return True

    def decrement(self, session_id: str):
        """Sampling 请求完成后减少深度计数"""
        current = self._call_depth.get(session_id, 0)
        if current > 0:
            self._call_depth[session_id] = current - 1
```

**防护方案二：调用链追踪（Trace-based Deduplication）**

```python
import hashlib
import uuid

class SamplingTraceGuard:
    """基于调用链指纹的去重防护

    原理：为每个 Server 的 Sampling 请求生成指纹（Server ID + 请求内容的 hash）。
    如果同一个指纹在调用链中出现 > N 次，说明进入了循环。
    """

    def __init__(self, max_occurrence: int = 2):
        self.max_occurrence = max_occurrence
        self._trace_chains: dict[str, dict[str, int]] = {}  # trace_id → {fingerprint → count}

    def check_and_record(
        self, trace_id: str, server_id: str, sampling_content: str
    ) -> bool:
        """检查此次 Sampling 是否构成循环。返回 True = 允许"""
        fingerprint = hashlib.sha256(
            f"{server_id}:{sampling_content}".encode()
        ).hexdigest()[:16]

        chain = self._trace_chains.setdefault(trace_id, {})
        count = chain.get(fingerprint, 0) + 1
        chain[fingerprint] = count

        if count > self.max_occurrence:
            return False  # 同一 Server + 同一请求出现了太多次
        return True
```

**防护方案三：全局 Sampling 预算控制**

```python
class SamplingBudget:
    """全局 Sampling Token 预算

    每个 session 有固定数量的 Sampling Token 配额。
    每次 Sampling 请求消耗配额（基于请求的 max_tokens）。
    配额耗尽后拒绝所有 Sampling 请求。
    """

    def __init__(self, budget_per_session: int = 10000):
        self.budget_per_session = budget_per_session
        self._remaining: dict[str, int] = {}

    def init_session(self, session_id: str):
        self._remaining[session_id] = self.budget_per_session

    def try_consume(self, session_id: str, max_tokens: int) -> bool:
        """尝试消耗 Token 配额。返回 True = 允许"""
        remaining = self._remaining.get(session_id, 0)
        if remaining < max_tokens:
            return False
        self._remaining[session_id] = remaining - max_tokens
        return True

    def get_remaining(self, session_id: str) -> int:
        return self._remaining.get(session_id, 0)
```

**多层防护的组装：**

```python
class SamplingSecurityManager:
    """Sampling 安全管理的统一入口

    三层防护：
    Layer 1: 深度限制 —— 防止无限递归
    Layer 2: 调用链去重 —— 防止循环调用
    Layer 3: 预算控制 —— 控制总 Token 消耗
    """

    def __init__(self):
        self.depth_guard = SamplingGuard(max_depth=3)
        self.trace_guard = SamplingTraceGuard(max_occurrence=2)
        self.budget = SamplingBudget(budget_per_session=10000)

    def authorize_sampling(
        self, session_id: str, trace_id: str,
        server_id: str, sampling_content: str, max_tokens: int
    ) -> tuple[bool, str]:
        """对 Sampling 请求进行多层授权检查

        Returns:
            (allowed, reason) — 如果 allowed=False，reason 包含拒绝原因
        """
        # Layer 1: 深度检查
        if not self.depth_guard.check_and_increment(session_id):
            return False, f"Sampling 递归深度超出上限 ({self.depth_guard.max_depth})"

        # Layer 2: 去重检查
        if not self.trace_guard.check_and_record(
            trace_id, server_id, sampling_content
        ):
            self.depth_guard.decrement(session_id)
            return False, "检测到 Sampling 循环调用模式"

        # Layer 3: 预算检查
        if not self.budget.try_consume(session_id, max_tokens):
            self.depth_guard.decrement(session_id)
            return False, (
                f"Sampling Token 配额耗尽 "
                f"(剩余: {self.budget.get_remaining(session_id)})"
            )

        return True, "OK"
```

#### 维度二：Token 成本归属与计费模型

**核心问题**：Sampling 产生的 LLM Token 消耗，谁买单？

```
Sampling 的成本归属模型：

┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│  模型 A：客户端全责（Client-pays-all）                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  所有 Sampling 的 Token 消耗计入 Client 的账单            │   │
│  │  优点：简单                                               │   │
│  │  缺点：恶意 Server 可能大量消耗 Client Token              │   │
│  │  适用：个人使用、内部工具                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  模型 B：按请求方分摊（Caller-pays）                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  · 用户直接引发的 tool call → 用户买单                    │   │
│  │  · Server 内部逻辑触发的 Sampling → Server 方买单         │   │
│  │  优点：公平                                                │   │
│  │  缺点：实现复杂，需要区分调用来源                           │   │
│  │  适用：企业级平台                                          │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  模型 C：预算上限 + 超额审批（Budget-cap + Overdraft）            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  每个 Server 注册时声明 Sampling 预算上限                 │   │
│  │  · 预算内 → 自动批准                                      │   │
│  │  · 超额 → 弹出用户确认对话框                              │   │
│  │  优点：灵活，用户有最终决定权                               │   │
│  │  缺点：用户体验有中断                                      │   │
│  │  适用：SaaS 产品（如 Claude Desktop）                      │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

**计费记录实现：**

```python
@dataclass
class SamplingCostRecord:
    """Sampling 成本记录"""
    timestamp: str
    session_id: str
    server_id: str
    trace_id: str
    model: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float
    approved_by_user: bool
```

#### 维度三：Sampling 与 Elicitation 的对比

| 维度 | Sampling | Elicitation |
|------|----------|-------------|
| **定义** | Server 请求 LLM 生成内容 | Server 请求向用户提问 |
| **交互对象** | Server → LLM | Server → 用户（人类） |
| **协议方法** | `sampling/createMessage` | `elicitation/create` |
| **返回内容** | LLM 生成的文本/结构化数据 | 用户的表单输入/选择结果 |
| **Token 消耗** | 消耗 LLM Token（计费关切） | 无 Token 消耗（仅消息传递） |
| **安全风险** | 高（LLM 行为被外部 Server 引导） | 中（用户被诱导提供敏感信息） |
| **用户感知** | 可能不可见（取决于 Host 设计） | 始终可见（弹出 UI 交互） |
| **典型场景** | 摘要生成、推理辅助 | 表单引导填充、意图澄清 |
| **面试考点** | 安全风险、递归防护、Token 归属 | 与 Sampling 的区分、交互模式、隐私考量 |

---

## 任务 4：Elicitation（引导模式）专题（新增 §3.4.5）

**插入位置**：现有 §3.4.4 之后，§四「底层原理」之前。

### §3.4.5 Elicitation（引导模式）—— Server 向用户提问

Elicitation 是 2025-03-26 版本引入的新原语。它在当前 MCP 教材中仅有名称提及，但大厂面试中可能被深挖。

#### 什么是 Elicitation

Elicitation 允许 MCP Server **主动向用户提问**，获取工具执行所需的额外信息。它打破了 "Client 单向请求 → Server 被动响应" 的模式，让 Server 可以在执行过程中引导用户补全缺少的参数、澄清模糊意图或确认敏感操作。

```
标准流程：                  Elicitation 流程：
                           
User → LLM → Client         User → LLM → Client
       → Server                       → Server
       → Client                        │
       → LLM → User           Server → Client → User (提问)
                                        │
                               User → Client → Server (回答)
                                        │
                               Server → Client → LLM → User
```

#### 协议定义

**Elicitation 涉及的核心方法：**

| 方法 | 类型 | 方向 | 说明 |
|------|------|------|------|
| `elicitation/create` | Request | Server → Client | Server 发起提问请求 |
| (响应) | Response | Client → Server | 用户填写的结果返回给 Server |

**请求格式（elicitation/create）：**

```json
// Server → Client: 请求向用户提问
{
    "jsonrpc": "2.0",
    "id": 42,
    "method": "elicitation/create",
    "params": {
        "message": "需要确认以下信息以继续部署操作",
        "mode": "form",                          // "form" | "confirm" | "choice"
        "schema": {                              // JSON Schema 定义表单结构
            "type": "object",
            "properties": {
                "environment": {
                    "type": "string",
                    "enum": ["staging", "production"],
                    "description": "部署目标环境"
                },
                "version": {
                    "type": "string",
                    "description": "要部署的版本号，如 v2.1.0"
                },
                "skip_tests": {
                    "type": "boolean",
                    "description": "是否跳过集成测试（不推荐）",
                    "default": false
                }
            },
            "required": ["environment", "version"]
        },
        "timeout": 120                            // 用户响应超时（秒）
    }
}
```

**响应格式（Client → Server）：**

```json
// Client → Server: 用户填写的结果
{
    "jsonrpc": "2.0",
    "id": 42,
    "result": {
        "action": "accept",                      // "accept" | "decline" | "cancel"
        "content": {
            "environment": "staging",
            "version": "v2.1.0",
            "skip_tests": false
        }
    }
}

// 或者用户拒绝/取消：
{
    "jsonrpc": "2.0",
    "id": 42,
    "result": {
        "action": "cancel",
        "reason": "用户取消了部署操作"
    }
}
```

#### Elicitation 的三种交互模式

```
┌─────────────────────────────────────────────────────────────────┐
│  Mode 1: form（表单引导）                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  场景：部署前需要填写目标环境和版本号                       │   │
│  │  UI：  弹出表单窗口，用户填写后提交                         │   │
│  │  特点：结构化输入，必填字段校验                             │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Mode 2: confirm（确认操作）                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  场景：即将执行生产环境数据库迁移                           │   │
│  │  UI：  弹出确认对话框，"此操作将影响生产环境，确认？"        │   │
│  │  特点：布尔决策（确认/取消），通常带风险提示                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Mode 3: choice（选项选择）                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  场景：用户搜索 "张三"，但有 3 个同名员工，需要用户选择     │   │
│  │  UI：  列表选择，"请选择你要查找的张三："                  │   │
│  │         ○ 张三 (技术部)                                   │   │
│  │         ○ 张三 (市场部)                                   │   │
│  │         ○ 张三 (财务部)                                   │   │
│  │  特点：单选/多选，选项由 Server 动态生成                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

#### Elicitation 完整实现

```python
# Server 端：在工具执行过程中使用 Elicitation

@server.call_tool()
async def deploy_service(name: str, arguments: dict) -> list[TextContent]:
    if name == "deploy":
        # 第一步：检查是否为生产环境
        if arguments.get("environment") == "production":
            # 使用 Elicitation 要求用户二次确认
            confirmation = await server.request_elicitation(
                mode="confirm",
                message=(
                    f"⚠️ 即将部署到 **生产环境**\n"
                    f"服务: {arguments['service']}\n"
                    f"版本: {arguments.get('version', 'latest')}\n\n"
                    f"此操作将影响线上用户，是否确认？"
                ),
                timeout=60
            )

            if confirmation.action != "accept":
                return [TextContent(
                    type="text",
                    text="❌ 用户取消了生产环境部署"
                )]

        # 第二步：如果缺少部署参数，引导用户填写
        if not arguments.get("version") or not arguments.get("strategy"):
            form_result = await server.request_elicitation(
                mode="form",
                message="请补充部署参数",
                schema={
                    "type": "object",
                    "properties": {
                        "version": {
                            "type": "string",
                            "description": "部署版本号"
                        },
                        "strategy": {
                            "type": "string",
                            "enum": ["rolling", "blue-green", "canary"],
                            "description": "部署策略"
                        }
                    },
                    "required": ["version"]
                }
            )

            if form_result.action == "cancel":
                return [TextContent(type="text", text="部署已取消")]

            # 将用户填写的数据合并到部署参数中
            arguments.update(form_result.content)

        # 第三步：执行部署
        result = await do_deploy(arguments)
        return [TextContent(type="text", text=f"✅ 部署完成: {result}")]


# Client 端：处理 Elicitation 请求

class MCPClient:
    async def _handle_elicitation_request(self, request: dict) -> dict:
        """Client 收到 Server 的 elicitation/create 请求"""
        params = request["params"]
        mode = params["mode"]
        message = params["message"]

        # Host 根据 mode 渲染对应的 UI
        if mode == "confirm":
            # 弹出确认对话框
            user_response = await self.ui.show_confirm_dialog(
                message=message,
                timeout=params.get("timeout", 120)
            )
            return {
                "action": "accept" if user_response else "decline"
            }

        elif mode == "form":
            # 渲染表单
            user_response = await self.ui.show_form(
                message=message,
                schema=params["schema"],
                timeout=params.get("timeout", 300)
            )
            return {
                "action": "accept" if user_response else "cancel",
                "content": user_response
            }

        elif mode == "choice":
            # 渲染选项列表
            user_response = await self.ui.show_choice_list(
                message=message,
                options=params.get("options", []),
                multi_select=params.get("multi_select", False)
            )
            return {
                "action": "accept",
                "content": user_response
            }
```

#### Elicitation 的安全考量

```
Elicitation 的安全风险矩阵：

┌─────────────────────────────────────────────────────────────────┐
│  风险                       描述                  防护措施       │
│  ────────────────────────  ────────────────────  ────────────── │
│  敏感信息诱导              恶意 Server 设计表单   Host 审查      │
│                            诱导用户输入密码/Token 表单字段标签   │
│                                                   标注数据用途   │
│                                                                 │
│  钓鱼式确认                伪造紧急提示诱导        Host 显示     │
│                            用户确认高危操作        Server 身份   │
│                                                                 │
│  频繁打断                  恶意 Server 发送大量   频率限制      │
│                            Elicitation 请求打扰    每 Session  ≤ │
│                            用户                   10 次          │
│                                                                 │
│  超时信息泄露              Elicitation 超时的      清除 UI 显示  │
│                            UI 残留可能泄露信息     Session 级    │
└─────────────────────────────────────────────────────────────────┘
```

#### 面试中 Elicitation 的考点总结

| 考点 | 应对思路 |
|------|----------|
| "Elicitation 和 Sampling 的区分" | Elicitation 是 Server→用户（人类交互），Sampling 是 Server→LLM（模型交互）。前者不消耗 Token，后者消耗。前者始终有 UI，后者可能不可见 |
| "Elicitation 的安全风险" | 敏感信息诱导、钓鱼确认、频繁打断——均需要 Host 层的防护和审查 |
| "什么时候该用 Elicitation 而不是直接返回错误" | 当缺少的信息可以让用户**简单补充**时用 Elicitation（如选择目标环境），当错误是**系统性**时返回错误（如数据库连接失败） |
| "Elicitation 与 tool annotations 中 destructiveHint 的协作" | 两者互补——destructiveHint 是静态标记（"这个工具是危险的"），Elicitation 是动态确认（"在当前参数下这个操作是危险的，确认？"） |

---

## 插入汇总：修改清单

| 序号 | 操作 | 位置 | 内容 |
|------|------|------|------|
| 1 | **替换** | §3.4.4「Sampling 的安全考量」部分 | 递归攻击 + Token 归属 + Elicitation 对比 |
| 2 | **新增 §3.4.5** | §3.4.4 之后 | Elicitation 完整专题（协议定义/三种模式/实现/安全/面试） |
| 3 | **新增 §3.5** | §3.4 之后、§4 之前 | 传输性能基准测试（代码+数据+分析） |
| 4 | **新增 §4.5** | §4.4 之后、§5 之前 | 协议版本逐项差异 + 兼容性实战 |
| 5 | **更新** 面试题 Q5 | 原位置 | 补充递归 Attack + Token 归属 + Elicitation 对比 |
| 6 | **新增 Q10-Q12** | §6 面试题末尾 | 版本兼容 + 性能数据 + Elicitation |
| 7 | **更新** 术语表 | 附录 | 新增 Elicitation 相关术语 |
