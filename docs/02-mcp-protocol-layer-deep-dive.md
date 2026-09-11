# 第二模块：MCP 协议层深入理解

## 目录

1. [一、是什么——MCP 协议全景回顾](#一是什么mcp-协议全景回顾)
2. [二、为什么需要——传输层演进与核心原语设计动机](#二为什么需要传输层演进与核心原语设计动机)
3. [三、如何实现——传输机制与原语详解](#三如何实现传输机制与原语详解)
   - [3.4.4 Sampling 安全深度分析](#344-sampling采样--反向请求-llm)
   - [3.4.5 Elicitation（引导模式）](#345-elicitations引导模式--server-向用户提问)
   - [3.5 传输方式性能基准测试](#35-传输方式性能基准测试)
4. [四、底层原理——JSON-RPC 消息格式与能力协商](#四底层原理json-rpc-消息格式与能力协商)
   - [4.5 协议版本逐项差异对照与兼容策略](#45-协议版本逐项差异对照与兼容策略)
5. [五、企业级最佳实践](#五企业级最佳实践)

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

  本质：

  标准输入输出（stdio）本质上是**进程打开的文件描述符（FD）**。:o::o::o::o::o::o::o:

  - **子进程**只有 `stdin`（0号）和 `stdout`（1号）这两个**端口**。
  - 而**父进程**手里握着的是连接这两个端口的**管道（Pipe）的另一端**。

  在操作系统层面：
  父进程握有管道的**写端**（用来往子进程的 `stdin` 写数据）和**读端**（用来读子进程 `stdout` 的输出）。
  **其他同级进程（第三方应用）没有这个管道另一端的句柄（Handle/FD）**。它们既不知道这个管道的 ID，也没有权限打开它，所以自然无法往里面写数据，也无法从中读取数据。

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

SSE 的一个核心问题是**连接不可恢复**——如果 SSE 长连接断开，Client 必须重新发起 HTTP POST 请求获取新数据。:o::o::o:这在移动网络或负载均衡器环境下频繁发生。:o::o::o::o::o:

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
| 连接可恢复性 | 断开后需完整重建 | 请求间无状态，任意重组:o: |
| Server 连接压力 | 每 Client 一个长连接 | 按需建立，可池化 |
| 双向流支持 | 单向推送 + 独立 POST | 统一在 HTTP 上双向流 |
| 模式灵活性 | 仅 Stateful | 支持 Stateless 和 Stateful 两种模式 |
| 负载均衡友好 | 需要 sticky session | 无状态请求可任意路由 |



### 💡 核心：Streamable HTTP = 回归标准 + 按需流式

在深入技术细节前，我们先理解本质差异：**SSE是一个有状态的专用推送通道，而Streamable HTTP是基于无状态HTTP的、按需启用的流式响应**。这是两者所有差异的根源。

#### 一、清晰界定：SSE和Streamable HTTP到底是什么？

#### 1. SSE是什么？

SSE（Server-Sent Events）是一项:rocket:**有状态**的单向传输技术，允许服务器通过一个持久化的HTTP长连接，向客户端单向推送数据流。在MCP协议的实现中，SSE采用了“双连接”模式：
- 一个 HTTP 短连接用于客户端发送请求；
- 一个 SSE 长连接用于服务器推送结果。

这个SSE通道是有状态的，它必须一直保持打开，才能持续接收服务器推送。

#### 2. Streamable HTTP是什么？

Streamable HTTP是MCP协议在2025年3月26日正式引入的传输机制，它并没有发明新协议，而是利用了**标准HTTP的现有能力**:o::o::o::o::o::o::o::o::o::o:（如Transfer-Encoding: chunked）:o::o:，实现了更灵活的通信模式。在最新修订中，工作流得到了进一步简化：

#### 与 Content-Length 的区别

| 特性     | Content-Length      | Transfer-Encoding: chunked |
| :------- | :------------------ | :------------------------- |
| 长度已知 | 必须知道精确长度:o: | 无需知道                   |
| 发送方式 | 一次性发送整个体    | 分块逐步发送               |
| 连接复用 | 支持                | 支持                       |
| 适用场景 | 静态内容、已知大小  | 动态生成、流式:o::o:       |

- **统一端点**：服务器只暴露一个单一的HTTP端点（如 `/mcp`），所有交互都在此完成。
- **无状态请求**：客户端将每个JSON-RPC请求或通知封装成一个独立的HTTP POST请求进行发送。
- **按需流式化**：服务器收到请求后，可以选择返回一个普通的JSON对象，也可以选择将响应:rocket:**升级为一个SSE流**，实现流式传输。
- **内置双向交互**：服务器发起的请求（如提示用户操作）通过 **MRTR（Multi Round-Trip Requests）** 机制，嵌入在响应结果中返回。
- **利用HTTP基础**：整个传输基于标准HTTP请求-响应模型，天然兼容各类HTTP基础设施。

---

#### 二、深入剖析：SSE为什么“不够好”？

SSE的“不够好”，源于其有状态的双连接设计带来的四个核心问题。

#### 1. 单向通信的交互瓶颈

SSE本身是单向推送的，这在MCP的场景下会产生一个僵硬的“命令-推送”裂谷
#### 2. 有状态连接的巨大资源消耗:rocket:

SSE的每个连接都需要服务器为其维护状态，这带来了双重的资源负担：
- **连接数线性增长**：在海量客户端场景下，服务器需要为每个客户端保持一个独立的长连接，这种`O(N)`的连接数增长会迅速耗尽服务器资源。即使是现代浏览器，每个域名下的SSE并发连接数也被限制在6个。
- **长时间占用**：不仅TCP连接被长期占用，服务器还需为每个连接维护其上下文状态，造成巨大的内存和CPU开销。

#### 3. 薄弱的基础设施兼容性

SSE依赖于“永远在线”的长连接，这与当前主流的、为短连接设计的云基础设施之间存在天然的矛盾：
- **负载均衡器困境**：大多数负载均衡器对长时间保持的连接支持不佳，可能导致负载不均衡或错误地终止空闲连接。
- **CDN的“绊脚石”**：CDN主要通过缓存短连接响应来加速，但无法有效缓存或优化SSE这类实时、动态的长连接。
- **防火墙干扰**：企业防火墙常常会主动断开长时间空闲的连接。

#### 4. 不佳的高并发性能

基准测试提供了强有力的数据支撑：
- **连接建立开销**：SSE机制在每次工具调用时，都需要经历TCP握手（约50-100ms）和SSL协商（约100-200ms），导致**端到端延迟增加约120-150ms**。
- **长连接下的性能恶化**：在有20个并发连接的“持续负载”测试中（60秒，目标RPS=50），SSE虽然在低负载下能保持100%成功率，但随着负载持续，其**平均响应时间已攀升至565ms**，出现了显著的性能恶化。

---

#### 三、架构拆解：Streamable HTTP“好在哪里”？

它解决上述问题的核心，就是对标准HTTP请求-响应模型的重构和创造性运用。

#### 1. 机制：回归HTTP请求-响应，实现低延迟

Streamable HTTP 通过回归标准的 HTTP POST 请求-响应模式，大幅降低了每次调用的延迟：
- **消除连接建立开销**：客户端每次发起请求都是一个标准的HTTP POST，**不需要为每个请求重新建立TCP连接**。在高频请求场景中，操作系统和网络库可以复用底层的TCP连接。
- **连接复用，而非复用会话**：Streamable HTTP的“连接复用”是指**操作系统的TCP连接复用**。这消除了反复建立新连接的开销，将首次调用的延迟降低了60%以上。延迟数据可以低至**10-30ms**。

#### 2. 机制：按需启用SSE，实现灵活交互:o::o::o::o::o::o::o::o::o::o::o::o::o::o::o::o::o::o::o::o::o::o:

**MCP 的 Streamable HTTP 传输方式很聪明地把 SSE（Server-Sent Events）从“必须一直用的通道”变成了“按需开启的响应格式”。** 这样服务器可以灵活决定什么时候用普通 JSON 响应，什么时候用流式响应，而且多个流式请求可以同时进行，互不干扰。

- **SSE作为响应格式，而非传输机制**：当不需要流式传输时，服务器可以直接返回一个标准的JSON响应。
- **请求发起流式**：流式传输的发起权在“请求”本身，而非一个独立的“通道”。服务器在处理POST请求时，如果结果需要分块返回，就可以将Content-Type设置为`text/event-stream`，将响应升级为SSE流。
- **请求内的流式会话**：每个独立的POST请求可以对应一个独立的SSE流式会话。这意味着**客户端可以同时发起多个需要流式响应的请求，而它们之间不会相互干扰**。

#### 3. 机制：拥抱无状态架构，实现水平扩展:o::o::o::o:

这是Streamable HTTP实现高吞吐量的基石，它通过拥抱**无状态设计**，让MCP服务器在现代云原生环境中轻松扩展：
- **服务器无需记忆**：每个HTTP POST请求都携带了服务器处理它所需的所有信息。服务器在处理完一个请求后，不保留任何关于客户端的状态，**这让应用服务器的扩展变得像Web服务器一样简单**。
- **连接数问题被彻底解决**：客户端连接的“数量”与服务器负载的“规模”不再直接挂钩。真正影响服务器性能的是它每秒能处理的HTTP请求数（RPS），而非有多少个客户端连接。
- **单连接多路复用**：通过单个TCP连接，可以发送无数个HTTP POST请求，并接收对应的响应，其有效性已在高并发测试中得到验证。标准测试数据显示，Streamable HTTP可实现**290-300 RPS**的吞吐量。

总结：一个有状态一个无状态，一个需要长连接，一个可以不用长连接，并且还能复用tcp连接



### 2.2 为什么需要四大核心原语

从第一模块我们知道 MCP 有三种基础原语（Tools / Resources / Prompts），但规范中实际上定义了**四种核心原语**，第四种是 **Sampling（采样）**。:rocket:2025 年初，MCP 官方宣布 **Sampling 原语已废弃**，不再推荐使用。

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

**Pretty-print**（美化打印）是一种将结构化数据（如 JSON、XML、HTML、代码等）以**人类可读的格式**输出的技术，核心特征包括**缩进、换行、对齐和适当的空格**，使层次结构和内容一目了然。

#### 为什么需要 pretty-print？

计算机处理数据时，追求**最小体积和最高效率**，所以原始格式往往是压缩的（无额外空格、换行）。例如：

```json
{"name":"Alice","age":30,"address":{"city":"Beijing","zip":"100000"},"hobbies":["reading","chess"]}
```

这种格式机器读起来飞快，但人眼看过去很难立刻找到 `age` 的值或 `hobbies` 的第二项。**Pretty-print 的目标就是为人类调试、查看、编辑提供视觉友好的展示**。

同上例经过 pretty-print 后：

```json
{
  "name": "Alice",
  "age": 30,
  "address": {
    "city": "Beijing",
    "zip": "100000"
  },
  "hobbies": [
    "reading",
    "chess"
  ]
}
```

一眼就能看出结构层级。

#### Pretty-print 的潜在问题

1. **体积膨胀**：对于大 JSON（例如 10 MB 数据），添加缩进和换行可能使体积增加 20%~50%，浪费存储和传输带宽。
2. **敏感信息暴露**：有些数据在压缩时可能利用字符数模糊处理，美化后更容易被肉眼发现。
3. **日志泛滥**：将超长对象 pretty-print 到日志文件会迅速消耗磁盘空间，且难以用 `grep` 等单行匹配工具搜索。



## 3.2 SSE 传输实现

#### 架构

SSE 传输使用两个 HTTP 端点：

```
POST /mcp  →  Client 向 Server 发送 JSON-RPC 请求
GET  /mcp  →  Server 向 Client 推送 SSE 事件流
GET  /health → (可选) 健康检查端点
```

#### Client 端实现

```python
类 SSEClientTransport:
    初始化(base_url):
        self.base_url = base_url
        self.message_id = 0                    # 自增消息ID
        self.pending_requests = {}             # {id: Future} 等待响应的请求

    方法 connect():
        # 建立 SSE 长连接
        创建异步 HTTP 客户端(超时=无限)
        打开到 {base_url}/mcp 的 GET 流式连接
        对于流中的每一行:
            如果行以 "data: " 开头:
                解析 JSON 数据
                调用 _handle_message(数据)

    方法 send(method, params):
        # 发送请求并等待对应响应
        self.message_id += 1
        request = {
            "jsonrpc": "2.0",
            "id": self.message_id,
            "method": method,
            "params": params
        }

        # 创建一个 Future 用于等待此请求的响应
        future = 创建新的 Future
        self.pending_requests[self.message_id] = future

        # 通过 HTTP POST 发送请求
        创建异步 HTTP 客户端
        向 {base_url}/mcp 发送 POST 请求，body 是上面的 JSON

        # 立即返回 Future，调用者可以 await 它
        return future

    方法 _handle_message(data):
        # 处理来自 SSE 流的消息
        if data 中包含 "id" 且 id 在 pending_requests 中:
            # 这是某个请求的响应
            取出对应的 future 并从 pending_requests 中移除
            if data 中有 "result":
                future.set_result(data["result"])    # 成功，设置结果
            else if data 中有 "error":
                future.set_exception(Exception(data["error"]))  # 失败，抛出异常
        else:
            # 这是服务器主动推送的通知
            调用 _handle_notification(data)
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

#### 3.4.5 Elicitation（引导模式）—— Server 向用户提问

Elicitation 是 **2025-03-26 版本引入的新原语**。它允许 MCP Server 主动向用户提问，获取工具执行所需的额外信息。当前大多数教材仅提及该词，但大厂面试中可能被深挖。

**Elicitation 的协议定义：**

Elicitation 是四个基础原语之外的**第五种交互模式**，其核心方法是 `elicitation/create`（Request，Server → Client 方向）。

| 方法 | 类型 | 方向 | 说明 |
|------|------|------|------|
| `elicitation/create` | Request | S → C | Server 发起提问 |
| (响应) | Response | C → S | 用户填写结果返回 Server |

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
        "schema": {                              // JSON Schema 定义表单/选项结构
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
                }
            },
            "required": ["environment", "version"]
        },
        "timeout": 120
    }
}

// Client → Server: 用户填写结果
{
    "jsonrpc": "2.0",
    "id": 42,
    "result": {
        "action": "accept",     // "accept" | "decline" | "cancel"
        "content": {
            "environment": "staging",
            "version": "v2.1.0"
        }
    }
}
```

**Elicitation 的三种交互模式：**

| 模式 | 用途 | UI 形态 | 典型场景 |
|------|------|---------|----------|
| **form** | 引导用户补全结构化参数 | 表单窗口 | 部署前填写环境和版本号 |
| **confirm** | 要求用户确认高风险操作 | 确认对话框 | "确认部署到生产环境？" |
| **choice** | 在多个选项中让用户选择 | 单选/多选列表 | 搜索到 3 个"张三"，选一个 |

**与 destructiveHint 的协作**：tool annotations 中的 `destructiveHint` 是**静态标记**（"这个工具有破坏性"），Elicitation 的 confirm 模式是**动态确认**（"在当前参数下这个操作有破坏性，确认吗？"）。两者互补——静态标记让 Host 预判风险，动态确认让用户在上下文中做出最终决定。

**面试核心区分**："Elicitation 是 Server → 用户（人类交互），Sampling 是 Server → LLM（模型交互）。前者不消耗 Token，始终可见 UI；后者消耗 Token，是纯数据交互。"

---









### 3.5 传输方式性能基准测试

面试中经常被追问："stdio 和 Streamable HTTP 哪个更快？差多少？"以下基于统一测试场景的量化数据，确保回答时有据可依。

#### 3.5.2 基准测试数据

**测试环境**：Apple M2 Pro / Intel i7-13700K, 16-32GB RAM, Python 3.12, MCP SDK 1.3.0, localhost。数据为基于 SDK 源码分析和同等场景 LSP 实测数据的工程估算值（标注 `[E]` = Estimated）：

```
┌──────────────────────────────────────────────────────────────────────┐
│                    MCP 传输性能基准测试结果                            │
│                                                                      │
│  模式                        Mean      P50       P99     Throughput  │
│  ────────────────────────   ──────    ──────   ──────   ──────────  │
│  stdio (本地) [E]           0.85ms    0.72ms    1.8ms    ~1,180/s   │
│   基于: subprocess + pipe I/O，LSP 同等场景实测外推                   │
│                                                                      │
│  Streamable HTTP Stateful   1.2ms     1.0ms     3.5ms    ~830/s     │
│   [E] 首次连接后复用，仅受 HTTP headers + body 帧开销影响             │
│                                                                      │
│  SSE [E]                    1.8ms     1.5ms     5.0ms    ~560/s     │
│   基于: 双 Channel (POST+GET)，响应通过 EventSource 异步回传          │
│                                                                      │
│  Streamable HTTP Stateless  4.5ms     3.8ms     12ms     ~220/s     │
│   [E] 每次: TCP握手(0.5ms) + HTTP req/res + TLS(1-3ms)              │
│        + MCP init(1RTT) + tools/list(1RTT)                           │
│                                                                      │
│  Streamable HTTP Stateless  35ms      28ms      85ms     ~28/s      │
│   (远程, 50ms RTT) [E]                                              │
│   基于: TLS握手(2RTT≈100ms)+TCP(1RTT≈50ms)+HTTP(1RTT≈50ms)         │
│        +MCP init(1RTT≈50ms)+tools/list(1RTT≈50ms)≈300ms基础开销     │
│  注：远程延迟高度依赖网络环境，此数据为典型 LAN/WAN 估算               │
└──────────────────────────────────────────────────────────────────────┘
```

#### 3.5.3 连接数上限与开销分析

**单机 SSE 并发连接瓶颈估算**：

```
每个 SSE 连接的资源消耗：
  操作系统文件描述符 (FD)      1 个
  TCP Socket 内核缓冲区        ~16KB (默认)
  Python asyncio Task          ~4KB
  uvicorn worker 连接状态      ~50KB
  ─────────────────────────────────────
  每连接总计                   ~70KB

单机理论上限：
  限制因素                       默认值           调优后
  ────────────────────────────  ────────────    ───────────
  文件描述符 (ulimit -n)         1024            65535
  内存 (16GB / 70KB per conn)    ~230,000       —
  Python Event Loop 效率         —               ~10,000-50,000
  实际瓶颈: Event Loop           不建议超过      10,000

  超过 10,000 并发 SSE 建议切换 Streamable HTTP Stateless——
  它无"并发连接数"概念，每次请求独立建立/释放 TCP 连接。
```

**Heartbeat 带宽估算**（SSE 30s 间隔发送 `: heartbeat\n\n` = 14 bytes）：

```
  10,000 连接 × 每分钟 2 次 heartbeat × 14 bytes / 60s ≈ 4.7 KB/s
  结论：心跳保活的带宽开销可忽略。真正瓶颈是 FD 和内存。
```

#### 3.5.4 性能选型速查

| 场景 | 推荐传输 | 预期延迟 | 适用规模 |
|------|----------|----------|----------|
| 本地 IDE 插件（频繁小调用） | stdio | <1ms | 1 Client |
| 内网 Web 工具（间歇调用） | Streamable HTTP Stateful | ~1-3ms | <500 并发 Session |
| SaaS 平台（海量用户） | Streamable HTTP Stateless | ~5ms (本地) / ~35ms (远程) | 无连接数限制 |
| 实时监控（Server Push） | SSE | ~2ms | <10,000 并发连接 |
| CI/CD Pipeline（一次性） | stdio 或 Stateless HTTP | 取决于模式 | — |
| 移动端（网络不稳定） | Streamable HTTP Stateless | 取决于网络 | — |





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

## MCP 能力声明的本质

:rocket:

在 `initialize` 请求和响应中，客户端和服务器各自发送一个 `capabilities` 对象。这个对象的每一字段都表示：**“我（发送方）已经准备好接收和处理对方发起的、与该能力相关的 JSON-RPC 请求。”**

- **客户端声明的能力**（如 `roots`, `sampling`, `elicitation`）：客户端承诺它可以处理服务器将来发送的某些请求（例如 `roots/list`、`sampling/createMessage`、`elicitation/createRequest`）。
- **服务器声明的能力**（如 `tools`, `resources`, `prompts`）：服务器承诺它可以处理客户端将来发送的某些请求（例如 `tools/call`、`resources/read`、`prompts/get`）。

也就是说，**能力的声明方是被动方（接收请求方），而另一方是主动方（发起请求方）**。

**能力协商是为了解决“客户端与服务器之间“能力不对称”和“动态发现”的问题，让双方在建立底层通信连接后，能够互相告知“我能做什么、我需要你做什么”，从而决定这个会话期间可以安全地使用哪些高级功能。**

下面我分三个层次讲清楚：

---

#### 一、没有能力协商时，会出现什么麻烦？

假设没有 MCP，你直接写一个 AI 应用，想集成一个“文件系统工具”。你会怎么做？大概率是**硬编码**：

- 你事先知道这个工具提供 `list_directory`、`read_file`、`write_file` 三个函数。
- 你写代码时就把这些函数名、参数格式写死在客户端。
- 如果工具升级了，新增了 `delete_file`，你得修改客户端代码再重新发布。
- 如果另一个工具只提供 `read_file` 和 `write_file`，没有 `list_directory`，你又要写一套不同的调用逻辑。

这种模式的问题是：**客户端必须提前知道服务器的全部能力细节，而且能力变更会导致客户端代码变更**。

---

#### 二、MCP 能力协商解决了什么具体问题？

MCP 把“连接建立”和“能力发现”分离：

1. **建立通信通道**（TCP/stdio/HTTP） – 这一步只保证双方能收发 JSON-RPC 消息。
2. **能力协商** – 双方交换 `capabilities` 对象，告诉对方：
   - 我支持哪些 MCP 原语:o::o::o:（例如 `tools`、`resources`、`prompts`、`sampling`、`roots`、`elicitation`、`logging` 等）。
   - 每个原语下有哪些更细的配置（比如 `tools.listChanged` 表示我会通知工具列表变化；`roots.listChanged` 表示我会通知根目录变化）。:o:

**解决的问题**：

### 1. 动态能力发现，消除硬编码
- 客户端不需要提前知道服务器提供了哪些具体工具（`tools/list` 返回什么），也不需要知道服务器是否支持 `resources` 或 `prompts`。
- 通过协商，客户端得知“这个服务器支持 `tools` 能力”，于是它可以在后续发送 `tools/list` 请求去获取工具列表。
- 如果服务器只支持 `resources` 而不支持 `tools`，客户端就不会尝试调用工具，避免出错。

### 2. 多客户端、多服务器的互操作性
- 同一个客户端可以连接不同能力的服务器：一个服务器支持 `tools` 和 `resources`，另一个只支持 `prompts`。客户端根据协商结果动态调整自己的行为。
- 同一个服务器可以被不同客户端连接：有的客户端支持 `sampling`（可以用自己的 LLM 帮服务器思考），有的不支持；服务器可以根据客户端是否声明了 `sampling` 来决定是否发起 `sampling/createMessage` 请求。

### 3. 会话级别的安全与权限边界
- 能力协商不是“全局注册”，而是**每次连接独立协商**。同一个服务器，连接客户端 A 时可能启用了 `tools` 能力，连接客户端 B 时可能因为客户端没有声明 `roots` 能力，服务器就不会暴露需要访问本地文件系统的工具。
- 这允许精细的权限控制：比如服务器可以同时提供“高权限工具”和“低权限工具”，但只有那些在协商时声明了 `roots` 且提供特定根目录的客户端，才会看到高权限工具。

---

### 三：在建立通信的基础上再确定能用什么工具

流程顺序：

1. **底层连接建立**（例如启动一个子进程通过 stdio 通信，或者通过 HTTP 建立 TCP 连接）。
2. **客户端发送 `initialize` 请求**，带上自己的 `capabilities`（比如 `{ "roots": { "listChanged": true }, "sampling": {} }`）。
3. **服务器响应 `initialize`**，带上自己的 `capabilities`（比如 `{ "tools": {}, "resources": {} }`）。
4. **客户端发送 `initialized` 通知**，表示协商完成，可以进入操作阶段。
5. **客户端根据服务器的 `capabilities` 决定后续行为**：
   - 如果服务器声明了 `tools`，客户端可以调用 `tools/list` 获取具体工具列表，然后向模型展示这些工具。
   - 如果服务器声明了 `resources`，客户端可以调用 `resources/list` 获取资源列表，并订阅变化。
   - 如果服务器没有声明 `tools`，客户端永远不会调用 `tools/list`，也不会尝试让模型去调用该服务器的工具。

所以**工具的具体名称、参数、描述（即工具列表）不是在协商阶段传输的**，协商阶段只传递“是否支持 tools 这个能力类”。具体工具列表是在协商完成后的操作阶段，通过额外的 `tools/list` 请求来获取的。

---

#### 四、为什么需要两层（能力协商 + 具体列表）？

| 层次     | 内容                                            | 传输时机         | 作用                                              |
| -------- | ----------------------------------------------- | ---------------- | ------------------------------------------------- |
| 能力协商 | `capabilities` 对象（布尔/简单结构）            | 连接初始化时     | 让双方快速了解对方支持哪些 MCP 原语，避免无效请求 |
| 具体列表 | `tools/list`、`resources/list` 等返回的详细数组 | 操作阶段按需请求 | 获取实际可用的函数名称、参数、描述等细节          |

分两层的好处：
- 能力协商非常轻量，不需要传输大量 schema。
- 能力协商结果决定后续哪些 list 请求是合法的，服务器可以拒绝未协商的能力请求。
- 具体列表可以动态变化（例如服务器热加载了新工具），通过 `listChanged` 通知机制告知客户端重新拉取，无需重新协商连接。

---

### 五、总结一句话

> **MCP 能力协商解决的是“客户端与服务器在建立连接后，如何在不硬编码、不预先约定的情况下，动态发现对方支持哪些高级功能（如工具、资源、提示、采样等），并据此安全地协调后续通信”的问题。它是在底层通信通道之上、具体数据交换之前的一层握手协议，目的是实现解耦、可扩展和安全的互操作。**





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

###  JSON-RPC 通知

MCP协议完全遵循 JSON-RPC 2.0 规范，这意味着所有通知本质上都是一个单向消息，由发送方发出，**接收方绝对不需要、也不应该发送任何响应**。通知消息中**不得包含ID字段**，这与请求和响应的格式形成明确区分。

---

###  标准方法列表

MCP规范定义了以下标准通知方法：

| 方法                                   | 方向            | 功能                 |
| -------------------------------------- | --------------- | -------------------- |
| `notifications/initialized`            | client → server | 客户端确认完成初始化 |
| `notifications/cancelled`              | 双向            | 取消正在进行的请求   |
| `notifications/progress`               | 双向            | 报告长时间操作进度   |
| `logging/message`                      | server → client | 发送结构化日志消息   |
| `notifications/roots/list_changed`     | server → client | 根目录列表变更       |
| `notifications/resources/list_changed` | server → client | 资源列表整体变更     |
| `notifications/resources/updated`      | server → client | 特定资源内容更新     |
| `notifications/tools/list_changed`     | server → client | 工具列表变更         |

---

## 🔄 完整的消息生命周期

为了让大家对MCP的消息机制建立更清晰的框架，以下是通知如何融入协议的全流程：

1.  **初始化阶段**：客户端发送 `initialize` 请求（包含能力声明和协议版本）。
2.  **协议版本协商**：服务器根据客户端发送的版本和自身支持的版本列表，确定本次会话使用的协议版本。
3.  **能力协商**：服务器在 `initialize` 响应中返回其支持的能力集（如日志、资源更新通知等）。
4.  **准备就绪**：客户端发送 `notifications/initialized` 通知，表示已完成初始化准备。
5.  **正常操作**：初始化完成后即可开始发送请求和处理通知。**重要**：服务器在收到 `initialized` 通知前，不应发送除了 `ping` 和 `logging` 以外的请求或通知。
6.  **任务协作**：双方可通过 `requests/progress` 等机制进行协作。
7.  **优雅终止**：客户端发送 `shutdown` 请求，等待成功后发送 `exit` 通知。

---

## 🛠️ 核心通知类型深度解析

### 1. `notifications/initialized` (初始化完成确认)
- **方向**：client → server
- **触发时机**：`initialize` 请求/响应成功完成后，客户端**必须**立即发送此通知。
- **内容**：空对象 `{}`。
- **协议作用**：它标志着手握阶段正式结束，是双方开始正常通信的“发令枪”。在它被发送之前，服务器的功能是受限的。

### 2. `notifications/cancelled` (取消通知)
- **方向**：双向
- **触发时机**：任何一方在请求超时前未能收到 `success` 或 `error` 响应时，应发送此通知。
- **参数**：
  - `requestId`: 必需，正在取消的请求ID，接收方可精准终止操作。
  - `reason`: 可选，提供取消原因（如 `"timeout"`、`"user_abort"`）。
- **使用场景**：当模型调用一个可能耗时极长的工具且用户主动选择中断时，客户端可通过此通知避免无效计算和资源浪费。

### 3. `notifications/progress` (进度报告)
- **方向**：双向
- **功能**：为长时间运行的操作提供可选的进度跟踪。
- **机制**：依赖于**进度令牌 (`progressToken`)**。请求发起方在请求中包含此令牌，接收方在处理过程中使用该令牌多次发送进度通知，直到任务完成。
- **令牌原则**：进度令牌必须是**不透明的**，接收方无法解析其内容。进度通知**仅能引用**在活跃请求中提供的令牌，且该令牌必须关联到进行中的操作。
- **用法**：
  - **发起方**：`{"_meta": {"progressToken": "task-123"}}`
  - **执行方**：`{"method": "notifications/progress", "params": {"progressToken": "task-123", "progress": 50, "total": 100}}`
- **使用场景**：文件上传、大数据分析、视频转码等耗时任务，避免客户端误以为连接已死。

### 4. `logging/message` (结构化日志)
- **方向**：server → client
- **功能**：为服务器提供了向客户端发送结构化日志消息的标准化方式。
- **参数包含：
  - `level`: 严重性级别 (e.g., `"debug"`, `"info"`, `"error"`)
  - `logger`: 可选的记录器名称
  - `data`: 任意 JSON 可序列化数据
- **客户端控制**：客户端可以设置最低日志级别来控制日志详细程度。
- **使用场景**：调试服务器功能、监控服务器内部状态，是实现"智能工具"的重要手段。

---

## 📁 资源变更通知

这组通知构成了一个精密的 **“订阅-推送”模型**，确保客户端高效获取最新资源，而无需频繁轮询：

1.  **能力声明**：服务器需在 `initialize` 响应中声明 `{"resources": {"subscribe": true, "listChanged": true}}`。
2.  **订阅管理**：
    - **`resources/subscribe`**：客户端显式订阅特定资源 URI。
    - **`resources/unsubscribe`**：客户端主动取消订阅以节省资源。
3.  **服务器推送变更**：
    - **`notifications/resources/updated`**：当**已订阅**的特定资源内容发生变化时，服务器必须发送此通知。通知**必须**包含资源 URI。客户端收到后应重新发送 `resources/read` 请求以获取最新内容。
    - **`notifications/resources/list_changed`**：当整个可用资源列表发生结构性变化（如新增或删除），且客户端已支持 `listChanged` 标志时触发。
4.  **变更发现**：
    - **`notifications/tools/list_changed`**：当服务器支持的工具集（名称、描述、参数）发生动态变化时触发，提示客户端重新调用 `tools/list`。
    - **`notifications/roots/list_changed`**：当客户端能访问的根目录列表发生变化时触发。

---

## 🧠 关键设计原则

### 基于能力的通知
通知和请求一样，都是**基于能力的**。这意味着在`initialize`阶段，双方必须明确声明其支持通知类型。若服务器未声明`listChanged`能力，客户端便不会收到`list_changed`通知。这种机制确保了协作中不会出现意外的消息，增强了协议的健壮性。

### 通知不是“控制台日志”
通知并非简单的调试信息，它们是**协议层面的一等公民**。例如，`notifications/roots/list_changed` 不是一个开发提示，而是MCP协议规定的一种标准机制，用于主动告知客户端文件系统结构已发生变化。

### 请求作用域通知
对于`progress`和`cancelled`这类与特定请求相关的通知，它们**必须通过该请求的响应流来传输**，而非通过独立的订阅/监听流。这确保了通知与原始请求的上下文紧密关联，避免了状态管理的混乱。

### 主动推送 vs. 轮询
MCP致力于让服务器能够主动向客户端推送变更，而不是让客户端频繁轮询。这种设计更现代化，能有效提升效率并减少延迟。如果一个变更通知丢失了，客户端可通过全量列表请求（如`resources/list`）来强制同步状态，最终保证数据一致性。

---

## 📊 通知机制的实现模式

总结MCP中通知的实现，可以分为三种模式：

1.  **异步报告模式**：一方发出请求（如工具调用），另一方通过`progress`通知反馈执行情况，但最终仍通过请求的响应`result`来返回最终结果。
2.  **主动变更推送模式**：服务器自主检测到状态变化（如文件修改），直接通过`updated`或`list_changed`通知告知所有相关客户端。
3.  **流程控制模式**：双方通过`initialized`和`cancelled`等通知来管理连接的生命周期和任务状态。

---

## 💎 总结

MCP的通知机制并非简单的状态传递，而是一套**以能力声明的双向通信系统**。它通过`progress`、`logging`、`cancelled`及各种`list_changed`等通知，将通信的双方有机地连接起来。这使得构建的AI应用不再是简单的请求-响应处理器，而是能够实时感知环境变化、主动向客户端报告进度、并根据用户行为优雅中止任务的智能系统。







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

### 4.5 协议版本逐项差异对照与兼容策略

理解协议版本的**代码级差异**，不仅是应对面试的需要，更是实现跨版本兼容 MCP Server/Client 的工程基础。以下是 2024-11-05 和 2025-03-26 两个关键版本的逐项对照。

#### 4.5.1 initialize 请求/响应的字段变化

**2024-11-05：**

```json
// Client → Server
{
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2024-11-05",
        "capabilities": { "roots": { "listChanged": true }, "sampling": {} },
        "clientInfo": { "name": "my-client", "version": "1.0.0" }
    }
}
// Server → Client
{
    "jsonrpc": "2.0", "id": 1,
    "result": {
        "protocolVersion": "2024-11-05",
        "capabilities": {
            "tools": {},
            "resources": { "subscribe": true, "listChanged": true },
            "prompts": { "listChanged": true },
            "logging": {}
        },
        "serverInfo": { "name": "my-server", "version": "1.0.0" },
        "instructions": "可选的使用说明"
    }
}
```

**2025-03-26：**

```json
// Client → Server
{
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {
            "roots": { "listChanged": true },
            "sampling": {},
            "elicitation": {}                     // ★ Client 新增
        },
        "clientInfo": { "name": "my-client", "version": "2.0.0" }
    }
}
// Server → Client
{
    "jsonrpc": "2.0", "id": 1,
    "result": {
        "protocolVersion": "2025-03-26",
        "capabilities": {
            "tools": {
                "listChanged": true,               // ★ Server 新增子字段
                "support_structured_output": true  // ★ Server 新增子字段
            },
            "resources": { "subscribe": true, "listChanged": true },
            "prompts": { "listChanged": true },
            "logging": {},
            "completions": {}                      // ★ Server 新增能力
        },
        "serverInfo": { "name": "my-server", "version": "2.0.0" }
        // instructions 字段已移除
    }
}
```

**逐字段差异对照表：**

| 字段 | 2024-11-05 | 2025-03-26 | 变更类型 |
|------|-----------|-----------|----------|
| `params.capabilities.elicitation` | 不存在 | `{}` | Client 新增 |
| `result.capabilities.tools.listChanged` | 不存在 | `bool` | Server 新增 |
| `result.capabilities.tools.support_structured_output` | 不存在 | `bool` | Server 新增 |
| `result.capabilities.completions` | 不存在 | `{}` | Server 新增 |
| `result.instructions` | 可选 `string` | 已移除 | 废弃 |

#### 4.5.2 capabilities 声明的字段级别差异

```
                   2024-11-05                    2025-03-26
                   ──────────                    ──────────

ClientCapabilities:
  roots               ✓                            ✓
  sampling            ✓                            ✓
  elicitation         ✗                            ✓  ← NEW

ServerCapabilities:
  tools               {} (空对象，仅表示支持)        {listChanged, support_structured_output}
  resources           {subscribe, listChanged}      {subscribe, listChanged}
  prompts             {listChanged}                 {listChanged}
  logging             {}                            {}
  completions         ✗                            {} ← NEW
```

> **关键认知**：2024-11-05 中 `tools: {}` 是空对象，存在仅表示"Server 支持工具"。2025-03-26 将其扩展为包含子能力的结构化对象——从"布尔式声明"演进到"能力矩阵声明"。

#### 4.5.3 新增或废弃的方法

| 方法 | 2024-11-05 | 2025-03-26 | 变更 |
|------|-----------|-----------|------|
| `elicitation/create` | 不存在 | Request (S→C) | **新增** |
| `notifications/capabilities/updated` | 不存在 | Notification (双向) | **新增** |
| `completion/complete` | 不存在 | Request (C→S) | **新增** |

JSON-RPC 标准 5 个错误码两个版本保持一致。

#### 4.5.4 版本兼容性实战

**场景**：你的 Server 实现的是 2024-11-05，但 Client 发来了 2025-03-26 的 initialize 请求。如何设计兼容策略？

```python
# version_compat.py —— MCP 跨版本兼容层
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class ProtocolVersion(Enum):
    V2024_11_05 = "2024-11-05"
    V2025_03_26 = "2025-03-26"
    V2025_06_18 = "2025-06-18"

# 兼容性矩阵：Server 版本 → 可接受的 Client 版本
COMPATIBILITY_MATRIX = {
    ProtocolVersion.V2024_11_05: [ProtocolVersion.V2024_11_05],
    ProtocolVersion.V2025_03_26: [
        ProtocolVersion.V2024_11_05,   # 向后兼容
        ProtocolVersion.V2025_03_26,
    ],
}

class VersionAdapter:
    """MCP 协议版本适配器

    核心策略：
    1. 版本协商：Server 选择兼容矩阵内可接受的版本
    2. 字段降级：移除目标版本不认识的 capability 字段
    3. Forward-compat：忽略 JSON 中的未知字段（旧 Server 不报错）
    4. 方法拒绝：Client 请求新版本专属方法时返回友好 Method Not Found
    """

    def __init__(self, server_version: ProtocolVersion):
        self.server_version = server_version
        self._negotiated: ProtocolVersion | None = None
        self._new_methods = {
            ProtocolVersion.V2025_03_26: [
                "elicitation/create", "completion/complete"
            ],
        }

    def negotiate(self, client_version_str: str) -> ProtocolVersion:
        """协商确定实际使用的协议版本

        规则：
        - 版本一致 → 直接使用
        - Client 更高 → 如果兼容矩阵允许则降级，否则拒绝
        - Client 更低 → Server 使用旧版本的能力子集
        """
        try:
            client_version = ProtocolVersion(client_version_str)
        except ValueError:
            raise VersionNegotiationError(
                f"不支持的协议版本: {client_version_str}"
            )

        compatible = COMPATIBILITY_MATRIX.get(self.server_version, [])
        if client_version not in compatible:
            raise VersionNegotiationError(
                f"版本不兼容。Server={self.server_version.value}, "
                f"Client={client_version_str}"
            )

        # 取双方版本的"较低者"作为实际运行版本
        all_versions = list(ProtocolVersion)
        self._negotiated = min(
            client_version, self.server_version,
            key=lambda v: all_versions.index(v)
        )
        logger.info(
            f"版本协商: Server={self.server_version.value}, "
            f"Client={client_version_str} → {self._negotiated.value}"
        )
        return self._negotiated

    def adapt_capabilities(self, server_caps: dict, target_version: ProtocolVersion) -> dict:
        """将 Server 能力声明降级到目标版本

        Forward-compat 原则：JSON 解析忽略未知字段，旧 Client 自动忽略新字段。
        降级主要是移除旧版本不认识的 capability 以避免误解。
        """
        import copy
        caps = copy.deepcopy(server_caps)

        if target_version == ProtocolVersion.V2024_11_05:
            # 降级到 2024-11-05：移除新版才有的字段
            if "tools" in caps and isinstance(caps["tools"], dict):
                caps["tools"].pop("listChanged", None)
                caps["tools"].pop("support_structured_output", None)
            caps.pop("completions", None)

        return caps

    def filter_new_method(self, method: str) -> bool:
        """检查方法是否在当前协商版本中可用"""
        if self._negotiated is None:
            return True
        for version, methods in self._new_methods.items():
            if method in methods and self._negotiated.value < version.value:
                logger.warning(f"拒绝新版本方法 '{method}' (协商={self._negotiated.value})")
                return False
        return True


class VersionNegotiationError(Exception):
    pass
```

**兼容策略总结：**

```
版本兼容决策树：

  Client 版本 > Server 版本？
      ├── YES → 兼容矩阵允许降级？
      │         ├── YES → 协商到 Server 版本，忽略 Client 的新字段
      │         └── NO  → 返回版本不兼容错误
      └── NO  → Server 版本 ≥ Client 版本
                ├── 相同 → 直接使用
                └── Server 更新 → 返回 Client 兼容的 capability 子集

  Forward-compat 原则：
  · JSON 解析忽略未知字段（不报错）
  · 未知 method → JSON-RPC -32601 Method Not Found
  · 未知 notification → 静默忽略
  · capabilities 中的新字段 → 旧 Client 自然忽略
```

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

