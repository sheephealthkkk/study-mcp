# MCP (Model Context Protocol) 入门教程

> 从 Function Calling 开发者到 MCP 开发者 —— 理解协议、架构差异、以及为什么这样写

---

## 目录

1. [先搞清楚：传统 Function Calling 怎么工作](#1-先搞清楚传统-function-calling-怎么工作)
2. [MCP 解决了什么问题](#2-mcp-解决了什么问题)
3. [MCP 协议核心三要素](#3-mcp-协议核心三要素)
4. [项目结构：三个文件的关系](#4-项目结构三个文件的关系)
5. [mcp_server.py 逐段详解](#5-mcp_serverpy-逐段详解)
6. [mcp_client.py 逐段详解](#6-mcp_clientpy-逐段详解)
7. [fc_demo.py：同一个功能，传统写法长什么样](#7-fc_demopy同一个功能传统写法长什么样)
8. [MCP vs Function Calling 对照表](#8-mcp-vs-function-calling-对照表)
9. [完整交互流程（一次请求的完整路径）](#9-完整交互流程一次请求的完整路径)
10. [FAQ](#10-faq)

---

## 1. 先搞清楚：传统 Function Calling 怎么工作

在你理解 MCP 之前，得先知道你"以前是怎么做的"。

### 1.1 传统 FC 的代码长这样

```
┌─────────────────────────────────────────────────┐
│              你的 Agent 代码 (单文件)             │
│                                                  │
│  tools = [                                       │
│    {"type":"function","name":"calculator",...}    │  ← 工具定义硬编码
│  ]                                               │
│                                                  │
│  def calculator(expr): ...                       │  ← 工具实现也在本地
│  def get_weather(city): ...                      │
│                                                  │
│  response = openai.chat(                         │
│      messages=[...],                             │
│      tools=tools          ← 每次请求都传全部工具   │
│  )                                               │
│                                                  │
│  if response.has_tool_call():                    │
│      func = lookup(response.tool_name)           │
│      result = func(**response.params)  ← 本地调用│
└─────────────────────────────────────────────────┘
```

### 1.2 传统 FC 的五个特点

| # | 特点 | 导致的问题 |
|---|------|-----------|
| 1 | **工具定义在客户端代码里** | 加工具 = 改客户端代码 = 重新部署 |
| 2 | **每次请求都传全部工具定义** | 工具多了，请求体巨大，token 消耗大 |
| 3 | **工具实现和 Agent 同进程** | 工具崩了，Agent 一起崩 |
| 4 | **格式跟 LLM 厂商走** | OpenAI 一种格式，Anthropic 另一种，换模型要改代码 |
| 5 | **无状态，每次调用独立** | 工具执行结果不能跨请求复用 |

### 1.3 传统 FC 只有一个优势（也是它最大的局限）

```
"简单——所有东西都在一个文件里"
```

但工程规模上去之后，这恰好变成了最大的问题。

---

## 2. MCP 解决了什么问题

### 2.1 一句话总结

> **MCP = 把工具从 Agent 里"拆出来"，变成一个独立的服务，用标准协议通信。**

### 2.2 架构对比图

```
【传统 Function Calling】              【MCP 协议】
                                       
 Agent 进程                             Agent 进程 (MCP Client)
 ┌──────────────┐                       ┌──────────────────┐
 │ 工具定义      │                      │ 决策引擎           │
 │ 工具实现      │   ← 全耦合在一起      │ 参数提取           │
 │ LLM 调用      │                      └────┬─┬─┬─────────┘
 │ 决策逻辑      │                           │ │ │
 └──────────────┘                      JSON-RPC over stdio
                                            │ │ │
                                       ┌────┴─┴─┴─────────┐
                                       工具服务进程 (MCP Server)
                                       ┌──────────────────┐
                                       │ 工具定义 (注册表)  │
                                       │ 工具实现 (函数)    │
                                       │ 参数校验           │
                                       └──────────────────┘
```

### 2.3 MCP 带来的五个改变

| 传统 FC | MCP | 好处 |
|---------|-----|------|
| 工具定义在客户端 | 工具定义在服务端，`tools/list` 动态获取 | 新增工具不碰客户端 |
| 每次请求传全部工具 | 握手一次，工具列表缓存 | 省 token，启动快 |
| 工具和 Agent 同进程 | 独立进程，stdio/HTTP 通信 | 工具崩了不影响 Agent |
| 每家 LLM 格式不同 | 统一的 JSON-RPC 2.0 | 换 LLM 不用改工具 |
| 无状态 | 有状态长连接 | 可复用上下文 |

---

## 3. MCP 协议核心三要素

MCP 协议由三个层次构成：

```
┌─────────────────────────────────┐
│  消息格式：JSON-RPC 2.0          │  ← 用 JSON 来表示请求和响应
├─────────────────────────────────┤
│  方法集合：initialize、           │
│  tools/list、tools/call、        │  ← MCP 定义的标准 API
│  resources/read、prompts/get    │
├─────────────────────────────────┤
│  传输层：stdio / HTTP+SSE       │  ← 消息怎么从 A 发到 B
└─────────────────────────────────┘
```

### 3.1 JSON-RPC 2.0（消息格式）

MCP 选择了 JSON-RPC 2.0 —— 一个只有 4 种消息类型的极简协议：

```json
// ① Request（请求）：有 id，期待响应
{"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}

// ② Response（成功）：有 id，有 result
{"jsonrpc": "2.0", "id": 1, "result": {"tools": [...]}}

// ③ Error（失败）：有 id，有 error
{"jsonrpc": "2.0", "id": 1, "error": {"code": -32601, "message": "..."}}

// ④ Notification（通知）：无 id，不期待响应
{"jsonrpc": "2.0", "method": "notifications/initialized"}
```

> **为什么选 JSON-RPC 而不是自己设计？**
> JSON-RPC 2.0 是一个已有 15 年历史、被无数项目验证过的标准。用现成的比造轮子好。

### 3.2 方法集合（MCP 的 API）

| 方法 | 方向 | 作用 |
|------|------|------|
| `initialize` | Client → Server | 握手：协商协议版本、交换能力 |
| `notifications/initialized` | Client → Server | 通知：我初始化完了 |
| `tools/list` | Client → Server | 发现：获取可用工具列表 |
| `tools/call` | Client → Server | 调用：执行一个工具 |
| `resources/read` | Client → Server | 读取资源（MCP 不止有工具） |
| `prompts/get` | Client → Server | 获取提示模板 |

本 Demo 实现了前 4 个（最核心的）。

### 3.3 传输层（stdio）

MCP 支持多种传输方式，本 Demo 使用 **stdio**（标准输入输出）：

```
Client 进程              Server 进程
    │                       │
    │ stdout ───────────→ stdin   (Client 发 JSON-RPC 请求)
    │                       │
    │ stdin  ←─────────── stdout  (Client 读 JSON-RPC 响应)
    │                       │
    │ stderr (日志)         stderr (日志)  ← 不参与协议
```

> 为什么用 stdio 而不是 HTTP？
> - 本地场景下，stdio 零配置（不需要端口号、防火墙）
> - 进程生命周期自然绑定（Agent 退出，工具进程自动回收）
> - 不暴露网络端口，更安全
> - MCP 规定 stdio 是必须支持的传输方式

---

## 4. 项目结构：三个文件的关系

```
study-mcp/
├── mcp_server.py    ← MCP 服务端：定义工具 + 处理 JSON-RPC 请求
├── mcp_client.py    ← MCP 客户端：协议握手 + 决策 + 调用工具
├── fc_demo.py       ← 对比用：同样的功能，传统 FC 的写法
└── TUTORIAL.md      ← 本教程
```

**先看谁？**

1. 先读 `fc_demo.py` —— 理解"你以前怎么写的"
2. 再读 `mcp_server.py` —— 看工具怎么"拆出去"
3. 最后读 `mcp_client.py` —— 看 Agent 怎么"连上去"
4. 对比两者的架构差异

**运行方式：**

```bash
# MCP 方式（两个文件联动，客户端自动启动服务端）
python mcp_client.py

# 传统 FC 方式（单文件运行）
python fc_demo.py
```

---

## 5. mcp_server.py 逐段详解

### 5.1 文件整体结构

```
mcp_server.py
├── 第1步：日志配置（stderr）
├── 第2步：工具实现（纯业务逻辑）
├── 第3步：工具注册表（inputSchema 格式）
├── 第4步：JSON-RPC 消息构造器
├── 第5步：MCP 协议方法处理
│   ├── handle_initialize()   → 握手
│   ├── handle_tools_list()   → 列出工具
│   └── handle_tools_call()   → 执行工具
├── 第6步：stdio 传输层（读/写）
└── 第7步：主循环
```

### 5.2 第1步：日志写到 stderr

```python
logging.basicConfig(
    level=logging.DEBUG,
    format="[SERVER] %(levelname)s %(message)s",
    stream=sys.stderr          # ← 注意
)
```

**为什么日志必须写 stderr？**

stdio 传输层中：
- **stdin** = MCP 客户端 → 服务端（JSON-RPC 请求）
- **stdout** = 服务端 → MCP 客户端（JSON-RPC 响应）
- **stderr** = 日志、调试信息（两边都不看它）

如果把日志写到 stdout，就会混入协议数据，客户端解析 JSON 会失败。**这是 stdio transport 最容易犯的错误之一。**

### 5.3 第2步：工具实现（纯业务函数）

```python
def _calculator(expression: str) -> str:
    allowed = set("0123456789+-*/.()% ")
    if not all(c in allowed for c in expression):
        return f"错误：表达式包含不允许的字符"
    result = eval(expression)
    return f"{expression} = {result}"
```

**这完全是普通的 Python 函数，不包含任何 MCP/HTTP/JSON-RPC 代码。**

这就是 MCP 的设计哲学：**工具函数和通信协议完全解耦**。同一个函数可以被 MCP、HTTP、gRPC、CLI 等任何方式调用。你今天用 MCP 包装它，明天可以换成 HTTP，函数本身一行都不用改。

> 对比：传统 FC 中，工具函数通常和 LLM SDK 代码写在同一个文件里，换一种调用方式要大改。

### 5.4 第3步：工具注册表 — 这里最关键

```python
TOOLS = [
    {
        "name": "calculator",
        "description": "执行数学运算...",
        "inputSchema": {                # ← MCP 叫 inputSchema
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "数学表达式，例如 2+3"
                }
            },
            "required": ["expression"]  # ← 声明必填参数
        }
    },
    ...
]
```

**MCP 的工具定义和 FC 的工具定义有什么不同？**

```python
# 传统 FC（OpenAI 格式）
{
    "type": "function",           # ← 有 type 字段
    "function": {
        "name": "...",
        "parameters": {...}       # ← 叫 parameters
    }
}

# MCP 格式
{
    "name": "...",                # ← 没有外层 type/function 包装
    "description": "...",
    "inputSchema": {...}          # ← 叫 inputSchema
}
```

**为什么要不一样？**

1. `inputSchema` 这个命名明确表示"这是工具的输入格式定义"，语义更清晰
2. MCP 去掉了 `"type": "function"` 的包装层——因为 MCP 不止有工具，还有 Resources 和 Prompts，不需要区分 type
3. `inputSchema` 是标准 JSON Schema——和任何 LLM 厂商无关，可以独立使用

### 5.5 第4步：JSON-RPC 消息构造器

```python
def make_response(req_id, result):
    return {
        "jsonrpc": "2.0",
        "id": req_id,           # ← 必须原样返回请求的 id
        "result": result
    }

def make_error(req_id, code, message):
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "error": {
            "code": code,        # ← JSON-RPC 标准错误码
            "message": message
        }
    }
```

**为什么 `id` 必须原样返回？**

因为客户端可能同时发多个请求（虽然 stdio 一般是串行的），id 用于把响应和请求对应起来。就像快递单号——你发了 3 个包裹，每个有唯一的单号，快递员回复时带着单号，你就知道是哪一单了。

**JSON-RPC 标准错误码**：

| 错误码 | 含义 |
|--------|------|
| -32700 | JSON 解析错误 |
| -32600 | 无效的 Request |
| -32601 | 方法不存在 |
| -32602 | 参数无效 |
| -32603 | 内部错误 |

### 5.6 第5步：协议方法处理

#### handle_initialize — 握手

```python
def handle_initialize(req_id, params):
    return make_response(req_id, {
        "protocolVersion": "1.0",
        "capabilities": {
            "tools": {}           # ← 声明"我有工具能力"
        },
        "serverInfo": {
            "name": "mcp-demo-server",
            "version": "1.0.0"
        }
    })
```

**这是 MCP 独有的，传统 FC 没有这个概念。**

握手的意义：
- **版本协商**：客户端说"我支持 1.0"，服务端回应"我也支持 1.0"。如果版本不匹配，直接在这一步失败，而不是在调用工具时才发现问题。
- **能力声明**：服务端告诉客户端"我有 tools 能力"。如果服务端没有声明 tools，客户端就知道不能调 tools/list。
- **标识信息**：双方互相报名字和版本，方便排查问题。

> 对比传统 FC：没有握手阶段，每次 API 请求直接把 tools 列表发过去。如果格式不兼容，只能从 LLM 的报错里猜。

#### handle_tools_list — 工具发现

```python
def handle_tools_list(req_id, params):
    return make_response(req_id, {
        "tools": TOOLS
    })
```

**一行代码就完成了。**

但这一行的背后是 MCP 最大的架构优势：**工具定义从客户端移到了服务端**。

想想这个场景：你有一个天气工具，100 个 Agent 都在用。传统 FC 模式下，每个 Agent 都要在自己的代码里写一遍工具定义；如果用 MCP，工具定义只在服务端写一次，所有 Agent 通过 `tools/list` 自动获取。

#### handle_tools_call — 执行工具

```python
def handle_tools_call(req_id, params):
    tool_name = params.get("name", "")
    arguments = params.get("arguments", {})

    func = TOOL_MAP.get(tool_name)
    if func is None:
        return make_error(req_id, -32601, f"工具不存在：{tool_name}")

    # 参数校验：检查必填参数
    tool_def = next((t for t in TOOLS if t["name"] == tool_name), None)
    if tool_def:
        required_params = tool_def["inputSchema"].get("required", [])
        for rp in required_params:
            if rp not in arguments:
                return make_error(req_id, -32602, f"缺少必填参数：{rp}")

    try:
        result_text = func(**arguments)
    except Exception as e:
        return make_error(req_id, -32603, f"工具执行出错：{e}")

    # 包装成 MCP 标准返回格式
    return make_response(req_id, {
        "content": [
            {"type": "text", "text": result_text}
        ]
    })
```

**两个关键细节：**

1. **参数校验在服务端做**
   服务端拿到参数后，先对照 `inputSchema.required` 检查必填参数是否齐全。这样即使客户端发来了不完整的数据，服务端也不会崩溃。这叫**防御性编程**。

2. **MCP 工具返回格式是固定的**
   ```json
   {
     "content": [
       {"type": "text", "text": "结果字符串"}
     ]
   }
   ```
   `content` 是一个数组，每个元素有 `type` 和对应的数据字段。当前最常用的是 `text` 类型，但 MCP 也支持 `image`、`resource` 等类型——工具可以返回图片、文件、甚至另一个资源的引用。

### 5.7 第6步：stdio 传输层

```python
def read_message():
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)

def write_message(msg):
    line = json.dumps(msg, ensure_ascii=False)
    sys.stdout.write(line + "\n")
    sys.stdout.flush()          # ← 必须立即 flush
```

**为什么每行一条 JSON？**

这是 MCP stdio transport 的规定：每条 JSON-RPC 消息占一行，用换行符分隔。原因：
- JSON 本身是文本，天然适合行分隔
- 简单粗暴，解析器一行 `json.loads()` 搞定
- 人类可以直接看日志（每行是一个完整的 JSON）
- 不需要实现复杂的帧定界（像 TCP 那样处理粘包）

**为什么 `flush()` 是必须的？**

Python 的 stdout 默认有缓冲——数据会在缓冲区攒到一定量才真正写出去。如果不 flush，消息可能一直卡在缓冲区，客户端永远收不到响应。这又是一个 stdio transport 的常见坑。

### 5.8 第7步：主循环

```python
def main():
    while True:
        msg = read_message()        # 读请求
        if msg is None:             # stdin 关了 → 退出
            break
        response = dispatch_message(msg)  # 处理
        if response is not None:    # Notification 没有响应
            write_message(response)       # 返回
```

这是经典的 **read-dispatch-write** 循环。服务端不主动发起通信，只被动响应——这也是 JSON-RPC 的设计模式（服务端是被调用方）。

---

## 6. mcp_client.py 逐段详解

### 6.1 文件整体结构

```
mcp_client.py
├── 第1步：McpTransport — stdio 传输层封装
│   ├── 启动服务端子进程
│   ├── send_request()    → 发 Request
│   ├── send_notification() → 发 Notification
│   └── receive()         → 收 Response
├── 第2步：McpClient — MCP 协议交互
│   ├── initialize()      → 握手 + 发现工具
│   └── call_tool()       → 调用工具
├── 第3步：SimpleAgent — 决策引擎
│   └── decide_and_call() → 关键词匹配 → 调用工具
└── 第4步：交互主循环
```

### 6.2 第1步：McpTransport — 启动服务端子进程

```python
class McpTransport:
    def __init__(self, server_script: str):
        self.process = subprocess.Popen(
            [sys.executable, server_script],  # python mcp_server.py
            stdin=subprocess.PIPE,            # 创建 stdin 管道
            stdout=subprocess.PIPE,           # 创建 stdout 管道
            stderr=subprocess.PIPE,           # 创建 stderr 管道
            text=True,                        # 文本模式（自动编解码）
            bufsize=1                         # 行缓冲
        )
```

**这里用了 `subprocess.Popen`，为什么不用 `import` 直接调函数？**

因为 MCP 要求服务端是**独立进程**。如果用 `import`，两者就在同一个 Python 解释器里——工具崩溃会导致 Agent 崩溃，完全失去了隔离性。

`subprocess.Popen` 把服务端启动为一个独立的子进程：
- 有自己独立的 Python 解释器
- 有自己独立的内存空间
- 崩溃不会影响父进程
- 可以通过管道通信

**参数解释：**
| 参数 | 含义 |
|------|------|
| `stdin=PIPE` | 创建管道，我们可以往服务端的 stdin 写数据 |
| `stdout=PIPE` | 创建管道，我们可以读服务端的 stdout 数据 |
| `text=True` | 读写的都是字符串（不是 bytes） |
| `bufsize=1` | 行缓冲模式，每写一行就发送（配合 flush 使用） |

**发送和接收消息：**

```python
def send_request(self, method, params=None):
    self._request_id += 1           # 自增的请求 ID
    msg = {
        "jsonrpc": "2.0",
        "id": self._request_id,
        "method": method,
        "params": params or {}
    }
    self._write(msg)
    return self._request_id         # 返回 id，调用方可以用于匹配响应

def _write(self, msg):
    line = json.dumps(msg, ensure_ascii=False)
    self.process.stdin.write(line + "\n")
    self.process.stdin.flush()      # ← 必须 flush，和服务端对称
```

**为什么用自增 id？**
JSON-RPC 要求每个 Request 有唯一 id。自增是最简单的方式，保证每次请求 id 不同。

### 6.3 第2步：McpClient — 协议交互

#### initialize() — 完整的初始化流程

```python
def initialize(self):
    # Step 1: 发送 initialize 请求
    req_id = self.transport.send_request("initialize", {
        "protocolVersion": "1.0",
        "capabilities": {},
        "clientInfo": {"name": "mcp-demo-client", "version": "1.0.0"}
    })
    resp = self.transport.receive()
    # ... 检查响应，打印服务端信息 ...

    # Step 2: 发送 initialized 通知（无 id，不期待响应）
    self.transport.send_notification("notifications/initialized")

    # Step 3: 发送 tools/list 请求
    req_id = self.transport.send_request("tools/list", {})
    resp = self.transport.receive()
    self.tools = resp["result"]["tools"]
```

**这三个步骤的顺序是 MCP 协议规定的，不能乱：**

```
initialize request
    ↓
initialize response      ← 握手完成
    ↓
initialized notification  ← 确认（不期待响应）
    ↓
tools/list request        ← 工具发现
    ↓
tools/list response
    ↓
tools/call request        ← 正常使用（可多次）
    ↓
tools/call response
```

**为什么 initialized 是 Notification 而不是 Request？**

Notification 没有 `id`，接收方不需要回复。这里客户端说"我初始化完了"，服务端知道了就行，不需要回复什么。如果设计成 Request，服务端还得想一个毫无意义的响应内容。

**为什么 tools/list 要放在 initialize 之后？**

因为服务端可能根据客户端声明的 capabilities 决定暴露哪些工具。比如客户端说"我支持图片"，服务端才返回能生成图片的工具。而 capabilities 是在 initialize 阶段交换的。

#### call_tool() — 调用工具

```python
def call_tool(self, tool_name, arguments):
    req_id = self.transport.send_request("tools/call", {
        "name": tool_name,
        "arguments": arguments
    })

    resp = self.transport.receive()

    # 解析 MCP 标准返回格式
    content = resp["result"].get("content", [])
    if content and content[0].get("type") == "text":
        return content[0]["text"]
```

**注意返回格式的解析：**
```python
content[0].get("type") == "text"
```
MCP 的设计允许一个工具返回多段内容（文本+图片+文件资源的混合体），所以 `content` 是数组。本 Demo 只用最简单的单文本返回。

### 6.4 第3步：SimpleAgent — 决策引擎

```python
class SimpleAgent:
    def decide_and_call(self, user_input):
        if self._match("calculator", user_input):
            expr = self._extract_expression(user_input)
            return self.mcp.call_tool("calculator", {"expression": expr})
        ...
```

**这个 Agent 用关键词匹配做决策。**

你在看这段代码时，请这样理解：
- `self._match("calculator", user_input)` 等价于 **LLM 判断"用户想算数"**
- `self._extract_expression(user_input)` 等价于 **LLM 提取参数**
- `self.mcp.call_tool(...)` 等价于 **执行 Function Call**

**关键词匹配** 和 **LLM 决策** 在逻辑上是等价的——都是"输入 → 分析 → 输出工具名+参数"。区别只是实现手段不同：一个是规则，一个是神经网络。

**为什么 demo 用关键词匹配而不用真实 LLM？**
1. 不需要 API Key，零门槛运行
2. 运行速度快，调试方便
3. 让你关注 MCP 协议本身，而不是 LLM 的使用细节
4. 规则是透明的——你知道为什么选了这个工具

---

## 7. fc_demo.py：同一个功能，传统写法长什么样

打开 `fc_demo.py`，你会看到它和前两个文件的对比：

### 7.1 工具定义：硬编码在 client 里

```python
# fc_demo.py (传统方式)
FC_TOOLS = [
    {
        "type": "function",          # ← FC 格式
        "function": {
            "name": "calculator",
            "parameters": {...}      # ← 叫 parameters
        }
    }
]

# vs mcp_server.py (MCP 方式)
TOOLS = [
    {
        "name": "calculator",
        "inputSchema": {...}         # ← 叫 inputSchema
    }
]
```

### 7.2 工具调用：本地函数调用 vs 跨进程调用

```python
# fc_demo.py — 传统 FC：直接调本地函数
func = FC_TOOL_MAP.get(tool_name)
result = func(**arguments)              # 同一个进程里直接调用

# mcp_client.py — MCP：通过 JSON-RPC 跨进程调用
result = self.mcp.call_tool(tool_name, arguments)
    # 内部通过 stdin/stdout 管道传递 JSON-RPC 消息
```

### 7.3 初始化：不存在 vs 完整握手

```python
# fc_demo.py — 传统 FC：没有初始化
agent = FcAgent()                # 直接创建，没有握手

# mcp_client.py — MCP：完整握手流程
mcp = McpClient("mcp_server.py")
mcp.initialize()                 # 握手 + 交换能力 + 发现工具
```

### 7.4 结构：一个文件 vs 两个文件分离

```
传统 FC:
  fc_demo.py  ← 包含全部：工具定义+工具实现+决策+调用

MCP:
  mcp_server.py  ← 服务端：工具定义+工具实现
  mcp_client.py  ← 客户端：协议+决策+调用
```

---

## 8. MCP vs Function Calling 对照表

| 维度 | 传统 Function Calling | MCP |
|------|----------------------|-----|
| **工具定义位置** | 客户端代码中 | 服务端（注册表） |
| **工具发现方式** | 硬编码，编译时确定 | `tools/list` 动态获取 |
| **添加新工具** | 改客户端代码，重新部署 | 改服务端，客户端无感知 |
| **通信协议** | LLM 厂商私有 API 格式 | JSON-RPC 2.0 标准 |
| **传输方式** | HTTPS API 调用 | stdio / HTTP+SSE / WebSocket |
| **进程模型** | 单进程（Agent + 工具） | 多进程（Agent 进程 + 工具进程） |
| **容错性** | 工具崩溃 = Agent 崩溃 | 工具崩溃不影响 Agent |
| **初始化握手** | 无 | 有 `initialize` |
| **能力协商** | 无（硬编码假设） | 有 capabilities 声明 |
| **状态管理** | 无状态（每次请求独立） | 有状态长连接 |
| **工具定义格式** | `{"type":"function","function":{...}}` | `{"name":"...","inputSchema":{...}}` |
| **参数 schema 字段名** | `parameters` | `inputSchema` |
| **返回格式** | 各厂商自定义 | `{"content":[{"type":"text","text":"..."}]}` |
| **LLM 厂商依赖** | 强依赖（换厂商 = 改格式） | 无依赖（协议标准统一） |
| **工具以外能力** | 无 | Resources、Prompts |
| **适用场景** | 单个 Agent + 少量工具 | 多 Agent 共享工具、大量工具 |

---

## 9. 完整交互流程（一次请求的完整路径）

用户输入 **"北京今天天气怎么样"** 时，发生了什么：

```
时间线 →

00:00  用户启动 mcp_client.py
       │
00:01  McpTransport.__init__()
       │  subprocess.Popen(["python", "mcp_server.py"], ...)
       │  服务端进程启动，开始监听 stdin
       │
00:02  McpClient.initialize()
       │
       ├─ send_request("initialize", {protocolVersion:"1.0",...})
       │  → client 往 server 的 stdin 写入:
       │    {"jsonrpc":"2.0","id":1,"method":"initialize","params":{...}}
       │
       ├─ receive()
       │  → client 从 server 的 stdout 读到:
       │    {"jsonrpc":"2.0","id":1,"result":{"protocolVersion":"1.0",...}}
       │  打印: ✅ 握手成功！
       │
       ├─ send_notification("notifications/initialized")
       │  → client 往 server 的 stdin 写入:
       │    {"jsonrpc":"2.0","method":"notifications/initialized"}
       │  (server 收到后不回复——因为 id 不存在)
       │
       ├─ send_request("tools/list", {})
       │  → client 写入: {"jsonrpc":"2.0","id":2,"method":"tools/list",...}
       │
       └─ receive()
          → client 读到: {"jsonrpc":"2.0","id":2,"result":{"tools":[...]}}
          打印: ✅ 发现 3 个可用工具

00:03  用户输入: "北京今天天气怎么样"
       │
00:04  SimpleAgent.decide_and_call("北京今天天气怎么样")
       │
       ├─ _match("calculator", ...)  → False (没有数学关键词)
       ├─ _match("get_weather", ...) → True  ("北京" 在关键词列表中)
       │
       ├─ _extract_city("北京今天天气怎么样") → "北京"
       │
       └─ mcp.call_tool("get_weather", {"city": "北京"})
          │
          ├─ send_request("tools/call", {name:"get_weather",
          │               arguments:{"city":"北京"}})
          │  → 写入: {"jsonrpc":"2.0","id":3,"method":"tools/call",...}
          │           params: {"name":"get_weather","arguments":{"city":"北京"}}
          │
          │  【服务端处理】
          │  read_message()
          │  → 从 stdin 读到请求
          │  dispatch_message()
          │  → method="tools/call" → handle_tools_call()
          │  → func = TOOL_MAP["get_weather"] = _get_weather
          │  → result = _get_weather(city="北京")
          │  → 返回 {"content":[{"type":"text","text":"☀️ 晴天，25°C..."}]}
          │  write_message(response)
          │  → 写入 stdout: {"jsonrpc":"2.0","id":3,"result":{...}}
          │
          └─ receive()
             → 从 server 的 stdout 读到响应
             → 解析 content[0]["text"]
             → 返回 "☀️ 晴天，25°C，湿度 40%，风力 2级"

00:05  print("📋 结果：☀️ 晴天，25°C，湿度 40%，风力 2级")
```

---

## 10. FAQ

### Q1: MCP 是不是就是换了个名字的 RPC？

不完全是。MCP 底层用 JSON-RPC，但 MCP 定义了**语义层**——它规定了 initialize、tools/list、tools/call 这些方法的含义，以及 inputSchema、content 等数据结构的格式。普通的 RPC 只是一个通信框架，MCP 是专门为 AI Agent 场景设计的。

### Q2: stdio 和 HTTP 传输有什么区别？什么时候用哪个？

| 场景 | stdio | HTTP+SSE |
|------|-------|----------|
| 本地工具 | ✅ 推荐 | 可用 |
| 远程工具 | ❌ 不支持 | ✅ 推荐 |
| 多客户端共享 | ❌ 不支持 | ✅ 推荐 |
| 配置复杂度 | 零配置 | 需要端口/域名 |
| 安全性 | 进程隔离 | 需要认证 |

MCP 规定所有实现**必须**支持 stdio，HTTP+SSE 是可选的。

### Q3: MCP 能替代 OpenAI Function Calling 吗？

不是"替代"关系，而是**解耦**关系。MCP 不调用 LLM——它只管工具的定义和调用。真正的流程是：

```
用户 → LLM（分析意图）→ MCP Client → MCP Server → 工具执行
```

LLM 负责"理解用户想干什么"，MCP 负责"把工具定义和调用标准化"。两者各司其职。

### Q4: 关键词匹配太简陋了，怎么接入真正的 LLM？

把 `SimpleAgent` 的 `_match()` 方法替换成 LLM API 调用即可。把 tools 列表和用户输入一起发给 LLM，LLM 返回 `{"tool": "get_weather", "params": {"city": "北京"}}`，然后你调用 `mcp.call_tool("get_weather", {"city": "北京"})`。Agent 的决策部分变了，但 MCP 协议的部分完全不用改——这就是解耦的价值。

### Q5: 为什么 MCP 要设计 initialize 握手，不能直接调吗？

因为 MCP 支持能力协商。服务端可能支持 tools、resources、prompts 等不同能力，客户端也可能有自己的能力。通过握手交换这些信息后，双方都知道后面可以调哪些方法，避免无效请求。

类比：你不能走进一家餐厅直接点菜——你得先知道这家餐厅做中餐还是西餐（握手），再看菜单（tools/list），然后点菜（tools/call）。

### Q6: MCP 工具一定要返回 `{"content": [{"type": "text", "text": "..."}]}` 这种格式吗？

是的，这是 MCP 规范的一部分。设计成数组是因为工具可能一次返回多段内容：
```json
{
  "content": [
    {"type": "text", "text": "这是分析结果"},
    {"type": "image", "data": "base64...", "mimeType": "image/png"},
    {"type": "resource", "resource": {"uri": "file:///report.pdf", "text": "..."}}
  ]
}
```
标准化返回格式让客户端可以统一处理所有工具的返回结果。

---

## 总结

通过这次学习，你理解了：

1. **传统 Function Calling 的问题**：工具和 Agent 耦合，难以扩展和管理
2. **MCP 的解决方案**：把工具拆成独立服务，用标准协议通信
3. **MCP 协议三要素**：JSON-RPC 2.0（消息格式）+ MCP Methods（API）+ stdio/HTTP（传输）
4. **MCP 生命周期**：initialize → tools/list → tools/call → close
5. **工具定义差异**：inputSchema vs parameters，注册表 vs 硬编码
6. **架构差异**：多进程隔离 vs 单进程耦合

现在动手跑一下 `python mcp_client.py` 和 `python fc_demo.py`，对比两者的运行效果，感受架构的差异！
