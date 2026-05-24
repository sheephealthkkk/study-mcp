# 第一模块：MCP 基础认知与核心概念

> **学习周期**：2-3 天  
> **学习目标**：理解 MCP 是什么、为什么需要它、它解决什么层次的问题

---

## 目录

1. [一、是什么——MCP 的定义与定位](#一是什么mcp-的定义与定位)
2. [二、为什么需要——MCP 解决的核心痛点](#二为什么需要mcp-解决的核心痛点)
3. [三、如何实现——MCP 的核心架构](#三如何实现mcp-的核心架构)
4. [四、底层原理——协议细节与消息流转](#四底层原理协议细节与消息流转)
5. [五、企业级最佳实践](#五企业级最佳实践)
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
```

**决策清单（Checklist）：**

| 评估维度 | 不需要 MCP（用 Function Calling） | 适合采用 MCP |
|----------|----------------------------------|-------------|
| 工具数量 | 1-2 个 | 5 个以上 |
| AI 应用数量 | 始终只用一个 | 多个 AI 应用需要共享工具 |
| 团队规模 | 个人项目 | 跨团队协作 |
| 工具复杂度 | 简单 API 调用 | 涉及流式、进度、文件操作 |
| 未来发展 | 无扩展计划 | 预期工具会持续增加 |
| 数据源多样性 | 单一数据源 | 多种数据源（数据库、文件、API） |

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
