# 第一模块：MCP 基础认知与核心概念

> **学习周期**：4-5 天  
> **学习目标**：理解 MCP 是什么、为什么需要它、它解决什么层次的问题。掌握协议横向
> 对比（gRPC/WebSocket/GraphQL）的选型依据，理解设计权衡，能用量化标准做出
> "是否采用 MCP"的工程决策。

---

## 目录

1. [一、是什么——MCP 的定义与定位](#一是什么mcp-的定义与定位)
   - [1.5 历史与技术演进背景](#15-历史与技术演进背景)
2. [二、为什么需要——MCP 解决的核心痛点](#二为什么需要mcp-解决的核心痛点)
   - [2.4 扩展协议横向对比](#24-扩展协议横向对比)
3. [三、如何实现——MCP 的核心架构](#三如何实现mcp-的核心架构)
   - [3.4 设计权衡：MCP 选择牺牲了什么](#34-设计权衡mcp-选择牺牲了什么)
4. [四、底层原理——协议细节与消息流转](#四底层原理协议细节与消息流转)
5. [五、企业级最佳实践](#五企业级最佳实践)
   - [5.1.1 量化决策标准](#511-量化决策标准)
   - [5.1.2 什么时候不该用 MCP](#512-什么时候不该用-mcp)
6. [六、常见面试题](#六常见面试题)

---

## 一、是什么——MCP 的定义与定位

### 1.1 官方定义

**MCP（Model Context Protocol，模型上下文协议）** 是由 Anthropic 于 **2024 年 11 月 25 日** 正式开源的一个开放标准协议。其核心作用是 **标准化大语言模型（LLM）与外部工具、数据源和服务之间的通信规则**。

> 官方原文：MCP is an open protocol that standardizes how applications provide context to LLMs.

### 1.2 类比理解

如果把 AI 工具调用世界比作电子设备的接口世界，那么：

| 类比维度 | 传统方式 | MCP 方式 |
|----------|----------|----------|
| 设备接口 | 每家厂商自己的充电口（Lightning、Micro-USB、30-pin） | USB-C 统一标准 |
| AI 工具 | 每个 AI 应用单独对接每个工具（N×M 集成） | MCP 统一协议（N+M 集成） |
| 核心价值 | 重复造轮子，生态割裂 | 一次开发，到处使用 |

**MCP 想做 AI 工具调用世界的 "USB-C"** —— 一套通用、统一的连接标准，让 LLM 和各类外部能力的对接不再需要重复定制开发。

### 1.3 MCP 在 AI 技术栈中的位置

```
┌──────────────────────────────────────────────┐
│              用户界面层 (UI Layer)              │
│   Claude Desktop  │  VS Code  │  Cursor  │ ... │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│            Host 层（宿主层）                    │
│   管理 MCP 客户端生命周期、权限控制、连接管理      │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│           Client 层（客户端层）                 │
│   协议消息路由、订阅管理、通知分发               │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│           Server 层（服务器层）                 │
│   暴露 Tools / Resources / Prompts 等原语      │
└──────────────────┬───────────────────────────┘
                   │
┌──────────────────▼───────────────────────────┐
│         外部能力层 (External Capabilities)      │
│   数据库  │  API  │  文件系统  │  第三方服务  │... │
└──────────────────────────────────────────────┘
```

### 1.4 MCP 不是银弹

在深入之前，需要明确 MCP 的边界：

- **MCP 管的是"连接"，不是"能力"**：MCP 定义了工具如何被发现和调用，但工具本身的实现质量由开发者负责
- **MCP 是协议，不是框架**：它定义通信规范，不限制你用什么语言实现（Python、TypeScript、Go、Java 均可）
- **MCP 解决的是 N×M 问题，不是 1×1 问题**：如果你的场景是 "一个 AI 应用 + 一两个工具"，直接用 Function Calling 反而更轻量

### 1.5 历史与技术演进背景

> **核心问题**：MCP 为什么在 2024 年底这个时间节点出现？它是凭空创造的，还是历史演进的必然产物？

MCP 的诞生是三条技术演进脉络在 2024 年的交汇。理解这三条脉络，才能真正理解 MCP 的设计基因和它所回应的历史问题。

#### 1.5.1 脉络一：LSP 的成功——范式的证明（2016-2020）

**Language Server Protocol（LSP）** 由微软在 2016 年推出，定义了一套 IDE（编辑器）与语言服务器之间的标准协议。MCP 的设计深受 LSP 的影响——两者不仅基于相同的底层协议（JSON-RPC 2.0），更共享相同的核心公式：**将 N×M 降为 N+M**。

```
LSP 的革命：从 N×M 到 N+M

LSP 之前 (2015)：                    LSP 之后 (2016+)：

  N 个编辑器 × M 种语言               N 个编辑器 + M 种语言
  = N×M 个插件                       = N+M 个适配

  Sublime × Python                   Sublime ⟍
  Sublime × JavaScript               VS Code  ─ LSP Protocol ── Python Server
  Sublime × Go                       Vim      ⟋               JavaScript Server
  VS Code × Python                                             Go Server
  VS Code × JavaScript
  VS Code × Go                      只需写一个 Language Server，
  Vim × Python                       所有编辑器都能用
  Vim × JavaScript
  Vim × Go
  ... (N×M = 数十个插件)             (N+M = 几个编辑器适配 + 几个 Server)
```

**LSP 验证了什么？**

1. **JSON-RPC 在工具通信场景中足够好**：VS Code 每天处理数十亿条 LSP 消息，性能从未成为瓶颈
2. **N×M → N+M 公式可行**：生态从几十个重复插件爆炸到数百个高质量 Language Server
3. **社区自发贡献**：标准化降低门槛，TypeScript、Rust、Go 的语言 Server 都由社区驱动

**MCP 直接继承的 LSP 基因：**

| LSP 基因 | MCP 继承 |
|----------|----------|
| JSON-RPC 2.0 协议基础 | 同协议 |
| 传输无关设计（stdio/TCP/HTTP） | 同设计理念 |
| Initialize → Running → Shutdown 生命周期 | 同生命周期模型 |
| ServerCapabilities 能力声明 | 同能力协商机制 |
| 通知机制（PublishDiagnostics 等） | 同通知机制（Progress, Resource Updated） |
| TextDocument 抽象 | Tools / Resources / Prompts 抽象 |

> **关键洞察**：MCP 不是凭空创造的——它是 LSP 范式在 AI 工具调用领域的"搬运"。LSP 证明了"用标准协议连接工具消费者和工具提供者"这个模式成立。Anthropic 做的事情本质上是：把 LSP 中的 `textDocument/completion` 替换为 `tools/call`，把 `textDocument/diagnostic` 替换为 `resources/read`。

#### 1.5.2 脉络二：ChatGPT Plugins 的失败——不可重蹈的覆辙（2023.03-2024.04）

ChatGPT Plugins 在 2023 年 3 月推出时被寄予厚望，但 2024 年 4 月被正式废弃，改为 GPTs。它的失败为 MCP 的设计提供了宝贵的反面教训。

**失败原因清单——每条都值得 MCP 设计者警醒：**

| 失败维度 | ChatGPT Plugins 的问题 | MCP 的应对 |
|----------|----------------------|------------|
| **开放性** | 闭源生态，只有 OpenAI 能审核和上架 Plugin | 开源协议，任何人都可以实现 MCP Server |
| **厂商绑定** | Plugin 只能用于 ChatGPT | 一次编写，任何 MCP Client 都能使用 |
| **审核机制** | 中心化人工审核，效率低下 | 去中心化，Host 自行决定信任哪些 Server |
| **开发体验** | 必须使用 OpenAI 特定的 manifest 格式 | 标准 JSON-RPC，任何语言都能实现 |
| **商业模式** | 不透明，Plugin 开发者无法独立盈利 | 开源社区驱动，Server 可独立部署和商业化 |
| **社区投入** | 开发者缺乏长期投入动力（平台风险） | 开放标准，Anthropic/OpenAI/Google 多方参与 |
| **创新速度** | 受限于 OpenAI 的审核节奏 | 无审核瓶颈，创新速度取决于社区 |

**ChatGPT Plugins 失败的深层教训：**

中心化的 AI 工具生态必然失败。因为：
1. **审核瓶颈**：中心化审核无法跟上工具数量的指数增长
2. **创新抑制**：平台守门人决定什么工具可以存在
3. **信任单向**：用户只能信任平台，无法自主评估工具风险

MCP 的去中心化设计直接回应了这些教训：没有中心审核机构，Host 自主决定信任链，Server 可独立发布。

#### 1.5.3 脉络三：开源模型的崛起——工具的民主化需求（2023-2024）

```
2023-2024 年开源 LLM 的爆发式增长：

  Llama 2 (2023.07) → Mistral (2023.09) → Llama 3 (2024.04)
  → Qwen 2 (2024.06) → DeepSeek-V2 (2024.05) → ...

结果：企业不再绑定一个 LLM 提供商，而是在多个模型间自由切换。

但问题来了：
  · Llama 3 的工具调用格式 ≠ GPT-4 的格式 ≠ Claude 的格式
  · 每换一个模型，工具集成代码就要重写
  · 企业需要的是一个"模型无关"的工具接入层

MCP 的价值在这个时间点被急剧放大：
  → 它让企业可以"定义一次工具，所有模型共用"
  → 模型厂商自己负责适配 MCP（或通过 Host 适配）
  → 工具开发者不再需要关心"这个工具是给 GPT 用的还是 Claude 用的"
```

#### 1.5.4 三条脉络的交汇点：2024 年 11 月

```
为什么是 2024 年 11 月？

  2024.04  ChatGPT Plugins 正式关闭   ← 旧范式终结
  2024.06  Llama 3 成为企业主流选择    ← 多模型格局确立
  2024.09  开源社区 MCP 讨论白热化      ← 需求已迫在眉睫
  2024.11  Anthropic 正式开源 MCP      ← 新范式诞生

三条线：
  ① LSP 成功 → 证明了协议标准化的可行性（技术基础）
  ② ChatGPT Plugins 失败 → 说明了中心化走不通（教训总结）
  ③ 开源模型崛起 → 倒逼统一接入标准（市场需求）
```

> **面试展示金句**："MCP 的诞生是 LSP 范式在 AI 时代的自然延伸，也是对 ChatGPT Plugins 失败模式的必然反思。它不是 Anthropic 的灵光一闪，而是三条技术演进脉络在 2024 年底的必然交汇——LSP 的成功证明了标准化可行，ChatGPT Plugins 的失败证明了中心化不可行，开源模型的崛起创造了统一接入的刚性需求。"

---

## 二、为什么需要——MCP 解决的核心痛点

### 2.1 传统 Function Calling 模式的三个核心问题

#### 问题一：厂商绑定（Vendor Lock-in）

每个 LLM 提供商的工具 Schema 定义格式不同：

```python
# OpenAI 的工具定义格式
openai_tool = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "获取指定城市的天气",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称"}
            },
            "required": ["city"]
        }
    }
}

# Anthropic 的工具定义格式（2024 早期版本）
anthropic_tool = {
    "name": "get_weather",
    "description": "获取指定城市的天气",
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {"type": "string", "description": "城市名称"}
        },
        "required": ["city"]
    }
}
```

同样的工具，只因对接不同的 LLM 就要写不同的 Schema 定义代码。工具越多、对接的 LLM 越多，维护成本呈指数级增长。

#### 问题二：无统一执行标准

传统模式下，工具调用方式由开发者**硬编码**：

```
传统模式流程：
用户提问 → LLM 返回 tool_call → 开发者写代码判断是哪个工具
          → 开发者写代码调用对应函数 → 开发者写代码把结果返回 LLM
          → LLM 生成最终回复
```

这里的每一步判断和调用逻辑都是**项目特有的胶水代码**（glue code），换个项目就得重写。

#### 问题三：功能简陋

传统 Function Calling 只支持最基础的 "请求→响应" 模型，缺少：

| 缺失能力 | 为什么重要 |
|----------|-----------|
| 流式输出（Streaming） | 工具执行时间可能很长，用户需要实时看到进度 |
| 进度反馈（Progress） | 大文件处理、批量操作时，用户需要知道完成了多少 |
| 取消操作（Cancellation） | 用户改变主意或工具卡住时，需要能中断执行 |
| 资源发现（Resource Discovery） | LLM 需要能主动发现有哪些数据源可用 |
| 提示模板（Prompt Templates） | 标准化复用高质量提示词 |

### 2.2 N×M 集成困境

这是 MCP 要解决的最核心问题。

**传统模式（N×M 集成）：**

```
              ┌──────────────┐
              │   AI App 1   │
              └──┬───┬───┬───┘
                 │   │   │
        ┌────────┘   │   └────────┐
        ▼            ▼            ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Tool A  │ │ Tool B  │ │ Tool C  │
   └─────────┘ └─────────┘ └─────────┘
        ▲            ▲            ▲
        │            │            │
   ┌────┴──────┬─────┴──────┬─────┴──────┐
   │   AI App 2   │   AI App 3   │ ... │
   └─────────────┘─────────────┘────────────┘

   集成代码量 = N (AI 应用) × M (工具)
   上图中：3 × 3 = 9 套集成代码
   实际场景：10 × 50 = 500 套集成代码
```

**MCP 模式（N+M 集成）：**

```
   ┌─────────┐  ┌─────────┐  ┌─────────┐
   │AI App 1 │  │AI App 2 │  │AI App 3 │  ... (N 个)
   └────┬─────┘  └────┬─────┘  └────┬─────┘
        │              │              │
        └──────────────┼──────────────┘
                       │
              ┌────────▼────────┐
              │   MCP Protocol  │ ← 统一协议层
              └────────┬────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
   ┌────▼─────┐  ┌────▼─────┐  ┌────▼─────┐
   │  Tool A  │  │  Tool B  │  │  Tool C  │  ... (M 个)
   └──────────┘  └──────────┘  └──────────┘

   集成代码量 = N (AI 应用适配) + M (工具实现)
   上图中：3 + 3 = 6 套集成代码
   实际场景：10 + 50 = 60 套集成代码
```

**数学本质**：MCP 将 O(N×M) 的复杂度降为 O(N+M)。

### 2.3 真实业务场景的痛点对照

| 场景 | 传统模式的困境 | MCP 如何解决 |
|------|---------------|-------------|
| 多团队协作 | 团队 A 写的工具团队 B 用不了 | 统一协议，工具可跨团队共享 |
| 多 AI 应用 | ChatGPT、Claude、Copilot 各写一套集成 | 一次编写 MCP Server，所有支持 MCP 的应用都能用 |
| 工具数量增长 | 每增加一个工具，所有 AI 应用都要更新 | 新工具注册到 MCP Server 即可，AI 应用自动发现 |
| 切换 LLM 提供商 | 工具 Schema 要全部重写 | MCP 屏蔽 LLM 差异，工具定义一次完成 |
| 工具能力复杂 | 文件操作、数据库查询、流式响应难以标准化 | MCP 原语（Tools/Resources/Prompts）统一抽象 |

### 2.4 扩展协议横向对比

Function Calling 不是 MCP 唯一的参照系。在实际面试和架构选型中，你会被问到以下更"刁钻"的对比问题。下面逐一拆解。

#### 2.4.1 MCP（JSON-RPC）与 gRPC 的对比

**核心问题**：gRPC 使用 Protocol Buffers 做序列化，性能远超 JSON；gRPC 有强类型 IDL，IDE 支持好。为什么 MCP 不直接用 gRPC？

gRPC 中的 **g** 最初代表 **Google**，因为该框架由 Google 开发并开源；而 **RPC** 是 **Remote Procedure Call**（远程过程调用）的缩写，指允许程序像调用本地函数一样调用远程服务器上功能的通信技术。

```
┌─────────────────────────────────────────────────────────────────┐
│               MCP (JSON-RPC) vs gRPC 设计哲学对比                 │
│                                                                 │
│  维度          JSON-RPC (MCP)         gRPC                      │
│  ────────────  ───────────────────    ────────────────────────  │
│  序列化格式     JSON (文本)            Protobuf (二进制)          │
│  序列化效率     低 (文本解析+膨胀)      高 (紧凑二进制，快 3-10x)  │
│  人类可读性     ✅ 直接可读             ❌ 需工具解码              │
│  类型系统       弱 (JSON Schema)       强 (Protobuf IDL)         │
│  代码生成       无 (手写消息解析)       有 (protoc 自动生成)       │
│  HTTP/2 依赖   无 (传输无关)           强 (重度依赖 HTTP/2)        │
│  浏览器支持     ✅ 原生 fetch/SSE       ❌ 需 grpc-web 代理       │
│  调试难度       低 (curl/nc 即可)       高 (需 grpcurl/BloomRPC)  │
│  学习曲线       极低 (JSON 人人会)      中高 (Proto 语法+工具链)   │
│  生态兼容性     极高 (LSP 验证)         中 (后端微服务主流)        │
└─────────────────────────────────────────────────────────────────┘
```

### Fetch（准确拼写）

- **是什么**：现代浏览器提供的一个 **Web API**，用于在 JavaScript 中发起网络请求（例如获取数据、提交表单等）。
- **特点**：基于 **Promise**，语法比传统的 `XMLHttpRequest` 更简洁、灵活。常用于替代 AJAX。
- **示例**：`fetch('https://api.example.com/data') .then(response => response.json()) .then(data => console.log(data));`

### SSE（Server-Sent Events）

- **是什么**：一种允许服务器 **主动向客户端推送数据** 的技术。客户端通过 HTTP 建立一个长连接，服务器可以持续发送事件流（文本数据）。
- **特点**：
  - 单向通信：服务器 → 浏览器。
  - 基于 HTTP（比 WebSocket 更简单，自动重连）。
  - 数据格式固定（`text/event-stream`），通常用于实时通知、股票报价、新闻推送等。

**curl** 和 **nc** 都是非常常用的网络命令行工具。

### curl
- **全称**：Client URL
- **是什么**：一个功能强大的命令行工具，用于**通过 URL 发送或接收数据**，支持 HTTP、HTTPS、FTP、SFTP、SMTP 等几十种协议。
- **常见用途**：
  - 测试 API 接口：`curl https://api.example.com/users`
  - 下载文件：`curl -O https://example.com/file.zip`
  - 发送 POST 请求：`curl -X POST -d "name=John" https://example.com/api`
  - 查看响应头：`curl -I https://google.com`
- **特点**：几乎每台 Linux/macOS 都有，Windows 10+ 也内置，是调试网络、REST API、gRPC-gateway 等场景的首选工具。

###  nc（netcat）
- **全称**：NetCat（网络瑞士军刀）
- **是什么**：一个用于**任意 TCP/UDP 网络连接读写**的工具，可以建立监听、发送原始数据、端口扫描、传输文件等。
- **常见用途**：
  - **端口测试**：`nc -zv example.com 80`（检查 80 端口是否开放）
  - **建立聊天/传输**：服务端 `nc -l 1234`，客户端 `nc server_ip 1234`，双方可互发文本
  - **手动发送 HTTP 请求**：`echo -e "GET / HTTP/1.0\n\n" | nc example.com 80`
  - **端口转发/代理**：`nc -l 8080 -c "nc backend 80"`
  - **调试 gRPC 或其他基于 TCP 的服务**：查看原始数据帧（虽然对 HTTP/2 需要更细致解码）
- **注意**：不同系统下 `nc` 可能有变种（如 `ncat`、`netcat-openbsd`），但核心功能相似。

### 两者对比
| 工具 | 协议层                       | 典型场景                                     |
| ---- | ---------------------------- | -------------------------------------------- |
| curl | 应用层协议（HTTP/FTP等）     | 调用 API、下载网页、测试 REST/gRPC-Web       |
| nc   | 传输层（TCP/UDP 原始socket） | 端口扫描、手工构造任意协议包、调试网络连通性 |

如果你是在调试 gRPC 服务，**curl** 可以配合 `grpcurl`（专门用于 gRPC 的 curl-like 工具）使用，而 **nc** 通常用于检查端口是否可达或抓取原始字节流。







**为何选择 JSON-RPC 而非 gRPC？——四个关键理由：**

**理由一：AI 工具调用的延迟瓶颈不在序列化**

```
一次典型的 MCP 工具调用延迟分解：

  JSON 序列化:    ~0.05ms   ← 几乎可忽略
  JSON 反序列化:  ~0.1ms    ← 几乎可忽略
  网络传输:       ~1-10ms   ← 非主导因素
  工具执行:       ~50-5000ms ← ★ 绝对瓶颈（数据库查询、API 调用）
  LLM 推理:       ~200-2000ms ← ★ 第二大瓶颈

结论：即使 gRPC 将序列化开销从 0.15ms 降到 0.02ms，对端到端延迟的改善 < 0.01%。
      优化序列化格式对 MCP 场景几乎没有实际收益。
```

**理由二：工具 Schema 的自描述性优先于类型安全**

MCP 的工具定义需要自描述——LLM 通过读取文本描述来理解工具的用途。JSON 原生支持运行时可见的 `description` 字段**，而 Protobuf 的注释在编译后丢失：**

```protobuf
// gRPC：注释在编译后消失，LLM 无法读取
service WeatherService {
  rpc GetWeather(WeatherRequest) returns (WeatherResponse); // 描述丢失
}
message WeatherRequest {
  string city = 1;  // 这条注释同样丢失
}
```

```json
// MCP/JSON：所有描述运行时可见，LLM 直接"读懂"
{
  "name": "get_weather",
  "description": "获取指定城市的实时天气信息，返回温度、湿度、风速",
  "inputSchema": {
    "properties": {
      "city": { "type": "string", "description": "城市名称，支持中英文" }
    }
  }
}
```

**理由三：传输无关性 > 协议强绑定**

gRPC 重度依赖 HTTP/2，在以下 MCP 核心场景中直接不可用：

| 场景 | gRPC | JSON-RPC (MCP) |
|------|------|----------------|
| stdio 本地进程通信 | ❌ 不支持 | ✅ 原生支持 |
| 浏览器直接连接 | ❌ 需 grpc-web 代理 | ✅ 原生 fetch / SSE |
| 云函数 (FaaS)Function as a Service，函数即服务 | ❌ 部分支持 | ✅ Streamable HTTP Stateless 模式 |
| curl 手动调试 | ❌ 不可行 | ✅ 一行命令 |

**理由四：LSP 生态验证了 JSON-RPC 的可行性**

LSP 自 2016 年起在 VS Code 中使用 JSON-RPC，每天处理数十亿条消息，服务数百万开发者。MCP 选择同样的协议路径是为了降低技术风险——这条路线已经被充分验证。

> **面试金句**："gRPC 是为微服务间高性能通信设计的，MCP 是为 AI 工具发现和调用设计的。两者的核心场景不同——gRPC 优化的是序列化效率，MCP 优化的是自描述性和接入成本。gRPC 让你跑得更快，JSON-RPC 让更多人愿意来跑。"

#### 2.4.2 WebSocket 与 Streamable HTTP 的对比

**核心问题**：WebSocket 是成熟的双向通信协议，为什么 MCP 新增 Streamable HTTP 而不是直接用 WebSocket？

```
┌─────────────────────────────────────────────────────────────────┐
│          WebSocket vs Streamable HTTP 在 MCP 场景的对比          │
│                                                                 │
│  维度            WebSocket              Streamable HTTP         │
│  ──────────────  ────────────────────   ──────────────────────  │
│  协议层级        独立协议 (升级 HTTP)    标准 HTTP/1.1            │
│  连接模型        持久长连接              按需连接 + 可选流式响应   │
│  穿透代理        ❌ 困难 (需 Upgrade)     ✅ 天然穿透 (标准 HTTP)  │
│  负载均衡        ❌ 需 sticky session    ✅ 无状态路由             │
│  Serverless      ❌ 不支持 (长连接)       ✅ Stateless 模式天然支持 │
│  断线重连        需手动实现              无需重连 (每个请求独立)   │
│  服务端推送      ✅ 原生双向              ✅ Stateful 模式 SSE 流  │
│  状态管理        隐式 (连接 = 会话)       显式 (Mcp-Session-Id)    │
└─────────────────────────────────────────────────────────────────┘
```

**为什么 Streamable HTTP 而非 WebSocket？——三个决定性因素：**

**因素一：企业代理/防火墙兼容性**

```
WebSocket 在企业网络中的痛苦：
  Client → 企业 HTTP 代理 → Server
           常见的 WebSocket 问题：
           · 代理不支持 Upgrade 头 → WebSocket 直接被拒
           · 代理空闲超时断开连接（无法配置 keepalive）
           · HTTP/2 代理可能完全不支持 WebSocket

Streamable HTTP：
  每个请求都是标准 HTTP POST/GET，任何 HTTP 代理都支持。
  这就是 HTTP 能穿透几乎所有防火墙的原因——它就是 Web 本身。
```

**因素二：Serverless 亲和性**

WebSocket 要求 Server 维护长连接，与 FaaS（Lambda / 云函数 / Cloud Run）"用完即走"的模型根本冲突。Streamable HTTP 的 Stateless 模式天然适配 Serverless 部署。

**因素三：弹性伸缩友好**

WebSocket 连接绑定到特定 Pod，水平伸缩时需要特殊处理连接迁移。Streamable HTTP 的每个请求可路由到任意 Pod，对 K8s HPA 完全透明。

> **面试金句**："WebSocket 解决的是'实时双向'，Streamable HTTP 解决的是'可靠灵活'。在 MCP 的场景中，跨网络环境的可靠性比全双工实时性更重要。"

#### 2.4.3 GraphQL Schema Introspection 与 MCP 工具发现机制

**核心问题**：两者都解决了"让调用方知道服务方能提供什么"的问题，设计思想有何异同？

```
┌─────────────────────────────────────────────────────────────────┐
│      GraphQL Schema Introspection  vs  MCP tools/list           │
│                                                                 │
│  共同点：                                                        │
│  · 都允许调用方在运行时查询"你能做什么"                           │
│  · 都使用类型系统描述能力（GraphQL Type System / JSON Schema）    │
│  · 都支持嵌套和复杂参数结构                                       │
│                                                                 │
│  关键差异：                                                      │
│                                                                 │
│  维度            GraphQL Introspection   MCP tools/list          │
│  ──────────────  ──────────────────────  ──────────────────────  │
│  服务对象        人类开发者                AI 模型 (LLM)          │
│  描述语言        类型定义 (SDL)           自然语言 (description)   │
│  发现粒度        字段级 (field)           工具级 (tool)           │
│  语义理解        依赖开发者经验            description 驱动 LLM   │
│  更新通知        ❌ 无标准机制              ✅ tools/list_changed  │
│  版本管理        ❌ 无 (需额外工具)          ✅ protocolVersion     │
│  可执行性        声明式查询                RPC 式调用              │
└─────────────────────────────────────────────────────────────────┘
```

**设计思想的分野：**

GraphQL Introspection 设计哲学是"让机器可读的 Schema 自动生成文档"——服务人类开发者。MCP tools/list 设计哲学是"让 AI 能自主理解工具用途"——服务 AI 模型。这决定了最关键的差异：GraphQL 面向类型（`String!`、`[User!]!`），MCP 面向语义（自然语言 description）。对 LLM 来说，类型约束是次要信息，语义描述才是决定是否调用工具的核心判断依据。

> **关键认知**：当 API 的消费者从人类变成 AI 时，"描述质量"比"类型精确度"更重要。

---

## 三、如何实现——MCP 的核心架构

### 3.1 三层架构模型

MCP 采用 **Host → Client → Server** 三层架构：

```
┌─────────────────────────────────────────────────────┐
│                      HOST（宿主）                     │
│  职责：管理客户端连接、权限控制、安全沙箱、UI 交互      │
│  实例：Claude Desktop、VS Code Extension、Cursor      │
│                                                     │
│  ┌───────────────────────────────────────────────┐  │
│  │                CLIENT（客户端）                 │  │
│  │  职责：协议消息路由、心跳维护、订阅管理、        │  │
│  │         能力协商、通知分发                      │  │
│  │  每个 Client 与一个 Server 建立 1:1 连接        │  │
│  └─────────────────┬─────────────────────────────┘  │
│                    │  JSON-RPC 2.0                   │
│                    │  (stdio / SSE / WebSocket)      │
│  ┌─────────────────▼─────────────────────────────┐  │
│  │                SERVER（服务器）                  │  │
│  │  职责：暴露 MCP 原语、执行具体能力              │  │
│  │  原语：Tools · Resources · Prompts             │  │
│  └───────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

#### Host（宿主）—— 应用级管理者

- **生命周期管理**：负责启动和关闭 MCP Client 进程
- **权限控制（Capability Negotiation）**：声明 Host 支持哪些能力，协商确定实际可用的能力合集
- **安全沙箱**：限制工具的执行范围（如只读文件、禁止网络访问）
- **用户交互**：UI 层面向用户的提示和确认界面

> 举例：当你在 Claude Desktop 中使用 MCP 工具时，弹窗询问 "是否允许此工具访问你的文件系统？"——这就是 Host 在履行权限管理职责。

#### Client（客户端）—— 协议路由层

- **1:1 通信**：每个 Client 实例与**一个** MCP Server 建立连接
- **消息路由**：将 LLM 的工具调用请求路由到对应的 Server
- **能力声明**：在连接建立时声明自己支持的能力（Client Capabilities）
- **订阅管理**：管理 Server 的资源变更订阅
- **通知分发**：将 Server 的变更通知推送给 LLM

```python
# Client 的能力声明示例
{
    "capabilities": {
        "roots": {
            "listChanged": True   # 支持监听根目录变更
        },
        "sampling": {},           # 支持采样（让 Server 反向请求 LLM）
        "experimental": {
            "feature_x": {}       # 实验性功能
        }
    }
}
```

#### Server（服务器）—— 能力提供层

Server 通过三种**原语（Primitives）**暴露能力：

| 原语 | 用途 | 示例 |
|------|------|------|
| **Tools** | 可执行的函数，LLM 可以调用 | `get_weather`、`search_db`、`send_email` |
| **Resources** | 可读取的数据源，支持订阅变更 | 文件内容、数据库记录、API 响应 |
| **Prompts** | 预定义的提示词模板 | 代码审查模板、翻译助手模板 |

```python
# Server 端工具定义示例
@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_weather",
            description="获取指定城市的实时天气信息",
            inputSchema={
                "type": "object",
                "properties": {
                    "city": {
                        "type": "string",
                        "description": "城市名称，如 '北京'、'Tokyo'"
                    }
                },
                "required": ["city"]
            }
        )
    ]
```

2025 年初，MCP 官方宣布 **Sampling 原语已废弃**，不再推荐使用。



### 3.2 MCP 的三个核心原语详解

#### 3.2.1 Tools（工具）—— "让 LLM 能做事"

Tools 是 MCP 中最常用的原语，代表 **LLM 可以执行的操作**。

**核心特征：**

- 模型控制（Model-controlled）：由 LLM 决定何时、以什么参数调用工具
- 可执行（Executable）：每个工具对应一个真实的函数执行
- 带 Schema（Structured）：每个工具都有结构化的输入定义（JSON Schema）

**完整交互流程：**

```
1. Client 发送 tools/list 请求
2. Server 返回可用工具列表（含名称、描述、参数 Schema）
3. LLM 分析用户意图，决定调用某个工具
4. Client 发送 tools/call 请求（含工具名 + 参数）
5. Server 执行工具逻辑
6. Server 返回 tools/call 响应（含执行结果）
7. LLM 根据结果生成最终回复
```

#### 3.2.2 Resources（资源）—— "让 LLM 能读到数据"

Resources 代表 **LLM 可以读取的上下文数据**。

**与 Tools 的关键区别：**

| 维度 | Tools | Resources |
|------|-------|-----------|
| 读写性 | 写（执行操作） | 读（获取数据） |
| 触发方式 | LLM 主动调用 | LLM 阅读 / Server 推送 |
| 是否幂等 | 不一定 | 是（读取操作天然幂等） |
| 订阅机制 | 无 | 有（支持变更通知） |

**Resource 的 URI 规范：**

```
[scheme]://[host]/[path]

示例：
  file:///home/user/document.txt        → 本地文件
  postgres://database/schema/table       → 数据库表结构
  api://internal/employees               → 内部 API 数据
  project://myproject/docs/readme        → 项目内的文档
```

**资源订阅（Resource Subscription）机制：**

```
┌─────────┐                     ┌─────────┐
│  Client  │                     │  Server  │
└────┬─────┘                     └────┬─────┘
     │                                │
     │  resources/subscribe           │
     │  {uri: "file:///log/app.log"}  │
     │ ─────────────────────────────> │
     │                                │ 开始监听文件变更
     │  resources/updated             │
     │  {uri: "file:///log/app.log"}  │
     │ <───────────────────────────── │ 文件内容变更
     │                                │
     │  (LLM 决定是否重新读取)         │
     │  resources/read                │
     │ ─────────────────────────────> │
     │  (返回最新内容)                 │
     │ <───────────────────────────── │
```

#### 3.2.3 Prompts（提示词模板）—— "让 LLM 得到更好的引导"

Prompts 是预定义的、可参数化的提示词模板。

**核心特征：**
- 用户控制（User-controlled）：由用户选择使用，而非 LLM 自动触发
- 可参数化：支持占位符，按需填充
- 可组合：可包含 Resources 和 Tools 的引用

```python
@server.list_prompts()
async def list_prompts() -> list[Prompt]:
    return [
        Prompt(
            name="code_review",
            description="对代码进行专业审查",
            arguments=[
                PromptArgument(
                    name="language",
                    description="编程语言",
                    required=True
                ),
                PromptArgument(
                    name="code",
                    description="待审查的代码",
                    required=True
                )
            ]
        )
    ]

@server.get_prompt()
async def get_prompt(name: str, arguments: dict) -> GetPromptResult:
    if name == "code_review":
        return GetPromptResult(
            messages=[
                PromptMessage(
                    role="user",
                    content=TextContent(
                        type="text",
                        text=f"""请对以下 {arguments['language']} 代码进行专业审查，从以下角度分析：
1. 代码正确性
2. 性能优化建议
3. 安全漏洞检测
4. 可维护性评价

```{arguments['language']}
{arguments['code']}
```"""
                    )
                )
            ]
        )
```

### 3.3 传输层支持

MCP 目前支持三种传输机制：

| 传输方式 | 适用场景 | 特点 |
|----------|----------|------|
| **stdio** | 本地进程间通信 | 简单直接，无需网络端口，默认方式 |
| **SSE（Server-Sent Events）** | 远程 HTTP 通信 | 支持从浏览器连接到远程 Server |
| **Streamable HTTP** | 远程 HTTP 通信（双向流） | 支持流式请求和响应，未来可能替代 SSE |

```json
// Claude Desktop 的 MCP Server 配置示例
{
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path/to/allowed/dir"],
            "transport": "stdio"
        },
        "remote-api": {
            "url": "https://my-mcp-server.example.com/mcp",
            "transport": "sse"
        }
    }
}
```

### 3.4 设计权衡：MCP 选择牺牲了什么

理解一个协议的设计，不能只看它"能做"什么，更要看它**选择不做**什么。MCP 的每个设计决策背后都有刻意的取舍。

#### 3.4.1 简单性与灵活性——为何只定义 3+1 个原语？

**MCP 的原语设计遵循"极简主义"：**

```
Tools    (模型控制执行)     ← LLM 决定调哪个
Resources (应用控制读取)    ← Client 决定读什么
Prompts  (用户控制交互)     ← 用户选择模板
Sampling (Server 反向请求)  ← 第 4 个，并非所有实现都包含
```

**为什么是 3+1 而不是 10 个？——"原语膨胀"的假设对照：**

| 如果增加这个原语 | 实际上等价于 | 为什么不单独定义 |
|------------------|-------------|-----------------|
| `Workflows` | 多个 `tools/call` 的顺序组合 | 编排是 Host/编排框架的责任，不是协议层的事 |
| `Agents` | 带有状态和决策能力的 Server | Agent 是比 MCP 更高层的抽象，属于 A2A 范畴 |
| `Streams` | 返回流式内容的 Resource | 已被 Streamable HTTP + 流式 Tool 结果覆盖 |
| `Plugins` | 带 UI 交互的 Tool | UI 是 Host 层的职责，MCP 只管数据通道 |

**极简设计的边界——MCP 力不能及的场景：**

```
✅ MCP 原语能覆盖的                     ❌ MCP 原语力不能及的
════════════════════                   ═════════════════════

LLM 调用工具获取数据                    定义多 Agent 协作流程
LLM 读取文件/数据库内容                 管理 Agent 间的对话状态
用户选择提示词模板引导 LLM              定义 UI 交互（按钮、表单等）
Server 请求 LLM 帮忙做推理              定义工具的定价和计费模型
Server 推送资源变更通知                 实现工具的 A/B 测试
```

> **设计哲学**："一个好的协议不是功能最多的协议，而是边界最清晰的协议。MCP 的 3+1 原语覆盖了 LLM 与外部世界交互的四个基本方向，而把编排、UI、计费留给其他层。这种克制本身就是一种智慧。"

#### 3.4.2 标准化与性能——JSON 文本协议的代价

**代价一：序列化膨胀率**

```
同样的数据，不同序列化格式的大小对比：

天气查询结果 → {"city":"北京","temperature":25,"humidity":45,"condition":"晴"}

JSON:        ~75 bytes  (基准)
Protobuf:    ~20 bytes  (缩小 73%)
MessagePack: ~45 bytes  (缩小 40%)

对 MCP 场景的影响评估：
  · 工具参数通常 < 1KB → JSON 膨胀可忽略
  · 工具结果通常 < 10KB → JSON 膨胀 < 3KB
  · 文件 Resource 内嵌 base64 → 33% 膨胀 ← 唯一需要关注的场景
```

**代价二：无原生流式分帧**

JSON-RPC 的 stdio 模式用换行符分帧——这意味着 JSON 消息不能包含未转义的换行符（不能 pretty-print）。这是一个工程约束，但通常不构成实际障碍。

**性能瓶颈的真相——什么场景下需要重新评估？**

```
┌─────────────────────────────────────────────────────┐
│ 场景                      序列化占比    需要优化？   │
├─────────────────────────────────────────────────────┤
│ 典型工具调用 (1KB 参数)      < 0.01%    否           │
│ 大数据库查询 (100KB 结果)    < 0.1%     否           │
│ 图片/音频内嵌返回 (1MB+)     ~33%       重新评估     │
│ 高频调用 (>1000 QPS)        ~1-5%      重新评估     │
│ 超低延迟要求 (<10ms e2e)    ~5-10%     重新评估     │
└─────────────────────────────────────────────────────┘

需要重新评估的场景（MCP 当前设计可能力不从心）：
1. 高频实时数据流（如每秒数千次 stock ticker 查询）
   → 可考虑 gRPC Stream 或专用二进制通道
2. 大体积二进制传输（视频、大图片）
   → MCP 支持 Resource URI 返回 URL 引用，而非内嵌 base64
3. 超低延迟场景（如自动驾驶中 Agent 调用传感器）
   → MCP 的设计目标本不包含硬实时场景
```

> **面试金句**："MCP 用 JSON 的性能代价换取了可调试性和低门槛。在 99% 的 AI 工具调用场景中，工具本身的执行时间（50-5000ms）远大于 JSON 的序列化开销（<1ms）。当序列化真的成为瓶颈时，通过 Resource URI 返回二进制引用而非内嵌 base64，即可绕开。"

#### 3.4.3 安全性与便利性——Server 看不到对话历史的设计

这是 MCP **最容易被误判为"缺陷"的设计**——初看限制了功能，实则是深思熟虑的安全架构选择。

**安全收益（为什么这个设计是正确的）：**

```
1. 防止恶意 Server 窃取对话信息
   · 对话中可能包含商业机密、个人隐私、系统内部信息
   · 如果 Server 能读全量历史 → 数据泄露风险不可控

2. 最小信息暴露原则
   · Server 只应该知道完成当前任务所需的最少信息
   · 这是信息安全的基本要求

3. 跨 Server 数据隔离
   · Server A 无法知道 Server B 之前被调用了什么
   · 一个被攻破的 Server 无法获取其他 Server 的数据

4. 简化合规审计
   · 每个 Server 的数据处理边界清晰
   · GDPR / 个人信息保护法的"数据最小化"合规成本低
```

**功能损失（Agentic 场景下的代价）：**

```
1. Server 无法做"上下文感知"的工具调用
   例：用户 10 轮对话前说"我是管理员"→ Server 不知道
   → 缓解：Host 在 tools/call 参数中显式传递必要的上下文

2. Server 无法修正之前的错误
   例：用户发现前面的查询有问题，希望 Server 自动纠正
   → 缓解：用户用自然语言重新表达需求

3. 无法实现"记忆型"工具
   例："记住我叫张三，下次别问了"
   → 缓解：Server 可维护自己的会话状态（通过 session_id）

4. Multi-turn 推理被截断
   例：Server 做了第一步，LLM 要求继续
   → 缓解：Server 内部维护任务状态（task_id）
```

**权衡判断**：Anthropic 明确地将**安全置于便利性之前**。在个人工具和实验中，对话历史隔离可能显得"不方便"；但在企业生产和合规环境中，这种隔离**不是功能缺失，而是必备的安全特性**。

> **面试金句**："有人说 MCP 不够灵活，因为让 Server 看不到对话历史。我说这恰恰是 MCP 最深思熟虑的设计——它把安全做进了架构层面，而不是事后叠加。在 AI Agent 时代，让每个工具 Server 都看到全部对话历史的风险，远大于上下文感知带来的便利。"

---

## 四、底层原理——协议细节与消息流转

### 4.1 协议基础：JSON-RPC 2.0

MCP 协议构建在 **JSON-RPC 2.0** 之上。JSON-RPC 是一种轻量级的远程过程调用协议，使用 JSON 作为数据格式。

#### 消息格式

**请求（Request）：**

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
        "name": "get_weather",
        "arguments": {
            "city": "北京"
        }
    }
}
```

**响应（Response）：**

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "result": {
        "content": [
            {
                "type": "text",
                "text": "北京当前天气：晴，气温 25°C，湿度 45%"
            }
        ]
    }
}
```

**通知（Notification）—— 无 id，无需响应：**

```json
{
    "jsonrpc": "2.0",
    "method": "notifications/resources/updated",
    "params": {
        "uri": "file:///data/report.json"
    }
}
```

**错误响应：**

```json
{
    "jsonrpc": "2.0",
    "id": 1,
    "error": {
        "code": -32602,
        "message": "Invalid params",
        "data": "Parameter 'city' is required but missing"
    }
}
```

#### JSON-RPC 选择理由

| 考量维度 | JSON-RPC 2.0 的优势 |
|----------|---------------------|
| **简单性** | 比 REST 更简单，无需关注 HTTP method 语义 |
| **双向通信** | 支持 Request 和 Notification（单向通知）两种模式 |
| **传输无关** | 可运行在 stdio、HTTP、WebSocket 等任何传输层上 |
| **生态兼容** | 被 LSP（Language Server Protocol）广泛验证 |

> MCP 的设计深受 LSP 的影响。LSP 也是基于 JSON-RPC，定义了编辑器与语言服务器之间的协议——这与 MCP 的 "AI 应用 ↔ 工具服务器" 模式是同构的。

### 4.2 完整的生命周期

MCP 连接从建立到关闭经历以下阶段：

```
┌──────────────────────────────────────────────────────┐
│                  1. 初始化 (Initialize)                │
│  Client → Server: initialize 请求                     │
│  (携带协议版本 + Client 能力声明)                      │
│  Server → Client: initialize 响应                     │
│  (携带协议版本 + Server 能力声明)                      │
│  Client → Server: initialized 通知                    │
│  (确认连接建立完成)                                    │
└──────────────────┬───────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────┐
│              2. 能力协商 (Capability Negotiation)       │
│  双方根据对方声明的 capabilities 确定可用功能集         │
│  例如：如果 Server 声明 support_structured_output，     │
│        Client 可以以结构化格式请求工具结果              │
└──────────────────┬───────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────┐
│              3. 正常运行 (Normal Operation)             │
│  ┌─────────────────────────────────────────────┐     │
│  │ tools/list   → 获取可用工具列表               │     │
│  │ tools/call   → 调用指定工具                   │     │
│  │ resources/read → 读取资源内容                 │     │
│  │ resources/subscribe → 订阅资源变更             │     │
│  │ prompts/list → 获取提示词模板列表              │     │
│  │ prompts/get  → 获取填充后的提示词              │     │
│  └─────────────────────────────────────────────┘     │
└──────────────────┬───────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────┐
│              4. 连接关闭 (Shutdown)                    │
│  Client → Server: shutdown 请求                       │
│  Server 停止接收新请求，完成进行中的任务                │
│  Server 释放资源后关闭连接                             │
└──────────────────────────────────────────────────────┘
```

#### 初始化阶段——协议版本协商

```
Client                              Server
  │                                    │
  │  initialize                        │
  │  {                                 │
  │    "protocolVersion": "2024-11-05",│
  │    "capabilities": {...},          │
  │    "clientInfo": {                 │
  │      "name": "ClaudeDesktop",      │
  │      "version": "1.2.3"           │
  │    }                               │
  │  }                                 │
  │ ─────────────────────────────────> │
  │                                    │
  │                     initialize     │
  │  {                                 │
  │    "protocolVersion": "2024-11-05",│
  │    "capabilities": {               │
  │      "tools": {},                  │
  │      "resources": {                │
  │        "subscribe": true           │
  │      }                             │
  │    },                              │
  │    "serverInfo": {                 │
  │      "name": "WeatherServer",      │
  │      "version": "2.0.0"           │
  │    }                               │
  │  }                                 │
  │ <───────────────────────────────── │
  │                                    │
  │  initialized (notification)        │
  │ ─────────────────────────────────> │
  │                                    │
  │  [进入正常运行状态]                  │
```

**版本兼容性规则：**
- 如果 Client 和 Server 的协议版本不兼容，初始化阶段即告失败
- `protocolVersion` 使用发布日期作为版本号（如 `2024-11-05`）
- 未来版本之间可能通过能力声明（capabilities）实现向下兼容

### 4.3 完整调用链路——以"查询天气"为例

```
┌─────────┐     ┌─────────┐     ┌──────────┐     ┌─────────┐
│ 用户     │     │  Host   │     │  Client  │     │  Server │
│         │     │(Claude) │     │          │     │(Weather)│
└────┬────┘     └────┬────┘     └────┬─────┘     └────┬────┘
     │               │               │                 │
     │ "北京天气?"    │               │                 │
     │──────────────>│               │                 │
     │               │               │                 │
     │               │               │  tools/list     │
     │               │               │────────────────>│
     │               │               │   [get_weather, │
     │               │               │    search_city] │
     │               │               │<────────────────│
     │               │               │                 │
     │               │  LLM 分析:                     │
     │               │  用户想查天气                    │
     │               │  选择 get_weather 工具           │
     │               │  提取参数 city="北京"            │
     │               │               │                 │
     │               │               │  tools/call     │
     │               │               │  {name:         │
     │               │               │   "get_weather",│
     │               │               │   arguments:    │
     │               │               │   {city:"北京"}}│
     │               │               │────────────────>│
     │               │               │                 │
     │               │               │                 │ 调用天气 API
     │               │               │                 │────────┐
     │               │               │                 │        │
     │               │               │                 │<───────┘
     │               │               │                 │
     │               │               │  返回结果        │
     │               │               │<────────────────│
     │               │               │                 │
     │               │  LLM 整合结果                    │
     │               │  生成自然语言回复                │
     │               │               │                 │
     │  "北京今天晴，  │               │                 │
     │   气温25°C..." │               │                 │
     │<──────────────│               │                 │
```

### 4.4 错误处理模型

MCP 定义了两层错误处理：

**协议层错误（JSON-RPC 标准错误码）：**

| 错误码 | 含义 | 触发场景 |
|--------|------|----------|
| `-32700` | Parse Error | 收到的 JSON 格式不合法 |
| `-32600` | Invalid Request | 不是合法的 JSON-RPC 请求 |
| `-32601` | Method Not Found | 调用的方法不存在 |
| `-32602` | Invalid Params | 参数类型或格式错误 |
| `-32603` | Internal Error | Server 内部执行异常 |

**应用层错误（工具执行结果中的 isError 标记）：**

```json
{
    "jsonrpc": "2.0",
    "id": 42,
    "result": {
        "content": [
            {
                "type": "text",
                "text": "数据库连接失败：connection refused"
            }
        ],
        "isError": true
    }
}
```

> **关键设计**：工具执行失败通过 `isError: true` 标记在 result 中返回，而不是通过 JSON-RPC 的 error 对象。这是因为 "工具执行失败" ≠ "协议通信失败"——前者是业务层的正常情况（比如查不到数据），后者才是通信异常。

---

## 五、企业级最佳实践

### 5.1 是否采用 MCP——决策框架

```
                    你的场景是什么？
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
    1-2个简单工具    5+个工具/服务   需要跨多AI应用
    单一LLM          多团队协作        复用工具
          │              │              │
          ▼              ▼              ▼
    用 Function      建议采用         必须采用
    Calling 即可      MCP              MCP
                         │
          ┌──────────────┴──────────────┐
          ▼                             ▼
    先看 §5.1.2 "什么时候不该用 MCP"     继续看 §5.1.1 量化标准
    确认不在反面清单中                  做精确计算
```

#### 5.1.1 量化决策标准

"1-2 个工具用 Function Calling，更多用 MCP"的判断偏经验直觉。以下提供可量化的评估模型，用于面试中展示工程决策能力。

**一、Token 消耗的临界点计算**

`ConvTurns` 表示对话中请求模型的轮次

```
核心公式：

  Function Calling 的 Token 消耗:
  TotalTokens_FC = SchemaSize × ConvTurns + ToolResultTokens

  MCP 的 Token 消耗:
  TotalTokens_MCP = ToolResultTokens
                   (tools/list 结果不在 prompt 中，不计入)

  差异 = SchemaSize × ConvTurns

  代入典型值：
  · 一个中等复杂的工具 Schema ≈ 150 tokens
  · 10 个工具 ≈ 1,500 tokens/轮
  · 平均对话 5 轮 → 7,500 tokens 差异
  · 按 GPT-4o 定价 ($2.5/1M input) → $0.019/次对话

  看起来差异不大？考虑高频场景：
  · 每日 10,000 次对话 → $190/天 → $69,350/年
  · 每日 100,000 次对话 → $1,900/天 → $693,500/年

  Schema 更多的极端情况：
  · 复杂工具 Schema (500 tokens) × 50 个工具 = 25,000 tokens/轮
  · 5 轮对话 = 125,000 tokens 差异
  · 每日 10,000 次对话 → $3,125/天 → $1.14M/年
```

### 无 MCP（传统 Function Calling）

- 每次你想让模型使用工具，都必须把**所有工具的名字、参数描述、JSON Schema** 塞进 API 请求的 `tools` 字段里。
- 即使用户连续 10 轮对话都在使用同一个简单工具（比如“获取当前时间”），模型每次思考前都要重新读取一遍那段冗长的 Schema。
- **消耗** = 每轮都支付 `SchemaSize` 个 Token。

### 有 MCP

- 工具定义通过 MCP 协议**提前注册**到模型服务端（或者通过外部上下文管理器维护），模型内部已经知道工具有哪些、怎么调用。
- 每次请求时，你**不需要**再发送那些工具定义，只需要在需要调用时传一个极小的标识（如工具名称和参数）。
- 模型可以直接执行工具，并把结果返回。
- **消耗** = 仅支付工具返回结果的 Token，**完全没有** 重复的 Schema 开销。





---

## 传统 Function Calling 为什么每轮都要发 Schema？

因为大模型 API（比如 OpenAI）的设计是：**模型本身不记得任何工具**。每次你调用 API，必须在请求里把 `tools` 参数完整带上，模型根据你这次给的定义生成 `function_call`。

所以：
```
第1轮请求：tools=[完整Schema] + 用户消息 → 模型输出调用
第2轮请求：tools=[完整Schema] + 上一轮结果 + 新消息 → 模型输出调用
...
每轮都要重复发送完整的 JSON Schema，消耗 `SchemaSize × 轮次` 的 token。
```

## MCP 是怎么做的？它并没有改变模型 API 的规则

MCP 是一个**客户端与工具服务器之间的协议**，它不直接改变大模型 API 的调用方式。  
它省 token 的原理非常简单：**不再使用官方的 `tools` 参数，改用自然语言告诉模型工具信息。**

### 具体流程（以 OpenAI API 为例）：

1. **启动时**：你的客户端连接 MCP Server，获取工具列表（比如 `[{name:"get_weather", description:"查询天气", parameters:{city:string}}]`）。
2. **构造请求时**：你不填 `tools` 参数。而是在 `messages` 的 **system 消息或第一个 user 消息** 里，用自然语言写：
   
   > “你可以使用以下工具：  
   > - `get_weather`：查询天气，参数为城市名（字符串）。  
   > 当你想调用工具时，输出格式：`<tool_call>get_weather|{"city":"北京"}</tool_call>`。”
3. **模型收到 prompt**：模型看到自然语言描述，它知道用什么格式输出。**模型不需要 JSON Schema**，它只要按约定输出文本即可。
4. **客户端解析模型输出**：客户端看到 `<tool_call>...`，解析出工具名和参数，然后通过 MCP 调用真正的函数。
5. **把结果放回对话**：客户端把函数返回结果以普通文本形式追加到 messages，再发给模型。

### 每轮请求的 token 对比

- **传统 FC**：每次都发 500 token 的 JSON Schema。
- **MCP 方式**：只在**首轮**发一次自然语言描述（比如 50 token）。后续轮次可以不再重复描述，因为模型已经从对话历史里知道规则了。如果担心模型忘记，可以每隔几轮简短提示一句（10 token），远小于 500 token。

所以 MCP 省 token 的本质是：**用自然语言描述替代 JSON Schema，并且利用对话历史来传递工具信息，避免在每个请求中重复发送。**



用文字版流程图对比 **多个工具** 的场景，清晰展示“无 MCP”（传统 Function Calling）和“有 MCP”两种流程。

假设我们有 3 个工具：
- `get_weather`（查天气）
- `send_email`（发邮件）
- `calculate`（计算器）

用户连续对话 3 轮：
1. “北京天气如何？” → 调用 `get_weather`
2. “把结果发邮件给小明” → 调用 `send_email`
3. “计算 123*456” → 调用 `calculate`

---

## 无 MCP（传统 Function Calling）

**特点**：每次请求都要把 **3 个工具的完整 JSON Schema** 发给模型。

```
┌─────────────────────────────────────────────────────────────────┐
│ 第1轮请求                                                       │
├─────────────────────────────────────────────────────────────────┤
│ 发送给模型：                                                    │
│   tools: [                                                     │
│     { name:"get_weather", parameters:{...} },   // 200 tokens │
│     { name:"send_email",  parameters:{...} },   // 300 tokens │
│     { name:"calculate",   parameters:{...} }    // 150 tokens │
│   ]                               ← 共 650 tokens 的工具定义     │
│   + 用户消息："北京天气如何？"                                   │
├─────────────────────────────────────────────────────────────────┤
│ 模型返回：function_call = get_weather(city="北京")              │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 客户端执行 get_weather，得到结果
┌─────────────────────────────────────────────────────────────────┐
│ 第2轮请求                                                       │
├─────────────────────────────────────────────────────────────────┤
│ 发送给模型：                                                    │
│   tools: [ 同上 3 个工具定义 ]       ← 又是 650 tokens           │
│   + 消息历史：                                                   │
│       user: "北京天气如何？"                                     │
│       assistant: function_call(get_weather)                     │
│       tool_result: "25°C，晴"                                   │
│   + 新用户消息："把结果发邮件给小明"                              │
├─────────────────────────────────────────────────────────────────┤
│ 模型返回：function_call = send_email(to="xiaoming", content="25°C晴")│
└─────────────────────────────────────────────────────────────────┘
                              ↓ 客户端执行 send_email
┌─────────────────────────────────────────────────────────────────┐
│ 第3轮请求                                                       │
├─────────────────────────────────────────────────────────────────┤
│ 发送给模型：                                                    │
│   tools: [ 同上 3 个工具定义 ]       ← 又是 650 tokens           │
│   + 更长历史 + 新消息："计算123*456"                             │
├─────────────────────────────────────────────────────────────────┤
│ 模型返回：function_call = calculate(expression="123*456")       │
└─────────────────────────────────────────────────────────────────┘

总 token 消耗（仅工具定义部分）：
  650 × 3 = 1950 tokens（外加工具结果 token 和普通对话 token）
```

**结论**：3 轮请求，工具定义重复发了 3 次，浪费大量 token。

---

## 有 MCP 的流程

**核心思想**：**只在首轮用自然语言告诉模型一次**，后续轮次利用对话历史，不再重复发送工具定义。

```
┌─────────────────────────────────────────────────────────────────┐
│ 准备阶段（不消耗调用模型的 token）                               │
├─────────────────────────────────────────────────────────────────┤
│ 1. 客户端连接 MCP Server，获取工具列表：                         │
│    - get_weather: 查询天气，参数城市名                           │
│    - send_email: 发送邮件，参数收件人、内容                      │
│    - calculate: 数学计算，参数表达式                             │
│ 2. 客户端把这些工具描述转成一段自然语言（约 80 tokens）           │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ 第1轮请求                                                       │
├─────────────────────────────────────────────────────────────────┤
│ 发送给模型（系统消息 + 用户消息）：                               │
│   system: "你可以使用以下工具，输出格式<tool>工具名|JSON</tool>：│
│            - get_weather: 查询天气，参数{"city":"城市名"}        │
│            - send_email: 发邮件，参数{"to":"邮箱","content":"内容"}│
│            - calculate: 计算，参数{"expr":"算式"}                │
│            只需输出工具调用，不要解释。"         ← 约 80 tokens  │
│   user: "北京天气如何？"                                         │
├─────────────────────────────────────────────────────────────────┤
│ 模型返回：<tool>get_weather|{"city":"北京"}</tool>               │
└─────────────────────────────────────────────────────────────────┘
                              ↓ 客户端解析，通过MCP调用真实函数
┌─────────────────────────────────────────────────────────────────┐
│ 第2轮请求                                                       │
├─────────────────────────────────────────────────────────────────┤
│ 发送给模型：                                                    │
│   ⚠️ 不再重复发送工具描述（因为模型还记得 system 消息内容）      │
│   消息历史：                                                     │
│       system: (上一轮的那段工具描述)  ← 在上下文中                │
│       user: "北京天气如何？"                                     │
│       assistant: <tool>get_weather|...                           │
│       tool_result: "25°C，晴"                                   │
│   + 新用户消息："把结果发邮件给小明"                              │
├─────────────────────────────────────────────────────────────────┤
│ 模型返回：<tool>send_email|{"to":"xiaoming@example.com","content":"25°C晴"}</tool>│
└─────────────────────────────────────────────────────────────────┘
                              ↓ 客户端执行 send_email
┌─────────────────────────────────────────────────────────────────┐
│ 第3轮请求                                                       │
├─────────────────────────────────────────────────────────────────┤
│ 发送给模型：                                                    │
│   继续利用已有对话历史（system 消息仍在上下文中），                │
│   不再重复发送工具定义。                                          │
│   + 新消息："计算123*456"                                        │
├─────────────────────────────────────────────────────────────────┤
│ 模型返回：<tool>calculate|{"expr":"123*456"}</tool>              │
└─────────────────────────────────────────────────────────────────┘

总 token 消耗（工具描述部分）：
  第1轮：80 tokens（一次性发送）
  第2轮：0   tokens（复用历史）
  第3轮：0   tokens（复用历史）
  合计：80 tokens，远小于传统 FC 的 1950 tokens。
```

---

## 直观对比图（多个工具场景）

```
【无 MCP — 传统 Function Calling】

 请求1: [ 工具Schema 650 tokens ] + 消息1 → 调用get_weather
 请求2: [ 工具Schema 650 tokens ] + 历史 + 消息2 → 调用send_email
 请求3: [ 工具Schema 650 tokens ] + 历史 + 消息3 → 调用calculate
 ----------------------------------------------
 工具定义总Token: 650 × 3 = 1950


【有 MCP — 自然语言描述 + 对话历史复用】

 准备: 从MCP Server获取工具 → 转成自然语言(80 tokens)
 请求1: [ 工具描述 80 tokens ] + 消息1 → 调用get_weather
 请求2: [ 无额外工具描述 ] + 历史(含请求1的system) + 消息2 → 调用send_email
 请求3: [ 无额外工具描述 ] + 历史 + 消息3 → 调用calculate
 ----------------------------------------------
 工具描述总Token: 80
```

---

## 总结差异

| 维度               | 无 MCP（传统 FC）         | 有 MCP                                   |
| ------------------ | ------------------------- | ---------------------------------------- |
| **工具定义位置**   | 每次请求的 `tools` 参数   | 首轮 system 消息（自然语言）             |
| **每轮是否重复**   | ✅ 每次都完整重复          | ❌ 只需第一次，后续复用历史               |
| **工具数量多时**   | Token 爆炸（Schema 累加） | 几乎不变（自然语言清单）                 |
| **模型调用格式**   | 官方 `function_call` 结构 | 自定义文本标签（如 `<tool>...</tool>`）  |
| **客户端额外工作** | 无（直接调 API）          | 需解析自定义输出 + 通过 MCP 调用真实函数 |

**一句话**：MCP 让工具描述从“每轮必发的重量级 JSON Schema”变为“首轮一次性轻量自然语言”，后续轮次通过对话历史自动延续，大幅节省 token。

> **MCP 没有让模型“提前知道”工具，而是让你在首轮用自然语言告诉模型一次，后续轮次利用对话历史避免重复发送 JSON Schema，从而省掉大量 token。**





**Token 临界点公式：**

```
MCP 的固定成本（一次性）：
  · tools/list 请求 + initialize 请求
  · 总计：~250 tokens / session

Function Calling 的持续成本（每轮）：
  · SchemaTokens × ConvTurns

临界条件：MCP 开始优于 Function Calling 当——
  SchemaTokens × ConvTurns > 250

  即：ConvTurns > 250 / SchemaTokens

代入计算：
  · N=1 个工具 → SchemaTokens=150 → T > 1.67 轮（几乎只要多轮就该用 MCP）
  · N=5 个工具 → SchemaTokens=750 → T > 0.33 轮（任何时候 MCP 都更省）
  · N=10 个工具 → SchemaTokens=1500 → T > 0.17 轮（MCP token 优势显著）
```

> **量化结论**：除了单轮对话 + 极少数工具的极端场景，MCP 在 Token 消耗上几乎总是优于 Function Calling。





**二、延迟对比模型**

```
端到端延迟分解（典型场景）：

  Function Calling 模式：
  ┌────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐
  │ LLM推理│ → │开发者代码 │ → │ 工具执行  │ → │LLM推理 │
  │ 200ms  │   │判断+调用  │   │ 50-500ms │   │ 200ms  │
  │        │   │  5-50ms  │   │          │   │        │
  └────────┘   └──────────┘   └──────────┘   └────────┘
  总计：~455-950ms

  MCP 模式 (stdio 本地)：
  ┌────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐
  │ LLM推理│ → │MCP协议层 │ → │ 工具执行  │ → │LLM推理 │
  │ 200ms  │   │ ~5-10ms  │   │ 50-500ms │   │ 200ms  │
  └────────┘   └──────────┘   └──────────┘   └────────┘
  总计：~455-710ms

  MCP 模式 (Streamable HTTP 远程)：
  ┌────────┐   ┌──────────┐   ┌──────────┐   ┌────────┐
  │ LLM推理│ → │网络+MCP  │ → │ 工具执行  │ → │LLM推理 │
  │ 200ms  │   │ 10-50ms  │   │ 50-500ms │   │ 200ms  │
  └────────┘   └──────────┘   └──────────┘   └────────┘
  总计：~460-750ms

关键发现：
  · LLM 推理时间 (200ms+) 是所有模式的最大瓶颈
  · MCP 协议开销 (5-50ms) 在端到端延迟中占比 < 10%
  · 选择 MCP 或 Function Calling 对一次工具调用的延迟影响 < 10%
  · 延迟不应该是 MCP vs Function Calling 的决策因子
```

**三、维护成本的量化估算**

```
边际成本随工具数量增长的变化：

  Function Calling 模式：
  ┌──────────────────────────────────────────────────────┐
  │ 工具数  初始开发  +  每次新增   +  跨 LLM 迁移成本    │
  │ 1-3     ~4h       ~1h/个        ~3h/model           │
  │ 4-10    ~8h       ~2h/个        ~8h/model           │
  │ 11-30   ~16h      ~3h/个        ~20h/model          │
  │ 31-50+  ~24h      ~5h/个        ~40h/model          │
  │                                                      │
  │ 边际成本曲线：每增加一个工具 ↑，跨 LLM 迁移 ↑         │
  └──────────────────────────────────────────────────────┘

  MCP 模式：
  ┌──────────────────────────────────────────────────────┐
  │ 工具数  初始开发  +  每次新增   +  跨 LLM 迁移成本    │
  │ 1-3     ~8h       ~1.5h/个      ~0.5h/model         │
  │ 4-10    ~12h      ~1.5h/个      ~1h/model           │
  │ 11-30   ~16h      ~2h/个        ~2h/model           │
  │ 31-50+  ~20h      ~2h/个        ~3h/model           │
  │                                                      │
  │ 边际成本曲线：每增加一个工具 ~恒定，跨 LLM 迁移 ~平坦  │
  └──────────────────────────────────────────────────────┘

拐点分析（两条曲线的交叉点）：
  · 工具数 > 5 → MCP 累计成本开始低于 Function Calling
  · 跨 LLM 迁移 > 1 次 → MCP 优势进一步扩大
  · 团队规模 > 5 → MCP 协作优势开始显现
```

**四、综合决策公式**

```
MCP 适用性得分 = Σ(加权因子 × 维度得分)

  维度              权重    得分标准
  ────────────────  ────    ────────────────────────────
  工具数量 (T)       30%    T≤2: 0, 3-5: 5, 6-15: 8, >15: 10
  AI 应用数量 (A)    20%    A=1: 0, 2-3: 5, >3: 10
  跨 LLM 需要 (L)    15%    No: 0, Maybe: 5, Yes: 10
  团队规模 (S)       15%    S=1: 0, 2-5: 5, >5: 10
  工具复杂度 (C)     10%    简单API: 0, 中等: 5, 高: 10
  安全要求 (R)       10%    低: 0, 中: 5, 高: 10

  总分 < 3.5: 用 Function Calling
  总分 3.5-6.5: 建议用 MCP
  总分 > 6.5: 必须用 MCP

  示例计算（5 个工具 + 1 个 AI 应用 + 不需要跨 LLM + 2 人团队 + 中等复杂 + 低安全）：
  得分 = 8×0.3 + 0×0.2 + 0×0.15 + 5×0.15 + 5×0.1 + 0×0.1
       = 2.4 + 0 + 0 + 0.75 + 0.5 + 0 = 3.65
  → 刚好进入"建议用 MCP"的区间
```

#### 5.1.2 什么时候不该用 MCP

决策不仅要看"什么时候该用"，更要看"什么时候不该用"。以下是明确的反面清单：

```
MCP 的反面清单——以下场景不应该用 MCP：

场景 1: 只有 1-2 个工具、单一 LLM、个人使用
  → 用 Function Calling。引入 MCP 的初始化/协商/生命周期开销不值得。

场景 2: 工具执行逻辑极简单（如 "1+1 等于几"）
  → 直接用 LLM 的知识或 Code Interpreter。MCP 的协议开销 > 工具价值。

场景 3: 需要硬实时响应的场景（<10ms 端到端延迟）
  → JSON-RPC 文本协议 + 网络传输无法满足此级别的延迟要求。

场景 4: 工具与 LLM 深度耦合（如特定模型的内部 API）
  → MCP 的设计哲学是模型无关。如果工具专属于某个模型，MCP 抽象层是多余的。

场景 5: 零网络环境 + 无法启动子进程
  → MCP 的最小运行单元是独立进程（Server），需要进程管理能力。

场景 6: 团队没有独立维护 MCP Server 的能力
  → MCP Server 是需运维的服务。如果团队只有前端开发者，引入 MCP 会增加运维负担。

场景 7: 试用/POC 阶段，不确定工具设计是否合理
  → 先用 Function Calling 快速验证。确定工具有价值后再按 MCP 规范重构。
```

> **判断原则**：**MCP 的价值 = N×M 集成收益 - 协议引入的固定成本**。当固定成本 > 收益时，MCP 不是正确选择。

**决策清单（Checklist）：**

| 评估维度 | 不需要 MCP（用 Function Calling） | 适合采用 MCP |
|----------|----------------------------------|-------------|
| 工具数量 | 1-2 个 | 5 个以上 |
| AI 应用数量 | 始终只用一个 | 多个 AI 应用需要共享工具 |
| 团队规模 | 个人项目 | 跨团队协作 |
| 工具复杂度 | 简单 API 调用 | 涉及流式、进度、文件操作 |
| 未来发展 | 无扩展计划 | 预期工具会持续增加 |
| 数据源多样性 | 单一数据源 | 多种数据源（数据库、文件、API） |
| LLM 迁移频率 | 永远不换 LLM 提供商 | 有多模型切换需求 |
| 安全合规要求 | 无合规需求 | 需要审计日志和数据隔离 |

### 5.2 MCP Server 设计原则

#### 原则一：单一职责（Single Responsibility）

每个 MCP Server 只负责一类能力。不要做一个 "万能 Server"。

```
❌ 不好的设计：
  my-giant-server/
    ├── weather_tool.py
    ├── database_tool.py
    ├── email_tool.py
    └── slack_tool.py

✅ 好的设计：
  weather-server/          → 只负责天气查询
  database-server/         → 只负责数据库操作
  communication-server/    → 只负责消息发送（email + slack）
```

**为什么？**
- Server 崩溃时影响范围可控
- 安全权限可以按 Server 粒度配置（数据库工具给只读权限，天气工具给所有人）
- 不同 Server 可以独立版本管理和部署

#### 原则二：最小权限（Least Privilege）

MCP Server 只暴露完成任务所需的最小权限集。

```python
# 不好的做法：暴露全表操作
db_tools = ["select_all", "insert_any", "delete_any", "drop_table"]

# 好的做法：只暴露需要的操作
db_tools = ["search_products", "get_product_detail", "check_inventory"]
```

#### 原则三：结构化输出（Structured Output）

工具返回结果应尽量结构化（JSON），便于 LLM 理解和进一步处理。

```python
# ❌ 不好的返回：纯文本
"产品 A: 价格 99 元，库存 50 件\n产品 B: 价格 199 元，库存 30 件"

# ✅ 好的返回：结构化 JSON
{
    "products": [
        {"name": "产品 A", "price": 99, "stock": 50},
        {"name": "产品 B", "price": 199, "stock": 30}
    ],
    "total_count": 2
}
```

#### 原则四：工具描述即文档（Self-Describing Tools）

工具的 `description` 和参数的 `description` 要写得足够详细，因为 LLM 是**靠这些描述来理解如何使用的**。

```python
# ❌ 模糊的描述
Tool(
    name="search",
    description="搜索",
    inputSchema={
        "properties": {
            "q": {"type": "string", "description": "查询"}
        }
    }
)

# ✅ 清晰的描述
Tool(
    name="search_customers",
    description="在客户数据库中搜索客户信息。支持按姓名、手机号或公司名进行模糊匹配。返回匹配的客户列表，最多返回 20 条记录。",
    inputSchema={
        "properties": {
            "query": {
                "type": "string",
                "description": "搜索关键词，可以是客户姓名、手机号后四位或公司名称。最少 2 个字符。"
            },
            "search_by": {
                "type": "string",
                "enum": ["name", "phone", "company"],
                "description": "指定搜索维度：name=按姓名搜索，phone=按手机号搜索，company=按公司名搜索。默认为 name。"
            }
        },
        "required": ["query"]
    }
)
```

### 5.3 安全最佳实践

#### 5.3.1 Host 端安全配置

```json
{
    "mcpServers": {
        "filesystem": {
            "command": "npx",
            "args": [
                "-y",
                "@modelcontextprotocol/server-filesystem",
                "/home/user/allowed/path"
            ]
        }
    }
}
```

- **始终限制文件系统访问范围**：不要让 MCP Server 访问整个文件系统
- **使用网络白名单**：如果 Server 需要网络访问，明确指定允许的域名/IP
- **环境变量隔离**：敏感凭证使用环境变量注入，不写在配置文件中

#### 5.3.2 Server 端实现安全

```python
# 在工具函数中始终做权限校验
async def execute_query(sql: str) -> dict:
    # 1. 只允许 SELECT 语句
    if not sql.strip().upper().startswith("SELECT"):
        raise ValueError("只允许 SELECT 查询")

    # 2. 禁止危险关键字
    dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "UPDATE", "INSERT"]
    sql_upper = sql.upper()
    for keyword in dangerous_keywords:
        if keyword in sql_upper:
            raise ValueError(f"检测到危险关键字: {keyword}")

    # 3. 限制结果集大小
    if "LIMIT" not in sql_upper:
        sql = f"{sql.strip()} LIMIT 1000"

    return await db.execute(sql)
```

#### 5.3.3 输入校验

```python
from pydantic import BaseModel, Field, validator
import re

class WeatherRequest(BaseModel):
    city: str = Field(..., description="城市名称", min_length=1, max_length=50)

    @validator("city")
    def validate_city(cls, v):
        # 只允许中文、英文、空格和连字符
        if not re.match(r'^[\u4e00-\u9fa5a-zA-Z\s\-]+$', v):
            raise ValueError(f"城市名称包含非法字符: {v}")
        return v.strip()
```

### 5.4 性能优化建议

| 优化方向 | 具体措施 | 收益 |
|----------|----------|------|
| **工具列表缓存** | tools/list 的结果在 Server 启动后不变，直接缓存 | 减少 1 次 RPC |
| **连接池复用** | Client 与 Server 之间的连接长期保持，避免频繁重建 | 减少连接开销 |
| **工具粒度设计** | 一个工具做一件事，比一个大而全的工具更省 token | 降低 token 消耗 |
| **结果截断** | 对于大结果，返回摘要 + 分页而非全量数据 | 避免 token 溢出 |
| **超时设置** | 为工具执行设置合理超时，避免 LLM 长时间等待 | 提升用户体验 |

---

## 六、常见面试题

### 基础概念

**Q1: MCP 是什么？它的全称是什么？由谁在什么时候提出？**

<details>
<summary>参考答案</summary>

MCP（Model Context Protocol，模型上下文协议）是由 Anthropic 于 2024 年 11 月 25 日正式开源的一个开放标准协议。它标准化了大语言模型（LLM）与外部工具、数据源和服务之间的通信规则。

核心理解：MCP 想做 AI 工具调用世界的 "USB-C"——一套通用的连接标准，让不同的 LLM 和不同的工具可以用统一的方式对接。

</details>

---

**Q2: MCP 的三层架构是什么？每层的职责是什么？**

<details>
<summary>参考答案</summary>

1. **Host（宿主层）**：管理 MCP Client 的生命周期、权限控制、安全沙箱。例如 Claude Desktop、VS Code。
2. **Client（客户端层）**：与 Server 一对一通信，负责协议消息路由、订阅管理、通知分发。每个 Client 连接一个 Server。
3. **Server（服务器层）**：暴露 Tools、Resources、Prompts 三种原语，提供具体的能力实现。

</details>

---

**Q3: MCP 的三个核心原语分别是什么？各自解决什么问题？**

<details>
<summary>参考答案</summary>

| 原语 | 解决什么问题 | 谁控制 |
|------|-------------|--------|
| **Tools** | 让 LLM 能执行操作（查天气、发邮件、操作数据库） | 模型控制（Model-controlled） |
| **Resources** | 让 LLM 能读取上下文数据（文件、API 响应、数据库记录） | 应用控制（Application-controlled） |
| **Prompts** | 提供可复用的提示词模板（代码审查、翻译等） | 用户控制（User-controlled） |

</details>

---

### 架构理解

**Q4: MCP 和 Function Calling 的本质区别是什么？什么时候该用哪个？**

<details>
<summary>参考答案</summary>

**本质区别：**
- **Function Calling** 是模型层面的能力——"模型会用工具"
- **MCP** 是系统层面的协议——"工具怎么接入和发现"

MCP 实际上是构建在 Function Calling 之上的系统级协议。

**选型建议：**
- 1-2 个简单工具 → Function Calling 就够了
- 5+ 个工具、多团队协作 → 建议用 MCP
- 需要让工具被多个 AI 应用共享 → 必须用 MCP

</details>

---

**Q5: 请解释 MCP 如何解决 N×M 集成困境？**

<details>
<summary>参考答案</summary>

传统模式下，N 个 AI 应用对接 M 个工具需要 N×M 套集成代码。比如 10 个 AI 应用 × 50 个工具 = 500 套集成代码。

MCP 通过引入统一协议层，将复杂度降为 N+M：10 个 AI 适配 + 50 个工具实现 = 60 套。AI 应用只需要适配 MCP 协议一次，工具只需要按 MCP 协议实现一次，两者就可以自由组合。

</details>

---

**Q6: MCP 基于什么底层协议？为什么选择它？**

<details>
<summary>参考答案</summary>

MCP 基于 **JSON-RPC 2.0** 协议。

选择理由：
1. **简单性**：比 REST 更简单，无需关注 HTTP method 语义
2. **双向通信**：支持 Request（需要响应）和 Notification（单向通知）两种模式
3. **传输无关**：可运行在 stdio、HTTP、WebSocket 等任何传输层上
4. **生态验证**：被 LSP（Language Server Protocol）广泛验证，成熟可靠

MCP 的设计深受 LSP 的影响——LSP 定义了编辑器与语言服务器的协议，MCP 定义了 AI 应用与工具服务器的协议，两者是同构的。

</details>

---

### 深入思考

**Q7: MCP 是"有状态"还是"无状态"协议？为什么这样设计？**

无状态：每个请求都是独立的，服务器不保存任何关于客户端的历史状态。

**例子**：HTTP 协议（基础版本）。

- 你访问网页 `A`，服务器返回内容。
- 接着访问网页 `B`，服务器**不知道**你刚看过 `A`，除非你通过 Cookie、Token 等方式在请求里主动带上。
- 每个请求都“自包含”。

有状态：服务器会记住客户端的上下文（如登录状态、会话 ID、对话历史、工具列表等），后续请求可以基于之前的状态自动处理。

**例子**：WebSocket、TCP 连接、数据库连接、MCP 中的某些实现。

- MCP 协议本身**可以**有状态：客户端和 MCP Server 建立连接后，Server 可以记住客户端之前注册过哪些工具、资源订阅等。
- 但**大模型 API 仍然是无状态的**，所以 MCP 的节省 token 并非依靠模型 API 有状态，而是依靠**客户端自己的上下文管理**（即对话历史中保留 system 消息）。

<details>
<summary>参考答案</summary>

MCP 是**无状态协议**。每个请求都自包含，携带协议版本、客户端身份和能力声明。

**这样设计的原因：**
1. **简化实现**：Server 不需要维护会话状态，降低实现复杂度
2. **容错性**：连接断开后重连不需要恢复状态
3. **水平扩展**：无状态 Server 可以任意水平扩展
4. **与 HTTP 一致**：符合 Web 架构的 REST 风格

但需要注意的是，虽然协议本身是无状态的，Server 实现可以自行维护业务状态（如数据库连接池、缓存等）。

</details>

---

**Q8: 一个 MCP Server 在 tools/call 时执行失败了，应该如何返回错误？为什么不用 JSON-RPC 的 error 对象？**

<details>
<summary>参考答案</summary>

应该返回正常的 JSON-RPC 响应，在 result 中设置 `isError: true` 和错误描述。

```json
{
    "jsonrpc": "2.0",
    "id": 42,
    "result": {
        "content": [{"type": "text", "text": "错误: 未找到该城市"}],
        "isError": true
    }
}
```

**为什么不用 JSON-RPC 的 error 对象？**

因为 "工具执行失败"（如查不到数据）和 "协议通信失败"（如 JSON 格式错误）是不同层次的事情。工具执行失败是业务层的正常情况，LLM 需要看到这个错误信息来决定下一步怎么做（换一个城市名再试、告诉用户找不到等）。而 JSON-RPC 的 error 对象是表示通信本身出了问题（如参数格式不对、连接断开），此时 LLM 不应该尝试处理错误。

</details>

---

**Q9: 如果你要设计一个企业级的 MCP 工具注册中心，你会怎么设计？**

<details>
<summary>参考答案</summary>

核心设计要点：

1. **服务发现**：需要一个注册中心（类似服务网格中的 Service Registry），MCP Server 启动时注册，Client 通过注册中心找到可用的 Server
2. **健康检查**：定期探测 Server 健康状态，自动摘除不可用节点
3. **版本管理**：工具定义支持版本化，Client 可以声明需要的工具版本
4. **权限控制**：基于 RBAC，不同团队/用户对工具的可见性和可使用性不同
5. **监控告警**：工具调用量、延迟、错误率等指标统一上报，支持告警
6. **工具市场**：企业内部的工具目录，支持搜索、预览、申请使用

这是一种典型的微服务网关架构，在 MCP 协议之上叠加服务治理能力。

</details>

---

### 扩展协议对比

**Q10: MCP 为什么选择 JSON-RPC 而不是 gRPC？**

<details>
<summary>参考答案</summary>

四个核心理由：

1. **性能瓶颈不在序列化**：AI 工具调用的延迟主要由 LLM 推理（200ms+）和工具执行（50-5000ms）主导，JSON 序列化开销（<1ms）在端到端延迟中占比 < 0.1%。优化序列化对 MCP 场景几乎没有实际收益。

2. **描述自包含性优先于类型安全**：工具 Schema 中的 `description` 字段是 LLM 理解工具用途的核心依据。JSON 原生支持运行时可见的描述，Protobuf 注释编译后丢失，LLM 无法读取。

3. **传输无关性 > 协议强绑定**：gRPC 重度依赖 HTTP/2，无法支持 stdio 本地进程通信、浏览器原生连接和 FaaS 部署等 MCP 核心场景。MCP 需要一套协议同时运行在终端进程、HTTP 服务和云函数上。

4. **LSP 生态验证**：LSP 在数百万开发者 + 每天数十亿条消息的规模上验证了 JSON-RPC 在工具通信场景中的可行性。

**加分回答**：能主动补充"什么时候 gRPC 可能更好"——高频实时数据流（>1000 QPS）或超低延迟硬实时场景（<10ms e2e），但 MCP 的设计目标本不包含这些场景。

</details>

---

**Q11: MCP 的诞生与 LSP 和 ChatGPT Plugins 有什么关联？**

<details>
<summary>参考答案</summary>

MCP 的诞生是三条演进脉络的交汇，而不是 Anthropic 的灵光一闪：

1. **LSP 的成功（技术基础）**：LSP 验证了"JSON-RPC + N×M→N+M + 能力协商"这套范式在工具通信场景中的可行性。MCP 继承了大量 LSP 基因——JSON-RPC 2.0、传输无关设计、生命周期模型、能力协商机制。本质上是把 LSP 的 `textDocument/completion` 替换为 `tools/call`。

2. **ChatGPT Plugins 的失败（反面教训）**：中心化的 AI 工具生态被证明不可行——审核瓶颈、厂商绑定、创新抑制、社区缺乏长期投入动力。MCP 的去中心化设计（开源协议、无中心审核、Host 自主决定信任链）是对此的直接回应。

3. **开源模型的崛起（市场需求）**：Llama 3、Mistral、Qwen 2、DeepSeek 等开源模型的爆发使企业进入多模型格局。每个模型的工具调用格式不同，产生了对"模型无关"工具接入层的刚性需求。

**金句**："MCP 是 LSP 范式在 AI 时代的自然延伸，也是对 ChatGPT Plugins 失败模式的必然反思。"

</details>

---

**Q12: MCP 选择牺牲了什么？它的设计边界在哪里？**

<details>
<summary>参考答案</summary>

三个核心 trade-off：

1. **简单性 vs 灵活性**：只定义 3+1 个原语（Tools/Resources/Prompts/Sampling），牺牲了对复杂编排、UI 交互、Agent 状态管理等场景的协议层支持，换取了极低的学习成本和实现门槛。编排和工作流留给 LangGraph 等上层框架。

2. **标准化 vs 性能**：选择 JSON 文本协议，牺牲了序列化效率（Protobuf 快 3-10x），换取了人类可读性、可调试性、浏览器兼容性和零学习曲线。在 99% 的场景中，工具执行时间远大于序列化开销。

3. **安全性 vs 便利性**：Server 看不到完整对话历史和其他 Server 的数据，牺牲了上下文感知和多 Server 协同的便利，换取了跨 Server 数据隔离、合规审计简化和防信息泄露的安全架构。

**MCP 的边界（力不能及的场景）**：硬实时（<10ms e2e）、高吞吐二进制流（>1000 QPS 大文件内嵌）、跨 Agent 协作编排（这是 A2A 的领域）。

</details>

---

### 量化决策

**Q13: 如何量化判断一个项目是否应该采用 MCP？**

<details>
<summary>参考答案</summary>

从四个可量化维度综合评估：

1. **Token 节省临界点**：SchemaTokens × ConvTurns > 250（MCP 固定成本）。5 个工具 × 3 轮对话即可节省 2000+ tokens。工具越多、对话轮次越多，MCP 的 Token 优势越显著。极限场景（50 个工具、长对话）每年可节省百万美元级别。

2. **延迟影响**：MCP 协议开销在端到端延迟中占比 < 10%（LLM 推理和工具执行是绝对主导因素），不应作为决策因子。

3. **维护成本拐点**：工具数 > 5 时，MCP 累计维护成本开始低于 Function Calling；跨 LLM 迁移次数 > 1 时优势进一步扩大。

4. **加权评分决策公式**：工具数量（30%）+ AI 应用数（20%）+ 跨 LLM 需求（15%）+ 团队规模（15%）+ 工具复杂度（10%）+ 安全要求（10%）。总分 > 3.5 建议用 MCP，> 6.5 必须用 MCP。

**核心结论**：MCP 不是银弹。判断标准是 MCP 价值 = N×M 集成收益 - 协议引入的固定成本。固定成本 > 收益时（单工具、单 LLM、个人项目），Function Calling 更合适。

</details>

---

**Q14: Streamable HTTP 和 WebSocket 在 MCP 场景中如何选择？**

<details>
<summary>参考答案</summary>

Streamable HTTP 是 2025 年新增的默认传输方式，在三个关键维度上优于 WebSocket：

1. **企业环境兼容**：WebSocket 的 HTTP Upgrade 在企业代理/防火墙中频繁被拒。Streamable HTTP 的标准 HTTP POST/GET 兼容任何 HTTP 基础设施，天然穿透企业网络边界。

2. **弹性伸缩友好**：WebSocket 连接绑定到特定 Pod，需要 sticky session 和复杂的连接迁移。Streamable HTTP 的每个请求独立，可被任意路由到任何 Pod，对 K8s HPA 完全透明。

3. **Serverless 亲和**：WebSocket 长连接与 FaaS"用完即走"模型根本冲突。Streamable HTTP Stateless 模式天然适配 Lambda / 云函数 / Cloud Run。

**什么时候 WebSocket 更好？** 需要 Server 主动向 Client 高频推送（如每秒多次推送）的场景。但 MCP 的 Resource Subscription 场景通常是分钟级的变更通知，SSE 流（Streamable HTTP Stateful 模式提供）已足够覆盖。

</details>

---

## 附录

### 核心术语速查表

| 术语 | 英文 | 简要说明 |
|------|------|----------|
| MCP | Model Context Protocol | 模型上下文协议 |
| Host | Host | 管理客户端连接和权限的宿主应用 |
| Client | Client | 与 Server 一对一通信的协议路由层 |
| Server | Server | 暴露能力原语的服务端 |
| Tool | Tool | 可执行的函数，LLM 可调用 |
| Resource | Resource | 可读取的数据源，支持订阅变更 |
| Prompt | Prompt | 预定义的提示词模板 |
| JSON-RPC | JSON-RPC | MCP 的底层通信协议 |
| Capability | Capability | 客户端/服务端的能力声明 |
| Primitive | Primitive | MCP 的基础抽象单元（Tool/Resource/Prompt） |
| SSE | Server-Sent Events | 服务器推送事件的 HTTP 传输方式 |
| LSP | Language Server Protocol | 语言服务器协议，MCP 的架构参考 |

### 推荐阅读

- [MCP 官方规范](https://spec.modelcontextprotocol.io/)
- [MCP GitHub 仓库](https://github.com/modelcontextprotocol)
- [Anthropic MCP 介绍博客](https://www.anthropic.com/news/model-context-protocol)
- [LSP 官方规范](https://microsoft.github.io/language-server-protocol/) —— 理解 MCP 的设计基因

### 学员自查清单

学完本模块后，你应能独立回答以下问题：

```
□ MCP 是什么？用一句话向非技术人员解释
□ MCP 的三层架构（Host/Client/Server）的职责划分
□ 四种核心原语（Tools/Resources/Prompts/Sampling）各自解决什么问题
□ N×M 集成困境是什么？MCP 如何将其降为 N+M？
□ MCP 和 Function Calling 的本质区别和选型建议
□ MCP 为何选择 JSON-RPC 而非 gRPC？给出至少三个理由
□ JSON-RPC 的性能瓶颈在什么场景下才会暴露？MCP 如何规避？
□ WebSocket 和 Streamable HTTP 的本质区别和选型建议
□ GraphQL Introspection 和 MCP tools/list 在设计哲学上的核心差异
□ LSP 的哪些基因被 MCP 继承？LSP 的成功如何影响了 MCP 的设计？
□ ChatGPT Plugins 失败的三个核心原因？MCP 如何避免重蹈覆辙？
□ 开源模型的崛起在什么意义上推动了 MCP 的诞生？
□ MCP 的三个核心 design trade-off 分别是什么？
□ 在什么情况下不应该使用 MCP？（至少说出 4 种场景）
□ 如何计算 MCP 比 Function Calling 节省 Token 的临界点？
□ 端到端延迟中，MCP 协议开销占比通常是多少？为什么不需要过度优化？
□ 工具数量增长时，MCP 和 Function Calling 的边际维护成本曲线有何不同？
□ 能用自己的话讲清"为什么 MCP 在 2024 年底出现"的完整叙事
```
