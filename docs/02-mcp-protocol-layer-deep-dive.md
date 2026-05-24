# 第二模块：MCP 协议层深入理解

> **学习周期**：3-4 天  
> **学习目标**：理解 MCP 的底层通信协议、传输方式和核心原语，具备排障能力

---

## 目录

1. [一、是什么——MCP 协议全景回顾](#一是什么mcp-协议全景回顾)
2. [二、为什么需要——传输层演进与核心原语设计动机](#二为什么需要传输层演进与核心原语设计动机)
3. [三、如何实现——传输机制与原语详解](#三如何实现传输机制与原语详解)
4. [四、底层原理——JSON-RPC 消息格式与能力协商](#四底层原理json-rpc-消息格式与能力协商)
5. [五、企业级最佳实践](#五企业级最佳实践)
6. [六、常见面试题](#六常见面试题)

---

## 一、是什么——MCP 协议全景回顾

### 1.1 MCP 协议的层次结构

在理解传输层之前，我们需要先建立 MCP 协议的宏观分层视图：

```
┌────────────────────────────────────────────────┐
│              应用语义层 (Semantic Layer)          │
│  Tools (做什么)  │  Resources (有什么)            │
│  Prompts (怎么说) │  Sampling (让 LLM 再生成)     │
├────────────────────────────────────────────────┤
│              协议消息层 (Message Layer)            │
│  Request  │  Response  │  Notification           │
│  Result   │  Error     │  Progress               │
├────────────────────────────────────────────────┤
│              RPC 协议层 (RPC Layer)               │
│           JSON-RPC 2.0                           │
│  id / method / params / result / error          │
├────────────────────────────────────────────────┤
│             传输层 (Transport Layer)              │
│  stdio  │  SSE  │  Streamable HTTP (默认)        │
└────────────────────────────────────────────────┘
```

**关键认知**：MCP 是一个 **分层协议**。传输层负责 "字节怎么传"，RPC 层负责 "消息怎么封装"，消息层负责 "请求/响应怎么交互"，语义层负责 "工具/资源/提示词怎么表达"。

### 1.2 什么是 JSON-RPC 2.0

**JSON-RPC 2.0** 是一种轻量级的远程过程调用（RPC）协议，使用 JSON 作为唯一的数据序列化格式。它定义了一套极简的规范——只有请求、响应、通知、错误四种消息类型。

```json
// 一个 JSON-RPC 请求的四个要素
{
    "jsonrpc": "2.0",          // ① 协议版本标识
    "id": 1,                   // ② 请求 ID（通知类型无此字段）
    "method": "tools/call",    // ③ 调用的方法名（点号分隔的命名空间）
    "params": {                // ④ 方法参数（可选）
        "name": "get_weather",
        "arguments": {"city": "北京"}
    }
}
```

> JSON-RPC 的哲学是 "少即是多"——它不规定 URI 设计、不规定 HTTP method 语义、不规定状态码。只定义最核心的消息格式和交互模式，把复杂性交给上层协议（如 MCP）去定义。

---

## 二、为什么需要——传输层演进与核心原语设计动机

### 2.1 为什么需要三种传输方式

一种传输方式不够吗？答案是**不够**，因为使用场景差异巨大：

| 场景 | 要求 | 最佳传输方式 |
|------|------|-------------|
| 本地 IDE 插件 ↔ 本地工具 | 低延迟、无网络依赖 | stdio |
| 远程浏览器客户端 ↔ 云端工具 | 能穿透防火墙、支持 HTTP | SSE |
| 生产环境微服务 ↔ 工具集群 | 高可靠、连接可恢复、弹性伸缩 | Streamable HTTP |

#### 2.1.1 stdio 的 "简单美"

stdio（标准输入输出）是最简单的进程间通信方式：父进程启动子进程，通过 stdin 写入请求，stdout 读取响应。

```
┌──────────────────┐  stdin (JSON-RPC Request)
│  Host Process    │ ──────────────────────────> ┌──────────────────┐
│  (Claude Desktop)│                              │  MCP Server      │
│                  │ <────────────────────────── │  Process         │
└──────────────────┘  stdout (JSON-RPC Response)  └──────────────────┘
```

**优势：**
- 零网络配置——不需要端口、不需要防火墙规则
- 天然安全——只有父进程能跟子进程通信
- 调试简单——可以直接在终端看到输入输出

**局限：**
- 只能本地通信，无法远程访问
- 进程崩溃即连接断开，无法恢复
- 一对一的，无法支撑多客户端场景

#### 2.1.2 SSE 的 "服务端推送能力"

SSE（Server-Sent Events）在 HTTP 之上提供了服务端向客户端推送事件的能力。

```
┌──────────┐   GET /mcp HTTP/1.1             ┌──────────┐
│  Client  │   Accept: text/event-stream      │  Server  │
│          │ ────────────────────────────────> │          │
│          │                                   │          │
│          │   HTTP/1.1 200 OK                 │          │
│          │   Content-Type: text/event-stream │          │
│          │ <──────────────────────────────── │          │
│          │                                   │          │
│          │   event: message                  │          │
│          │   data: {"jsonrpc":"2.0",...}     │          │
│          │ <──────────────────────────────── │  (持续推送)
│          │                                   │          │
│          │   event: progress                 │          │
│          │   data: {"progress":50,...}       │          │
│          │ <──────────────────────────────── │          │
```

**SSE 的关键特性：**
- 单向推送：Server → Client，Client 的请求仍通过普通 HTTP POST 发送
- 自动重连：浏览器原生 SSE API 支持断线自动重连
- 事件类型：支持 `message`、`progress`、`error` 等自定义事件类型

**SSE 的局限与 Streamable HTTP 的诞生：**

SSE 的一个核心问题是**连接不可恢复**——如果 SSE 长连接断开，Client 必须重新发起 HTTP POST 请求获取新数据。这在移动网络或负载均衡器环境下频繁发生。

此外，SSE 要求 Server 为每个 Client 维护一个长连接，当 Client 数量激增时（比如一个有数万 AI 用户的 SaaS 平台），Server 的连接压力会非常大。

#### 2.1.3 Streamable HTTP——"鱼和熊掌兼得"

Streamable HTTP 是 **2025 年新增的默认传输方式**，它融合了 stdio 的简单性和 SSE 的流式能力，同时解决了后者的痛点。

```
┌──────────┐                              ┌──────────┐
│  Client  │                              │  Server  │
└────┬─────┘                              └────┬─────┘
     │                                         │
     │  POST /mcp HTTP/1.1                     │
     │  Accept: application/json, text/event-stream
     │  {"jsonrpc":"2.0","method":"tools/call",...}
     │ ────────────────────────────────────────> │
     │                                         │
     │  HTTP/1.1 200 OK                        │
     │  Content-Type: text/event-stream        │
     │  (流式返回工具执行结果)                    │
     │ <──────────────────────────────────────  │
     │                                         │
     │  (连接可以在任意请求后关闭，下次请求新建)    │
     │                                         │
     │  GET /mcp HTTP/1.1                      │
     │  Accept: text/event-stream              │
     │ ────────────────────────────────────────> │
     │  (重新建立 SSE 流，接收 Server 推送)       │
     │ <======================================  │
```

**Streamable HTTP 的核心改进：**

| 特性 | SSE | Streamable HTTP |
|------|-----|-----------------|
| 连接可恢复性 | 断开后需完整重建 | 请求间无状态，任意重组 |
| Server 连接压力 | 每 Client 一个长连接 | 按需建立，可池化 |
| 双向流支持 | 单向推送 + 独立 POST | 统一在 HTTP 上双向流 |
| 模式灵活性 | 仅 Stateful | 支持 Stateless 和 Stateful 两种模式 |
| 负载均衡友好 | 需要 sticky session | 无状态请求可任意路由 |

### 2.2 为什么需要四大核心原语

从第一模块我们知道 MCP 有三种基础原语（Tools / Resources / Prompts），但规范中实际上定义了**四种核心原语**，第四种是 **Sampling（采样）**。

为什么需要四种而不是一种或十种？这源于对 "LLM 与外部交互" 场景的完整抽象：

```
LLM 的四种外部交互需求：

┌─────────────────────────────────────────────────────┐
│                                                     │
│   ① 我需要执行一个操作 → Tools                       │
│      例："查一下北京的天气"                           │
│                                                     │
│   ② 我需要读取一些数据 → Resources                   │
│      例："打开 /docs/report.pdf 看看里面有什么"       │
│                                                     │
│   ③ 我需要一个高质量的引导词 → Prompts               │
│      例："用代码审查模板帮我审查这段代码"              │
│                                                     │
│   ④ 我需要让 LLM 帮我生成内容 → Sampling             │
│      例："Server 先生成摘要，再让 LLM 根据摘要回答"   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

四种原语覆盖了交互方向的完整矩阵：

| 原语 | 谁发起 | 数据流向 | 代表操作 |
|------|--------|----------|----------|
| **Tools** | LLM 决定调用 | Client → Server → Client | 写操作、执行动作 |
| **Resources** | Client 读取 | Server → Client | 读操作、获取上下文 |
| **Prompts** | 用户选择 | Server → Client → LLM | 模板化的交互指令 |
| **Sampling** | Server 请求 | Server → Client → LLM → Client → Server | 反向请求 LLM 生成 |

---

## 三、如何实现——传输机制与原语详解

### 3.1 stdio 传输实现

#### 工作原理

stdio 传输通过操作系统的标准输入输出流进行通信。Host 作为父进程启动 MCP Server 作为子进程。

```python
# Client 端 (通过 subprocess 启动 Server)
import subprocess
import json

class StdioClientTransport:
    def __init__(self, command: list[str]):
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE  # Server 的日志走 stderr，不影响协议通信
        )

    def send(self, message: dict) -> None:
        """发送 JSON-RPC 消息到 Server"""
        payload = json.dumps(message) + "\n"
        self.process.stdin.write(payload.encode("utf-8"))
        self.process.stdin.flush()

    def receive(self) -> dict:
        """从 Server 读取 JSON-RPC 响应"""
        line = self.process.stdout.readline()
        return json.loads(line.decode("utf-8"))

    def close(self):
        self.process.terminate()
        self.process.wait()
```

#### 消息分帧

stdio 传输使用**换行符分帧**（newline-delimited JSON），即每个 JSON-RPC 消息后跟一个 `\n`：

```
{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n
{"jsonrpc":"2.0","id":1,"result":{"tools":[...]}}\n
{"jsonrpc":"2.0","method":"notifications/initialized"}\n
```

> 注意：JSON 内部不能包含未转义的换行符，否则会破坏分帧。这意味着所有 JSON-RPC 消息必须是单行 JSON，不能 pretty-print。

### 3.2 SSE 传输实现

#### 架构

SSE 传输使用两个 HTTP 端点：

```
POST /mcp  →  Client 向 Server 发送 JSON-RPC 请求
GET  /mcp  →  Server 向 Client 推送 SSE 事件流
GET  /health → (可选) 健康检查端点
```

#### Client 端实现

```python
import httpx
import json
import asyncio

class SSEClientTransport:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.message_id = 0
        self.pending_requests: dict[int, asyncio.Future] = {}

    async def connect(self):
        """建立 SSE 连接，开始接收服务端推送"""
        self.sse_client = httpx.AsyncClient(timeout=None)
        async with self.sse_client.stream("GET", f"{self.base_url}/mcp") as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    data = json.loads(line[6:])
                    await self._handle_message(data)

    async def send(self, method: str, params: dict = None) -> dict:
        """发送 JSON-RPC 请求并等待响应"""
        self.message_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.message_id,
            "method": method,
            "params": params or {}
        }

        # 创建 Future 等待响应
        future = asyncio.get_event_loop().create_future()
        self.pending_requests[self.message_id] = future

        # 通过 HTTP POST 发送请求
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{self.base_url}/mcp",
                json=request,
                headers={"Content-Type": "application/json"}
            )

        return await future

    async def _handle_message(self, data: dict):
        """处理来自 SSE 流的消息"""
        if "id" in data and data["id"] in self.pending_requests:
            # 这是对某个请求的响应
            future = self.pending_requests.pop(data["id"])
            if "result" in data:
                future.set_result(data["result"])
            elif "error" in data:
                future.set_exception(Exception(data["error"]))
        else:
            # 这是 Server 的主动通知
            await self._handle_notification(data)
```

#### Server 端实现

```python
from starlette.applications import Starlette
from starlette.responses import StreamingResponse
from starlette.routing import Route
import asyncio
import json

class SSEServerTransport:
    def __init__(self):
        self.event_queues: dict[str, asyncio.Queue] = {}  # session_id → event queue

    async def handle_post(self, request):
        """处理 Client 发来的 JSON-RPC 请求"""
        body = await request.json()
        session_id = request.headers.get("X-Session-Id", "default")

        # 执行请求，获取结果
        result = await self._execute_method(body["method"], body.get("params", {}))

        # 构造响应，放入事件队列通过 SSE 推送回去
        response = {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": result
        }
        await self.event_queues.setdefault(session_id, asyncio.Queue()).put(response)

        return JSONResponse({"status": "accepted"})

    async def handle_get(self, request):
        """建立 SSE 流，持续推送事件给 Client"""
        session_id = request.query_params.get("session", "default")
        queue = self.event_queues.setdefault(session_id, asyncio.Queue())

        async def event_generator():
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event)}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # 禁用 Nginx 缓冲
            }
        )
```

#### SSE 常见排障点

| 问题 | 原因 | 解决方案 |
|------|------|----------|
| SSE 连接频繁断开 | Nginx/负载均衡器有超时限制 | 增加 `proxy_read_timeout`；Server 定期发送 heartbeat 注释行 |
| 事件接收不完整 | Nginx 启用了响应缓冲 | 设置 `proxy_buffering off;` 和 `X-Accel-Buffering: no` |
| 跨域请求被拒 | Server 未配置 CORS | SSE 响应头中添加 `Access-Control-Allow-Origin` |

### 3.3 Streamable HTTP 传输实现

#### 两种模式

Streamable HTTP 支持两种运行模式：

**Stateless 模式（无状态）：**
```
每个 HTTP 请求都是独立的。Client 发 POST，Server 返回响应后连接关闭。
下一个请求可以是全新的 HTTP 连接。

适用场景：Serverless 部署、FaaS（Function as a Service）
```

**Stateful 模式（有状态）：**
```
Client 与 Server 之间维护 Session。Server 可以在 Session 期间
通过 Server→Client 方向推送通知（在响应流中持续输出）。

适用场景：需要 Server 主动推送的场景（资源变更通知等）
```

#### 完整实现

```python
import asyncio
import json
import uuid
from aiohttp import web

class StreamableHTTPTransport:
    """Streamable HTTP 传输的 Server 端实现"""

    def __init__(self):
        self.sessions: dict[str, dict] = {}  # session_id → session state
        self.subscriptions: dict[str, set[str]] = {}  # uri → set of session_ids

    async def handle_request(self, request: web.Request) -> web.Response:
        """统一处理入口"""
        session_id = request.headers.get("Mcp-Session-Id")

        # 判断 Client 想要什么响应模式
        accept_header = request.headers.get("Accept", "application/json")

        if "text/event-stream" in accept_header:
            # Client 希望接收流式响应
            return await self._handle_streaming(request, session_id)
        else:
            # Client 只需要普通 JSON 响应
            return await self._handle_json(request, session_id)

    async def _handle_json(self, request, session_id) -> web.Response:
        """处理普通 JSON 响应（Stateless 模式）"""
        body = await request.json()
        result = await self._execute_method(body["method"], body.get("params", {}))

        return web.json_response({
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": result
        })

    async def _handle_streaming(self, request, session_id) -> web.StreamResponse:
        """处理流式响应（Stateful 模式）"""
        body = await request.json()

        # 准备 SSE 流式响应
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "Connection": "keep-alive"
            }
        )
        await response.prepare(request)

        # 执行方法
        tool_name = body["params"]["name"]
        arguments = body["params"]["arguments"]

        try:
            # 流式执行工具，每有进展就推送
            async for chunk in self._execute_tool_streaming(tool_name, arguments):
                event_data = json.dumps({
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {"content": [{"type": "text", "text": chunk}]}
                })
                await response.write(f"data: {event_data}\n\n".encode())

            # 发送完成信号
            await response.write(
                f"data: {json.dumps({'jsonrpc': '2.0', 'id': body.get('id'), 'result': {'content': [], 'isError': False}})}\n\n".encode()
            )

        except Exception as e:
            error_data = json.dumps({
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": {
                    "content": [{"type": "text", "text": str(e)}],
                    "isError": True
                }
            })
            await response.write(f"data: {error_data}\n\n".encode())

        return response

    async def _execute_tool_streaming(self, name: str, args: dict):
        """模拟流式工具执行"""
        # 实际场景中，这可能是逐行读取大文件、分页查询数据库等
        for i in range(1, 6):
            await asyncio.sleep(0.5)  # 模拟耗时操作
            yield f"[步骤 {i}/5] 正在处理 {name}({args}) ..."

    async def send_notification(self, session_id: str, notification: dict):
        """
        在 Stateful 模式下，Server 可以主动向 Client 推送通知。
        这通常用于资源变更通知 —— 当被订阅的资源发生变化时，
        Server 通过已建立的 SSE 流推送 notifications/resources/updated。
        """
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if "response" in session:  # 如果有活跃的 SSE 流式响应
                response = session["response"]
                payload = json.dumps(notification)
                await response.write(f"data: {payload}\n\n".encode())
```

### 3.4 四大核心原语详解

#### 3.4.1 Tools（工具）—— 深度剖析

**完整的 Tool 定义结构：**

```python
from typing import Literal
from pydantic import BaseModel

class Tool(BaseModel):
    """MCP Tool 的完整定义"""
    name: str                              # 工具唯一标识符，如 "get_weather"
    description: str | None = None         # 人类可读的工具描述（LLM 据此判断何时调用）
    inputSchema: dict                      # JSON Schema 格式的参数定义
    annotations: ToolAnnotations | None = None  # 工具元信息

class ToolAnnotations(BaseModel):
    """工具的行为注解"""
    title: str | None = None               # 人类可读的标题
    readOnlyHint: bool | None = None       # 提示：是否为只读操作
    destructiveHint: bool | None = None    # 提示：是否为破坏性操作
    idempotentHint: bool | None = None     # 提示：是否为幂等操作
    openWorldHint: bool | None = None      # 提示：是否可能访问外部世界
```

**Annotations 的作用：** Host 可以根据这些注解做出安全决策。例如，如果 `destructiveHint: true`，Host 可以在执行前弹出二次确认对话框。

**Tool 调用结果的完整结构：**

```python
class CallToolResult(BaseModel):
    """工具调用结果"""
    content: list[TextContent | ImageContent | AudioContent | EmbeddedResource]
    isError: bool = False       # 标记业务执行是否出错
    structuredContent: dict | None = None  # 结构化输出（需 Server 声明 support_structured_output）
    _meta: dict | None = None   # 元数据（如执行耗时、token 消耗）
```

**Content 类型的多样性：**

```python
# 文本内容
TextContent(type="text", text="北京今天晴，气温25°C")

# 图片内容
ImageContent(type="image", data="base64_encoded_image...", mimeType="image/png")

# 音频内容
AudioContent(type="audio", data="base64_encoded_audio...", mimeType="audio/wav")

# 嵌入资源
EmbeddedResource(
    type="resource",
    resource={
        "uri": "file:///data/chart.png",
        "mimeType": "image/png",
        "text": "这是一张2024年销售数据柱状图..."  # 资源文本描述（供 LLM 理解）
    }
)
```

> MCP 支持多模态内容返回——工具不仅能返回文本，还能返回图片、音频和嵌入资源。这意味着 MCP 天然支持多模态 AI 应用场景。

#### 3.4.2 Resources（资源）—— 深度剖析

**Resource 的完整定义：**

```python
class Resource(BaseModel):
    """资源定义"""
    uri: str                        # 资源的唯一标识 URI
    name: str                       # 人类可读的名称
    description: str | None = None  # 描述
    mimeType: str | None = None     # MIME 类型，如 "text/plain", "image/png"
    size: int | None = None         # 资源大小（字节），可选
    annotations: Annotations | None = None  # 注解
```

**资源模板（Resource Templates）：**

对于参数化的资源访问，MCP 提供了资源模板机制：

```python
# 定义模板：通过参数化的 URI 访问数据
@server.list_resource_templates()
async def list_templates() -> list[ResourceTemplate]:
    return [
        ResourceTemplate(
            uriTemplate="db://users/{user_id}/profile",    # URI 模板
            name="用户资料",
            description="获取指定用户的详细资料",
            mimeType="application/json"
        ),
        ResourceTemplate(
            uriTemplate="db://projects/{project_id}/members",
            name="项目成员列表",
            description="获取指定项目的所有成员信息"
        )
    ]

# Client 通过 resources/read 请求具体 URI
# 例：resources/read { uri: "db://users/42/profile" }
```

**资源订阅的完整实现：**

```python
class ResourceServer:
    def __init__(self):
        self._watchers: dict[str, list[str]] = {}  # uri → [session_ids]
        self._resource_cache: dict[str, ResourceContent] = {}

    async def subscribe(self, uri: str, session_id: str):
        """订阅资源变更"""
        if uri not in self._watchers:
            self._watchers[uri] = []
            await self._start_watching(uri)  # 启动文件监控/数据库轮询等
        self._watchers[uri].append(session_id)

    async def unsubscribe(self, uri: str, session_id: str):
        """取消订阅"""
        if uri in self._watchers:
            self._watchers[uri].remove(session_id)
            if not self._watchers[uri]:
                await self._stop_watching(uri)

    async def _on_resource_changed(self, uri: str, new_content: ResourceContent):
        """资源变更回调 —— 通知所有订阅者"""
        self._resource_cache[uri] = new_content
        for session_id in self._watchers.get(uri, []):
            await self._send_notification(session_id, {
                "jsonrpc": "2.0",
                "method": "notifications/resources/updated",
                "params": {"uri": uri}
            })

    async def read(self, uri: str) -> ResourceContent:
        """读取资源内容"""
        if uri in self._resource_cache:
            return self._resource_cache[uri]
        return await self._load_resource(uri)
```

**ListChanged 通知：** Client 可以声明 `resources.listChanged` 能力，当 Server 端的资源列表发生变化时（如新增了文件监控目录），Server 会推送 `notifications/resources/list_changed` 通知。

#### 3.4.3 Prompts（提示词模板）—— 深度剖析

**Prompt 的完整结构：**

```python
class Prompt(BaseModel):
    """提示词模板定义"""
    name: str                              # 模板唯一名称
    description: str | None = None         # 人类可读的描述
    arguments: list[PromptArgument] | None = None  # 可填充的参数列表

class PromptArgument(BaseModel):
    """提示词参数"""
    name: str                              # 参数名
    description: str | None = None         # 参数说明
    required: bool | None = False          # 是否必填
    completions: list[str] | None = None   # 建议值列表（供 UI 下拉选择）

class GetPromptResult(BaseModel):
    """提示词填充结果"""
    description: str | None = None         # 结果描述
    messages: list[PromptMessage]          # 填充后的消息列表

class PromptMessage(BaseModel):
    """提示词中的一条消息"""
    role: Literal["user", "assistant"]     # 消息角色
    content: TextContent | ImageContent | AudioContent | EmbeddedResource
```

**Message 的角色设计哲学：** Prompt 中只能有 `user` 和 `assistant` 两种角色，没有 `system` 角色。这是因为：
- `system` 提示通常由 Host 控制，不应由 MCP Server 注入
- 保持安全边界——外部 Server 不应该能修改系统级指令

**实战示例——完整的代码审查 Prompt：**

```python
@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    return [
        Prompt(
            name="code_review",
            description="对代码进行全面的专业审查，涵盖正确性、安全性、性能和可维护性",
            arguments=[
                PromptArgument(
                    name="language",
                    description="编程语言（如 Python, TypeScript, Go）",
                    required=True,
                    completions=["Python", "TypeScript", "Go", "Java", "Rust"]
                ),
                PromptArgument(
                    name="code",
                    description="需要被审查的代码，建议粘贴完整函数或文件",
                    required=True
                ),
                PromptArgument(
                    name="focus",
                    description="审查的侧重点",
                    required=False,
                    completions=["全面审查", "安全性优先", "性能优先", "代码风格"]
                )
            ]
        ),
    ]

@server.get_prompt()
async def get_prompt(name: str, arguments: dict) -> GetPromptResult:
    if name == "code_review":
        focus = arguments.get("focus", "全面审查")
        return GetPromptResult(
            description=f"对 {arguments['language']} 代码进行{focus}",
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""你是一位资深的 {arguments['language']} 代码审查专家。请对以下代码进行 {focus}。

审查要求：
1. **代码正确性**：逻辑是否有缺陷？边界条件是否覆盖？
2. **安全性**：是否存在 OWASP Top 10 中的常见漏洞？
3. **性能**：是否存在不必要的循环、重复计算或内存泄漏？
4. **可维护性**：命名是否清晰？函数是否过于复杂？是否有足够的注释？
5. **最佳实践**：是否符合 {arguments['language']} 社区的最佳实践和惯用法？

对于每个发现的问题，请按以下格式输出：
- 🔴 严重：...
- 🟡 建议：...
- 🟢 优点：...

待审查代码：
```{arguments['language']}
{arguments['code']}
```"""
                    )
                )
            ]
        )
```

#### 3.4.4 Sampling（采样）—— 反向请求 LLM

**Sampling 是什么：**

Sampling 是四个原语中最特殊的一个——它允许 **Server 主动请求 LLM 生成内容**。这打破了传统的 "Client 请求 → Server 响应" 单向模式。

```
标准流程：           User → LLM → Client → Server → Client → LLM → User

Sampling 流程：     User → LLM → Client → Server
                                        │
                             Server → Client → LLM（LLM 生成内容）
                                        │
                             Server ← Client ← LLM
                                        │
                             Server → Client → LLM → User
```

**为什么需要 Sampling？**

| 场景 | 说明 |
|------|------|
| **智能摘要** | Server 拿到一大段数据，让 LLM 先做摘要再处理 |
| **内容生成** | Server 需要让 LLM 生成一些文本用于后续处理 |
| **多步骤推理** | Server 在中间步骤让 LLM 做一些判断或推理 |

**Sampling 的完整实现：**

```python
# Server 端 —— 发起 Sampling 请求
@server.call_tool()
async def analyze_document(name: str, arguments: dict) -> list[TextContent]:
    if name == "analyze_long_document":
        # 1. 获取文档全文
        doc_text = await fetch_document(arguments["document_id"])

        # 2. 如果文档太长，先让 LLM 做摘要（使用 Sampling）
        if len(doc_text) > 10000:
            summary = await server.create_message(
                messages=[
                    SamplingMessage(
                        role="user",
                        content=TextContent(
                            type="text",
                            text=f"请用 300 字以内总结以下文档的核心内容：\n\n{doc_text}"
                        )
                    )
                ],
                max_tokens=500,
                temperature=0.3,
                # 可以指定模型偏好
                modelPreferences=ModelPreferences(
                    hints=[ModelHint(name="claude-sonnet-4-6")],
                    costPriority=0.8,   # 成本权重（0-1）
                    speedPriority=0.3,  # 速度权重
                    intelligencePriority=0.9  # 智能程度权重
                )
            )
            # summary 包含 LLM 生成的摘要
            doc_summary = summary.content

        # 3. 基于摘要做进一步分析
        # ...

# Client 端 —— 处理 Server 的 Sampling 请求
class MCPClient:
    async def _handle_sampling_request(self, request: dict):
        """Client 收到 Server 的 sampling/createMessage 请求"""
        messages = request["params"]["messages"]
        max_tokens = request["params"]["max_tokens"]

        # Client 将请求转发给 LLM
        llm_response = await self.llm.generate(
            messages=messages,
            max_tokens=max_tokens,
            temperature=request["params"].get("temperature", 0.7)
        )

        return {
            "role": "assistant",
            "content": TextContent(type="text", text=llm_response),
            "model": llm_response.model,
            "stopReason": llm_response.stop_reason
        }
```

**Sampling 的安全考量：**

Sampling 是一个需要格外谨慎的能力，因为它让外部 Server 间接控制了 LLM 的行为。Host 通常需要：

1. **弹出用户确认对话框**—— "Server X 请求让 LLM 生成内容，是否允许？"
2. **限制 token 数量**—— 防止 Server 通过 Sampling 消耗大量 token
3. **审查消息内容**—— 检查 Server 发送给 LLM 的提示词是否包含敏感信息

---

## 四、底层原理——JSON-RPC 消息格式与能力协商

### 4.1 JSON-RPC 消息类型完整规范

#### 四种消息类型

```
JSON-RPC 2.0 消息分类

┌─────────────────────────────────────────────────┐
│                   有 id 字段                      │
│         ┌─────────────────────────┐             │
│         │       Request           │             │
│         │  Client → Server        │             │
│         │  期待 Response 或 Error  │             │
│         └─────────────────────────┘             │
│                                                 │
│         ┌─────────────────────────┐             │
│         │       Response          │             │
│         │  Server → Client        │             │
│         │  携带 result 字段        │             │
│         └─────────────────────────┘             │
│                                                 │
│         ┌─────────────────────────┐             │
│         │       Error             │             │
│         │  Server → Client        │             │
│         │  携带 error 对象         │             │
│         └─────────────────────────┘             │
├─────────────────────────────────────────────────┤
│                   无 id 字段                      │
│         ┌─────────────────────────┐             │
│         │     Notification        │             │
│         │  双向均可发送             │             │
│         │  不需要对方响应           │             │
│         └─────────────────────────┘             │
└─────────────────────────────────────────────────┘
```

#### 错误码完整定义

| 错误码 | 常量名 | 含义 | 示例 |
|--------|--------|------|------|
| `-32700` | Parse Error | JSON 解析失败 | `{"invalid json` |
| `-32600` | Invalid Request | 不是合法的 JSON-RPC 请求 | 缺少 `jsonrpc` 字段 |
| `-32601` | Method Not Found | 方法不存在 | 调用了 `tools/nonexistent` |
| `-32602` | Invalid Params | 参数无效 | 缺少必填参数 |
| `-32603` | Internal Error | Server 内部错误 | 未捕获的异常 |
| `-32000` ~ `-32099` | Server Error (reserved) | 应用层自定义错误 | 自定义业务异常 |

#### 批量请求（Batch Request）

JSON-RPC 2.0 支持批量发送多个请求：

```json
// Client 一次性发送多个请求
[
    {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    {"jsonrpc": "2.0", "id": 2, "method": "resources/list"},
    {"jsonrpc": "2.0", "id": 3, "method": "prompts/list"}
]

// Server 返回对应顺序的响应数组
[
    {"jsonrpc": "2.0", "id": 1, "result": {"tools": [...]}},
    {"jsonrpc": "2.0", "id": 2, "result": {"resources": [...]}},
    {"jsonrpc": "2.0", "id": 3, "result": {"prompts": [...]}}
]
```

> MCP 目前**不建议**使用批量请求，因为 stdio 传输的处理模型是顺序的，批量请求可能引入并发问题。但 Streamable HTTP 的未来版本可能会更好地支持批量请求。

### 4.2 能力协商机制深度解析

#### 什么是能力协商（Capability Negotiation）

能力协商是 MCP 协议中一个**贯穿所有交互**的核心机制：Client 和 Server 在初始化和每次交互中声明自己具备的能力，双方按照 "最小交集" 原则确定可用的功能集。

```
Client 能力声明                 Server 能力声明
┌──────────────────┐          ┌──────────────────┐
│ roots.listChanged │          │ tools             │
│ sampling          │          │ resources.subscribe│
│ experimental.x    │          │ prompts           │
└────────┬─────────┘          └────────┬─────────┘
         │                             │
         └──────────┬──────────────────┘
                    │
         ┌──────────▼──────────┐
         │   协商后的能力交集     │
         │   tools             │
         │   prompts           │
         │   roots.listChanged (Client 独有能力)│
         └─────────────────────┘
```

#### Client 端能力声明（ClientCapabilities）

```python
class ClientCapabilities(BaseModel):
    """Client 在 initialize 请求中声明的能力"""
    roots: RootsCapability | None = None
    sampling: SamplingCapability | None = None
    elicitation: ElicitationCapability | None = None
    experimental: dict[str, dict] | None = None  # 实验性功能

class RootsCapability(BaseModel):
    """Client 支持的根目录相关能力"""
    listChanged: bool | None = None  # 是否支持监听根目录列表变更

class SamplingCapability(BaseModel):
    """Client 是否支持 Sampling（让 Server 反向请求 LLM）"""
    # 如果存在此对象即表示支持，无需额外字段
    pass

class ElicitationCapability(BaseModel):
    """Client 是否支持引导模式（让 Server 向用户提问）"""
    pass
```

#### Server 端能力声明（ServerCapabilities）

```python
class ServerCapabilities(BaseModel):
    """Server 在 initialize 响应中声明的能力"""
    tools: ToolsCapability | None = None
    resources: ResourcesCapability | None = None
    prompts: PromptsCapability | None = None
    logging: LoggingCapability | None = None
    experimental: dict[str, dict] | None = None

class ToolsCapability(BaseModel):
    """工具相关能力"""
    listChanged: bool | None = None  # 工具列表是否会变化（影响 Client 缓存策略）
    support_structured_output: bool | None = None  # 是否支持结构化输出

class ResourcesCapability(BaseModel):
    """资源相关能力"""
    subscribe: bool | None = None    # 是否支持资源订阅
    listChanged: bool | None = None  # 资源列表是否会变化

class PromptsCapability(BaseModel):
    """提示词相关能力"""
    listChanged: bool | None = None  # 提示词列表是否会变化

class LoggingCapability(BaseModel):
    """日志相关能力"""
    pass  # Server 声明后 Client 可通过 logging/setLevel 设置日志级别
```

#### 能力协商的完整流程

```
阶段一：初始化协商 (Initialize)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Client → Server: initialize {
    "protocolVersion": "2025-03-26",
    "capabilities": {
        "roots": {"listChanged": true},
        "sampling": {}
    },
    "clientInfo": {"name": "my-client", "version": "1.0.0"}
}

Server → Client: initialize {
    "protocolVersion": "2025-03-26",
    "capabilities": {
        "tools": {"listChanged": false, "support_structured_output": true},
        "resources": {"subscribe": true, "listChanged": true},
        "prompts": {"listChanged": false}
    },
    "serverInfo": {"name": "my-server", "version": "2.0.0"}
}

协商结果：
  ✓ 双方协议版本一致
  ✓ Server 提供 tools/resources/prompts（Client 无需声明即可使用）
  ✓ Client 支持 sampling（Server 可以请求 LLM 生成内容）
  ✓ Server 支持 resources.subscribe（Client 可以订阅资源变更）

阶段二：运行时中的隐式协商
━━━━━━━━━━━━━━━━━━━━━━━━━

当 Client 请求 tools/call 时：
  - 如果 Server 声明了 support_structured_output，Client 可以期待结构化结果
  - 如果 Server 未声明，Client 不应期待 structuredContent 字段

当 Client 请求 resources/subscribe 时：
  - 如果 Server 声明了 subscribe: true，请求正常执行
  - 如果 Server 未声明 subscribe，Client 不应发送此请求
```

#### 渐进式能力声明（Progressive Capability Declaration）

从 2025 年 3 月 26 日版本开始，MCP 支持**渐进式能力声明**：Client 和 Server 可以在运行时通过通知更新自己的能力声明，而不需要重新初始化连接。

```json
// Client 在运行时新增能力声明
{
    "jsonrpc": "2.0",
    "method": "notifications/capabilities/updated",
    "params": {
        "capabilities": {
            "elicitation": {}  // 新增：支持引导模式
        }
    }
}
```

这种设计支持了**动态加载插件**和**运行时升级**等场景。

### 4.3 通知机制（Notification System）

MCP 的通知机制是协议中一个重要的设计——它允许一方在不期待回复的情况下向另一方推送信息。

#### 所有标准通知类型

```
MCP 标准通知分类

┌─────────────────────────────────────────────────────┐
│              连接生命周期通知                          │
│  initialized          → Client 初始化完成             │
│  capabilities/updated → 能力声明变更                  │
├─────────────────────────────────────────────────────┤
│              工具相关通知                              │
│  tools/list_changed   → Server 的工具列表发生变更      │
├─────────────────────────────────────────────────────┤
│              资源相关通知                              │
│  resources/list_changed → 资源列表变更                │
│  resources/updated       → 指定资源内容变更            │
├─────────────────────────────────────────────────────┤
│              提示词相关通知                            │
│  prompts/list_changed → 提示词模板列表变更             │
├─────────────────────────────────────────────────────┤
│              进度通知                                  │
│  progress             → 长时间操作进度更新             │
│  (携带 progressToken + progress + total)            │
├─────────────────────────────────────────────────────┤
│              日志通知                                  │
│  logging/message      → Server 发送日志给 Client      │
├─────────────────────────────────────────────────────┤
│              取消通知                                  │
│  cancelled            → 通知某操作已被取消             │
└─────────────────────────────────────────────────────┘
```

#### 进度通知（Progress Notification）

```python
# Server 端：在执行长时间操作时发送进度通知
async def execute_long_task(self, progress_token: str):
    total_steps = 100
    for i in range(total_steps):
        await self._do_work()
        await self._send_progress(progress_token, i + 1, total_steps)

async def _send_progress(self, token: str, progress: int, total: int):
    await self.send_notification({
        "jsonrpc": "2.0",
        "method": "notifications/progress",
        "params": {
            "progressToken": token,
            "progress": progress,
            "total": total,
            "message": f"处理中... {progress}/{total}"
        }
    })
```

> 进度通知是解决传统 Function Calling "工具执行黑盒" 问题的关键机制。用户在 AI 应用中可以看到实时进度条，而不是对着空白等待。

#### 取消通知（Cancelled Notification）

```python
# Client 发送取消请求
async def cancel_operation(self, request_id: int, reason: str = "用户取消了操作"):
    await self.send_notification({
        "jsonrpc": "2.0",
        "method": "notifications/cancelled",
        "params": {
            "requestId": request_id,
            "reason": reason
        }
    })

# Server 端处理取消
class CancellableTool:
    def __init__(self):
        self._cancelled_requests: set[int] = set()

    async def on_cancelled(self, request_id: int):
        """接收到取消通知"""
        self._cancelled_requests.add(request_id)

    async def execute(self, request_id: int):
        """在工具执行过程中检查是否被取消"""
        for step in self.steps:
            if request_id in self._cancelled_requests:
                self._cancelled_requests.remove(request_id)
                raise OperationCancelledError(f"操作 {request_id} 已被取消")
            await step()
```

### 4.4 协议版本演进

| 协议版本 | 发布日期 | 关键变化 |
|----------|----------|----------|
| `2024-11-05` | 2024.11.05 | 初始版本，定义 Tools/Resources/Prompts，支持 stdio 和 SSE |
| `2025-03-26` | 2025.03.26 | 新增 Streamable HTTP 默认传输、Elicitation（引导模式）、渐进式能力声明、工具 Annotations |
| `2025-06-18` | 2025.06.18 | 引入 Resource 和 Prompt Annotations、工具执行结果支持 AudioContent、`_meta` 元数据 |

---

## 五、企业级最佳实践

### 5.1 传输方式选择决策树

```
                    部署场景是什么？
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
    纯本地运行      远程访问         生产级微服务
    (IDE插件等)    (浏览器等)       (SaaS 平台)
         │               │               │
         ▼               ▼               ▼
      stdio            SSE          Streamable HTTP
                     (或 HTTP)      (Stateful 模式)
```

**具体建议：**

| 场景 | 推荐传输 | 原因 |
|------|----------|------|
| VS Code / Cursor 插件 | stdio | 低延迟，零网络依赖，天然进程隔离 |
| 内部 Web 工具（<1000 并发） | SSE | 成熟稳定，自动重连，实现简单 |
| SaaS 平台（>1000 并发） | Streamable HTTP | 连接可恢复，兼容 Serverless，负载均衡友好 |
| CI/CD Pipeline 中的工具 | stdio 或 Stateless HTTP | 无需长连接，用完即走 |
| 移动端 AI 应用 | Streamable HTTP | 移动网络不稳定，连接可恢复是关键 |

### 5.2 Architecture 设计模式

#### 模式一：聚合 Server（Aggregator Pattern）

当一个场景涉及多个独立的 MCP Server 时，使用一个聚合 Server 来统一入口。

```
┌─────────────────────────────────────────────┐
│                 AI 应用 (Host)               │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│           Gateway MCP Server                 │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐     │
│  │ Router  │  │ Aggreg. │  │ Cache   │     │
│  └────┬────┘  └─────────┘  └─────────┘     │
└───────┼─────────────────────────────────────┘
        │
   ┌────┼────────┬──────────┐
   ▼    ▼        ▼          ▼
┌────┐ ┌────┐ ┌────┐   ┌────────┐
│ DB │ │API │ │File│   │Search  │
│Svr │ │Svr │ │Svr │   │Svr    │
└────┘ └────┘ └────┘   └────────┘
```

#### 模式二：职责链模式（Chain of Responsibility）

多个 Server 按优先级处理同一类工具，一个不处理则转给下一个。

```python
class ChainMCPClient:
    def __init__(self, servers: list[MCPClientConnection]):
        self.servers = servers

    async def call_tool(self, name: str, args: dict):
        for server in self.servers:
            # 尝试在每个 Server 上调用工具
            tools = await server.list_tools()
            if any(t.name == name for t in tools):
                return await server.call_tool(name, args)
        raise ToolNotFoundError(f"没有 Server 能处理工具: {name}")
```

#### 模式三：缓存代理模式（Caching Proxy）

对于 Resources read 操作，在 Client 和 Server 之间加入缓存层。

```python
class CachingProxyServer:
    def __init__(self, upstream: MCPClientConnection, ttl: int = 60):
        self.upstream = upstream
        self.cache: dict[str, tuple[float, ResourceContent]] = {}  # uri → (expiry, content)
        self.ttl = ttl

    async def read_resource(self, uri: str) -> ResourceContent:
        now = time.time()
        if uri in self.cache:
            expiry, content = self.cache[uri]
            if now < expiry:
                return content  # 缓存命中
        content = await self.upstream.read_resource(uri)
        self.cache[uri] = (now + self.ttl, content)
        return content
```

### 5.3 安全加固清单

```
□ 传输层安全
  □ HTTPS/TLS 加密所有远程通信（SSE 和 Streamable HTTP）
  □ stdio 确认进程启动参数不包含明文密码
  □ 使用 mTLS 进行 Server 身份认证（生产环境）

□ 访问控制
  □ 基于 API Key / JWT Token 进行 Client 认证
  □ 按 session 隔离用户数据（不同的 session_id 看到不同的资源）
  □ 工具级别权限控制（用户 A 可以调用只读工具，用户 B 可以调用所有工具）

□ 输入校验
  □ 所有工具参数使用 JSON Schema 验证（框架层自动处理）
  □ 额外校验：文件路径穿越检查、SQL 注入检查、命令注入检查
  □ URI 校验：确保 Resource URI 不指向敏感路径

□ 资源限制
  □ 工具执行超时（默认 30s，可配置）
  □ 结果大小限制（单次响应 ≤ 10MB）
  □ 令牌消耗限制（Sampling 时限制 max_tokens）
  □ 并发调用限制（每个 session 同时最多 N 个 tool call）

□ 审计日志
  □ 记录所有 tools/call 请求（谁、什么时候、调了什么工具、参数、结果）
  □ 记录所有 resources/read 请求
  □ 记录 Sampling 请求（涉及 LLM token 消耗）
  □ 日志包含 session_id、user_id、timestamp
```

### 5.4 排障指南

#### 常见问题速查

| 症状 | 可能原因 | 排查命令/方法 |
|------|----------|--------------|
| 连接建立失败 | 协议版本不兼容 | 检查 initialize 请求中的 protocolVersion |
| 工具调用超时 | Server 执行耗时过长 | 检查工具执行日志；设置合理的超时时间 |
| SSE 连接频繁断开 | 反向代理超时 | 检查 Nginx `proxy_read_timeout`；添加 heartbeat |
| 资源读取返回空 | URI 格式错误 | 检查 URI scheme 是否正确注册 |
| 进度通知不显示 | Client 未处理 progress notification | 确认 Client 的 Notification handler 已注册 |
| 批量请求乱序 | stdio 不支持并发 | 使用 Streamable HTTP 替代 |

#### 调试技巧

```python
# 1. 开启 MCP 协议日志
import logging
logging.getLogger("mcp").setLevel(logging.DEBUG)

# 2. 使用 MCP Inspector 调试（Anthropic 官方工具）
# npx @anthropic-ai/mcp-inspector <command>
# 这会启动一个 Web UI，可以交互式测试 MCP Server

# 3. 截获并打印原始 JSON-RPC 消息
class DebugTransport:
    def __init__(self, wrapped_transport):
        self.wrapped = wrapped_transport

    async def send(self, message: dict):
        print(f"[MCP →] {json.dumps(message, ensure_ascii=False)}")
        return await self.wrapped.send(message)

    async def receive(self) -> dict:
        response = await self.wrapped.receive()
        print(f"[MCP ←] {json.dumps(response, ensure_ascii=False)}")
        return response
```

---

## 六、常见面试题

### 传输层

**Q1: MCP 支持哪三种传输方式？各自的适用场景是什么？**

<details>
<summary>参考答案</summary>

| 传输方式 | 适用场景 | 典型部署 |
|----------|----------|----------|
| **stdio** | 本地进程间通信 | IDE 插件 ↔ 本地工具 |
| **SSE** | 需要服务端推送的远程通信 | Web 客户端 ↔ 云端工具 |
| **Streamable HTTP** | 生产环境高可靠性要求 | SaaS 平台、微服务架构 |

Streamable HTTP 是 2025 年新增的默认传输方式，解决了 SSE 连接不可恢复和 Session 管理复杂的问题。

</details>

---

**Q2: Streamable HTTP 相比 SSE 解决了哪些核心问题？**

<details>
<summary>参考答案</summary>

1. **连接可恢复性**：Streamable HTTP 的每个请求可以走不同的 TCP 连接，SSE 断开后需要完整重建
2. **Server 连接压力**：Streamable HTTP 无需为每个 Client 维护长连接，适合大规模部署
3. **负载均衡友好**：无状态请求可被任意路由，SSE 需要 sticky session
4. **模式灵活性**：支持 Stateless（FaaS 友好）和 Stateful（需要推送时）两种模式

</details>

---

### 核心原语

**Q3: MCP 的四大核心原语是什么？各自解决什么问题？**

<details>
<summary>参考答案</summary>

| 原语 | 解决的问题 | 控制方 | 数据流向 |
|------|-----------|--------|----------|
| **Tools** | LLM 需要执行操作（查数据、发邮件） | LLM | Client → Server → Client |
| **Resources** | LLM 需要读取上下文（文件、数据库） | Client | Server → Client |
| **Prompts** | 提供标准化的交互模板 | 用户 | Server → Client → LLM |
| **Sampling** | Server 需要反向请求 LLM 生成内容 | Server | Server → Client → LLM → Client → Server |

</details>

---

**Q4: Tools 和 Resources 的本质区别是什么？为什么不能合二为一？**

<details>
<summary>参考答案</summary>

**本质区别：**

| 维度 | Tools | Resources |
|------|-------|-----------|
| 语义 | 执行操作（写） | 读取数据（读） |
| 幂等性 | 不一定 | 天然幂等 |
| 订阅 | 不支持 | 支持资源变更订阅 |
| 安全模型 | 需要权限校验 | 通常可放宽权限 |

**为什么不能合并？**

1. 安全模型不同：Host 可能对"数据库查询"和"数据库修改"配置不同的权限策略
2. 缓存策略不同：Resource 结果可以缓存，Tool 结果通常不能
3. 订阅机制：Resource 有独特的订阅能力，Tool 没有这个需求

类比 REST：`GET /users` 和 `POST /users` 虽然操作同一个资源集合，但语义截然不同，适用不同的中间件策略。

</details>

---

**Q5: Sampling 是什么？它打破了什么传统模式？有什么安全风险？**

<details>
<summary>参考答案</summary>

**Sampling** 允许 MCP Server 反向请求 LLM 生成内容，打破了传统的 "Client 单向请求 → Server 响应" 模式。

**典型场景：**
- Server 拿到大段文档，让 LLM 先做摘要再处理
- Server 需要在处理过程中让 LLM 做判断或推理

**安全风险：**
1. **Token 消耗**：恶意 Server 可能通过 Sampling 大量消耗 LLM token
2. **提示词注入**：Server 可能构造恶意提示词诱导 LLM
3. **数据泄露**：Server 可能在 Sampling 请求中泄露敏感数据

**防御措施：**
- Host 必须在每次 Sampling 前弹窗让用户确认
- 限制单次 Sampling 的 max_tokens
- 审查 Server 发送给 LLM 的消息内容

</details>

---

### 能力协商与协议细节

**Q6: 请解释 MCP 的能力协商（Capability Negotiation）机制。**

<details>
<summary>参考答案</summary>

能力协商是贯穿 MCP 所有交互的核心机制：Client 和 Server 在初始化和运行时声明各自支持的功能，双方按"最小交集"原则确定可用功能集。

**协商流程：**
1. Client 在 `initialize` 请求中声明 `ClientCapabilities`（如 `roots`、`sampling`）
2. Server 在 `initialize` 响应中声明 `ServerCapabilities`（如 `tools`、`resources.subscribe`）
3. 双方在后续交互中需遵守声明——Server 未声明 `subscribe` 则 Client 不应发送订阅请求
4. 2025 年 3 月版本后支持渐进式能力更新（运行时通过 `capabilities/updated` 通知更新）

</details>

---

**Q7: 当一个 tools/call 的业务执行失败时，MCP 如何区分"工具调用失败"和"协议通信失败"？**

<details>
<summary>参考答案</summary>

这是 MCP 错误处理模型的核心设计：

**工具执行失败（业务层）** → 返回 JSON-RPC Response，`result.isError = true`：

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "content": [{"type": "text", "text": "数据库查询失败：连接超时"}],
        "isError": true
    }
}
```

**协议通信失败（协议层）** → 返回 JSON-RPC Error：

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "error": {
        "code": -32602,
        "message": "Invalid params",
        "data": "缺少必填参数 'city'"
    }
}
```

**为什么这样设计？** LLM 可以理解 `isError: true` 的工具错误并采取补救（换参数重试、告知用户等），但 JSON-RPC Error 表示通信本身出了问题，LLM 无法也不应处理。

</details>

---

### 设计理解

**Q8: MCP 的四大设计原则是什么？为什么这么设计？**

<details>
<summary>参考答案</summary>

1. **Servers 应极容易构建**：降低工具开发门槛，鼓励更多开发者贡献 MCP Server
2. **Servers 应高度可组合**：不同 Server 可以自由组合，形成更复杂的工具链
3. **Servers 不应能读取完整对话历史，也不能"窥视"其他 Server**：保护用户隐私和安全隔离
4. **功能可渐进添加，向后兼容**：Client 和 Server 可以独立升级，新老版本共存

**为什么这么设计？** 这些原则直接回应了传统 AI 工具集成的痛点：
- 原则①②降低生态建设难度
- 原则③解决安全和隐私顾虑
- 原则④保证协议的长期演进能力

</details>

---

**Q9: 如果你的 MCP Server 需要处理一个耗时 30 秒的操作，你会如何设计以提供良好的用户体验？**

<details>
<summary>参考答案</summary>

核心思路：利用 MCP 的**进度通知**和**取消机制**。

1. **接受 progressToken**：工具参数中接受来自 Client 的 `_meta.progressToken`
2. **分阶段推送进度**：在工具执行的关键节点发送 `notifications/progress`
3. **支持取消**：监听 `notifications/cancelled`，在每次循环前检查是否被取消
4. **合理的超时设置**：Server 端设置总超时，避免无限执行
5. **流式返回中间结果**：如果可以，通过 Streamable HTTP 流式返回部分结果

</details>

---

## 附录

### 新增术语速查表

| 术语 | 英文 | 简要说明 |
|------|------|----------|
| JSON-RPC | JSON-RPC 2.0 | 轻量级 RPC 协议，JSON 格式，传输无关 |
| stdio | Standard Input/Output | 标准输入输出，进程间通信方式 |
| SSE | Server-Sent Events | HTTP 服务端推送技术 |
| Streamable HTTP | Streamable HTTP | 2025 年新增的默认 MCP 传输方式 |
| Capability Negotiation | Capability Negotiation | Client/Server 之间的能力协商机制 |
| Sampling | Sampling | Server 反向请求 LLM 生成内容的能力 |
| Progress Notification | Progress Notification | 长时间操作的进度通知 |
| Cancelled Notification | Cancelled Notification | 取消正在进行的操作 |
| Notification | Notification | 无需回复的单向消息 |
| Batch Request | Batch Request | JSON-RPC 的批量请求能力 |
| Stateless / Stateful | Stateless / Stateful | Streamable HTTP 的两种运行模式 |
| Elicitation | Elicitation | Server 向用户提问的引导模式 |

### 协议方法速查表

| 方法 | 类型 | 方向 | 说明 |
|------|------|------|------|
| `initialize` | Request | C → S | 初始化连接 |
| `initialized` | Notification | C → S | 确认初始化完成 |
| `ping` | Request | C → S | 心跳检测 |
| `tools/list` | Request | C → S | 获取工具列表 |
| `tools/call` | Request | C → S | 调用指定工具 |
| `resources/list` | Request | C → S | 获取资源列表 |
| `resources/read` | Request | C → S | 读取指定资源 |
| `resources/subscribe` | Request | C → S | 订阅资源变更 |
| `resources/unsubscribe` | Request | C → S | 取消订阅 |
| `resources/templates/list` | Request | C → S | 获取资源模板列表 |
| `prompts/list` | Request | C → S | 获取提示词模板列表 |
| `prompts/get` | Request | C → S | 获取填充后的提示词 |
| `sampling/createMessage` | Request | S → C | Server 请求 LLM 生成内容 |
| `elicitation/create` | Request | S → C | Server 请求向用户提问 |
| `logging/setLevel` | Request | C → S | 设置 Server 日志级别 |
| `completion/complete` | Request | C → S | 请求自动补全建议 |
| `notifications/progress` | Notification | S → C | 进度更新 |
| `notifications/cancelled` | Notification | C → S | 取消操作 |
| `notifications/resources/updated` | Notification | S → C | 资源内容变更 |
| `notifications/resources/list_changed` | Notification | S → C | 资源列表变更 |
| `notifications/tools/list_changed` | Notification | S → C | 工具列表变更 |
| `notifications/prompts/list_changed` | Notification | S → C | 提示词列表变更 |
| `notifications/capabilities/updated` | Notification | S → C | 能力声明更新 |

### 推荐阅读

- [MCP 官方规范 - Transport Layer](https://spec.modelcontextprotocol.io/specification/2025-03-26/basic/transports/)
- [MCP 官方规范 - Lifecycle](https://spec.modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle/)
- [Streamable HTTP 设计文档](https://modelcontextprotocol.io/specification/streamable-http)
- [MCP Inspector 调试工具](https://github.com/modelcontextprotocol/inspector)
