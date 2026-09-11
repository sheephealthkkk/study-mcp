# 第三模块：MCP Server/Client 开发入门

---

## 目录

1. [一、是什么——MCP SDK 体系概览](#一是什么mcp-sdk-体系概览)
   - [1.1 SDK 全景图（含 Go SDK 实战）](#11-sdk-全景图)
   - [1.4 跨语言 SDK 行为差异与迁移注意事项](#14-跨语言-sdk-行为差异与迁移注意事项)
   
2. [二、为什么需要——SDK 解决了哪些开发痛点](#二为什么需要sdk-解决了哪些开发痛点)

3. [三、如何实现——从零构建 MCP Server 和 Client](#三如何实现从零构建-mcp-server-和-client)
   - [3.3.5 全局错误处理中间件](#335-全局错误处理中间件)
   - [3.5.2 构建健壮的 MCP Client](#352-构建健壮的-mcp-client)
   - [3.7.5 使用 Mock Transport 进行轻量级测试](#375-使用-mock-transport-进行轻量级测试)
   
4. [四、底层原理——SDK 内部机制剖析](#四底层原理sdk-内部机制剖析)

5. [五、企业级最佳实践](#五企业级最佳实践)

   

---

## 一、是什么——MCP SDK 体系概览

### 1.1 SDK 全景图

MCP 官方提供了 Python 和 TypeScript/JavaScript 两种语言的 SDK，社区还贡献了 Kotlin、Go、C#、Rust 等语言的实现。

```
MCP SDK 生态系统

┌──────────────────────────────────────────────────────────┐
│                    官方 SDK（Anthropic 维护）              │
│                                                          │
│  ┌─────────────────────────┐  ┌─────────────────────────┐│
│  │     Python SDK           │  │   TypeScript SDK        ││
│  │  pip install mcp         │  │  npm install            ││
│  │  最新稳定版: 1.3.0       │  │  @modelcontextprotocol  ││
│  │                          │  │  /sdk                   ││
│  │  核心模块:                │  │  最新稳定版: 1.0.4      ││
│  │  ├── mcp.server          │  │                         ││
│  │  │   ├── fastmcp         │  │  核心模块:               ││
│  │  │   ├── lowlevel        │  │  ├── server             ││
│  │  │   └── models          │  │  ├── client             ││
│  │  ├── mcp.client          │  │  └── shared             ││
│  │  └── mcp.types           │  │                         ││
│  └─────────────────────────┘  └─────────────────────────┘│
│                                                          │
├──────────────────────────────────────────────────────────┤
│                  社区 SDK（精选）                          │
│                                                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │ Kotlin   │ │   Go     │ │   C#     │ │  Rust    │   │
│  │ (model-  │ │ (mark3   │ │ (model-  │ │ (model-  │   │
│  │ context- │ │ labs/mcp-│ │ context- │ │ context- │   │
│  │ protocol │ │ go)      │ │ protocol │ │ protocol │   │
│  │ /kotlin- │ │ ★ 1k+   │ │ /csharp- │ │ /rust-sdk│   │
│  │ sdk)     │ │ stars    │ │ sdk)     │ │ )        │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │
└──────────────────────────────────────────────────────────┘
```

Go SDK 值得重点关注——大量企业后端使用 Go 技术栈，面试中可能被问及。以下是 `mark3labs/mcp-go` 的最小可运行 Server 示例：

```go
// main.go —— Go MCP Server 最小可运行示例
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
        "go-weather-server", "1.0.0",
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

**面试追问**："公司后端是 Go 技术栈，你会如何用 Go SDK 构建 MCP Server？"

**应对要点**：
- 首选 `mark3labs/mcp-go`（社区最活跃），编译为单一二进制文件，Docker 镜像 < 10MB
- 与 Python 的关键差异：Go 需**手写 JSON Schema**（通过 `mcp.WithString()` 等 builder），没有 Python FastMCP 的类型自动推导能力。工具数量 > 10 时建议编写代码生成工具从 Go struct tag 生成 Tool 定义
- **并发优势**：goroutine 模型天然适合 MCP 并发调用，handler 中检查 `ctx.Done()` 以支持 MCP Cancelled 通知
- **并发安全**：如多个 tools/call 并发访问共享 map，需加 `sync.Mutex`

**Go vs Python 选型速查**：

| 维度 | Python (FastMCP) | Go (mcp-go) |
|------|-----------------|-------------|
| 开发效率 | 高（类型推导 + 装饰器） | 中（手写 Schema） |
| 部署体积 | ~100MB (Docker) | <10MB (scratch 镜像) |
| 并发性能 | 中（asyncio） | 高（goroutine） |
| 适合规模 | 工具数 < 20 | 工具数不限 |

### 1.2 FastMCP vs Low-Level API

Python SDK 提供了两层 API：

| 特性 | FastMCP（高层 API） | Low-Level API |
|------|---------------------|---------------|
| **设计理念** | 装饰器驱动，约定优于配置 | 手动注册，完全控制 |
| **学习曲线** | 低，5 分钟上手 | 中，需要理解协议细节 |
| **类型安全** | 依赖 Python 类型注解 | 手动编写 JSON Schema |
| **适用场景** | 快速原型、简单工具 | 复杂需求、高度定制 |
| **灵活性** | 满足 90% 的需求 | 100% 的协议控制力 |

> **核心坑点**：在 MCP Python SDK 1.2.0 之前，Quickstart 文档使用 `server.run()` 方式启动 Server。**从 1.2.0 版本开始，此写法已被废弃**，正确做法是使用 `FastMCP` 类或 Low-Level API 的 `stdio_server()` 上下文管理器。如果你在网上看到 `mcp.server.run()` 的示例代码，那是过时的，不要使用。

### 1.3 版本对照表

| Python SDK | TypeScript SDK | 协议版本 | 关键变化 |
|------------|---------------|----------|----------|
| ≤ 1.1.x | ≤ 0.x | 2024-11-05 | 初始版本 |
| 1.2.0 | — | 2024-11-05 | 废弃 `server.run()`，引入 `FastMCP` |
| 1.3.0 | 1.0.4 | 2025-03-26 | 支持 Streamable HTTP、Elicitation、Progressive Capabilities |

### 1.4 跨语言 SDK 行为差异与迁移注意事项

#### 1.4.1 `server.run()` 废弃后的完整迁移 checklist

MCP Python SDK 1.2.0 起废弃了老式的 `server.run()`，必须迁移到 `FastMCP`：

```
□ Step 1: 检查 SDK 版本
    pip show mcp | grep Version
    如果 < 1.2.0 → pip install mcp>=1.3.0

□ Step 2: 替换 Server 创建
    [旧] from mcp.server import Server
         server = Server("my-server")
         @server.list_tools() ...; @server.call_tool() ...
         server.run()

    [新] from mcp.server.fastmcp import FastMCP
         mcp = FastMCP("my-server")
         @mcp.tool() ...    # 一个装饰器替代 list_tools + call_tool
         mcp.run(transport="stdio")

□ Step 3: 替换 Resource 注册
    [旧] @server.list_resources() + @server.read_resource()
    [新] @mcp.resource("uri://path")   # 一个装饰器同时处理 list + read

□ Step 4: 明确传输方式
    [旧] server.run() → 默认 stdio
    [新] mcp.run(transport="stdio")    # 显式指定，防止误用

□ Step 5: 能力声明自动化
    [旧] 手动在 Server 构造函数中声明 capabilities
    [新] FastMCP 从装饰器自动推断——注册了 @mcp.tool() 即自动声明 tools 能力

□ Step 6: 验证
    python server.py
    npx @anthropic-ai/mcp-inspector python server.py
```

#### 1.4.2 Python SDK vs TypeScript SDK 关键行为差异

| 行为 | Python SDK (FastMCP) | TypeScript SDK | 面试要点 |
|------|---------------------|---------------|----------|
| **工具定义** | 装饰器 + 类型注解**自动推导** JSON Schema | `server.registerTool()` + **手写 Zod** Schema | Python 开发效率高 2-3x |
| **错误返回** | `result.isError = True` | 同，但 **TS 类型更严格**（编译期检查） | Python 依赖运行时校验 |
| **Resource 返回** | 返回 `str` → SDK **自动包装**为协议格式 | 需**显式返回** `{contents: [...]}` | TS 更接近协议原始结构 |
| **Transport 切换** | `mcp.run(transport="sse")` 一行切换 | 需手动创建 `SSEServerTransport` 实例 | Python 抽象层级更高 |
| **并发模型** | `asyncio` 协程 | Node.js Event Loop | 性能模型不同但都能满足需求 |
| **部署体积** | ~100MB（含依赖） | ~50MB（node_modules） | Go 编译单二进制 < 10MB |

**面试追问**："Python 和 TypeScript SDK 你更推荐哪个？"

**参考回答**：取决于团队背景和场景。数据/AI 团队推荐 Python FastMCP（类型推导 + 少写代码），前端/全栈团队推荐 TypeScript（编译期安全 + 浏览器 Client）。对于工具数 > 50 的大项目，TS 的类型安全价值更大。混合方案（Python Server + TS Client）也很常见。

#### 1.4.3 Go SDK 的定位

Go 社区 SDK 适合以下场景：公司后端是 Go + 需要高并发 + 希望单二进制部署 + 微服务架构。相对于 Python 和 TypeScript，Go SDK 的劣势是工具定义的样板代码更多（需手写 JSON Schema），优势是部署简单和并发性能更好。

---

## 二、为什么需要——SDK 解决了哪些开发痛点

### 2.1 如果没有 SDK——裸写 JSON-RPC 的痛苦

```python
# 如果没有 SDK，你需要手写这些：
import json
import sys

def handle_request(request: dict) -> dict:
    """手动处理 JSON-RPC 请求 —— 仅展示核心痛苦"""
    method = request.get("method")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {},
                    "resources": {"subscribe": True},
                    "prompts": {}
                },
                "serverInfo": {
                    "name": "my-server",
                    "version": "1.0.0"
                }
            }
        }
    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": request["id"],
            "result": {
                "tools": [
                    {
                        "name": "get_weather",
                        "description": "获取天气",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "city": {"type": "string", "description": "城市名"}
                            },
                            "required": ["city"]
                        }
                    }
                ]
            }
        }
    elif method == "tools/call":
        tool_name = request["params"]["name"]
        args = request["params"]["arguments"]
        # 需要手动判断工具名、参数校验、错误处理、序列化...
        # ...

    # ... 还有 initialize、initialized、shutdown、ping、
    #     resources/list、resources/read、resources/subscribe、
    #     prompts/list、prompts/get、notifications/* ...
    #     每一个都需要手动编写消息处理逻辑
```

**痛点的量化：**

| 维度 | 裸写协议 | 使用 SDK |
|------|----------|----------|
| 代码量 | ~500+ 行基础设施 | ~5 行装饰器 |
| 需要理解的概念 | JSON-RPC 全部规范、协议生命周期、能力协商、错误码 | FastMCP 装饰器语义 |
| 出错概率 | 高（手写 JSON Schema 容易拼写错误） | 低（类型注解自动生成 Schema） |
| 升级成本 | 需要手动跟踪协议变更 | SDK 内部消化协议变更 |

### 2.2 SDK 的核心价值

```
┌─────────────────────────────────────────────────────┐
│              SDK 帮你处理的事情                        │
│                                                     │
│  ✅ JSON-RPC 消息解析和序列化                         │
│  ✅ 协议生命周期管理（initialize → 运行 → shutdown）   │
│  ✅ 能力声明和能力协商                                │
│  ✅ 传输层抽象（stdio / SSE / Streamable HTTP 切换）  │
│  ✅ 自动从类型注解生成 JSON Schema                    │
│  ✅ 参数校验和错误处理                                │
│  ✅ 进度通知和取消机制                                │
│  ✅ 资源订阅和变更通知                                │
│                                                     │
│  🎯 你只需要关注：编写工具函数和业务逻辑               │
└─────────────────────────────────────────────────────┘
```

---

## 三、如何实现——从零构建 MCP Server 和 Client

### 3.1 开发环境搭建

#### Python 环境

```bash
# 1. 创建虚拟环境（强烈推荐）
python -m venv mcp-env
source mcp-env/bin/activate  # Linux/Mac
# mcp-env\Scripts\activate   # Windows

# 2. 安装 MCP SDK
pip install mcp==1.3.0

# 3. 验证安装
python -c "from mcp.server.fastmcp import FastMCP; print('安装成功')"

# 4. （可选）安装开发辅助工具
pip install pydantic httpx uvicorn  # 参数校验 + HTTP 客户端 + Web Server
```

#### TypeScript 环境

```bash
# 1. 初始化项目
mkdir my-mcp-server && cd my-mcp-server
npm init -y

# 2. 安装 SDK
npm install @modelcontextprotocol/sdk@1.0.4

# 3. （可选）安装 TypeScript 和辅助库
npm install -D typescript @types/node
npm install zod  # 参数校验（推荐）
```

#### 开发工具配置

```json
// .vscode/settings.json —— 推荐配置
{
    "python.analysis.typeCheckingMode": "basic",
    "python.defaultInterpreterPath": "${workspaceFolder}/mcp-env/bin/python",
    "[python]": {
        "editor.formatOnSave": true,
        "editor.defaultFormatter": "ms-python.black-formatter"
    }
}
```

### 3.2 第一个 MCP Server（Python FastMCP）

#### 最小可运行 Server

```python
# server.py
from mcp.server.fastmcp import FastMCP

# 创建 FastMCP 实例 —— 服务名用于日志和标识
mcp = FastMCP("My First MCP Server")

@mcp.tool()
def hello(name: str) -> str:
    """向指定的人打招呼"""
    return f"你好，{name}！欢迎来到 MCP 的世界。"

if __name__ == "__main__":
    # 使用 stdio 传输启动 Server
    # Client 会通过标准输入输出与这个 Server 通信
    mcp.run(transport="stdio")
```

**验证 Server 能否启动：**

```bash
python server.py
# Server 启动后会等待 stdin 输入 JSON-RPC 消息
# 按 Ctrl+C 退出
```

#### 使用 MCP Inspector 测试

```bash
# 启动 Inspector——它会帮你启动 Server 并提供一个 Web UI
npx @anthropic-ai/mcp-inspector python server.py

# 浏览器会自动打开 http://localhost:5173
# 在 UI 中你可以：
#   1. 查看 Server 声明的能力（Tools、Resources、Prompts）
#   2. 以交互方式调用工具
#   3. 查看原始 JSON-RPC 消息
```

#### 在 Claude Desktop 中注册

```json
// claude_desktop_config.json
// Windows: %APPDATA%\Claude\claude_desktop_config.json
// Mac: ~/Library/Application Support/Claude/claude_desktop_config.json
{
    "mcpServers": {
        "my-first-server": {
            "command": "python",
            "args": ["C:\\Users\\bkjysheep\\Desktop\\mcp\\study-mcp\\server.py"],
            "transport": "stdio"
        }
    }
}
```

注册后重启 Claude Desktop，在对话中就可以使用你定义的 `hello` 工具了。

### 3.3 Tool 的定义与最佳实践

#### 3.3.1 基础工具定义

```python
from mcp.server.fastmcp import FastMCP
from typing import Literal

mcp = FastMCP("Tool Demo Server")

# ---- 示例 1：简单工具 ----
@mcp.tool()
def add(a: int, b: int) -> int:
    """计算两个整数的和"""
    return a + b


# ---- 示例 2：带枚举参数的工具 ----
@mcp.tool()
def convert_temperature(value: float, unit: Literal["C", "F"]) -> str:
    """在摄氏度和华氏度之间转换温度

    如果是 C，表示从摄氏度转为华氏度
    如果是 F，表示从华氏度转为摄氏度
    """
    if unit == "C":
        result = value * 9 / 5 + 32
        return f"{value}°C = {result:.1f}°F"
    else:
        result = (value - 32) * 5 / 9
        return f"{value}°F = {result:.1f}°C"


# ---- 示例 3：结构化返回 ----
@mcp.tool()
def search_products(keyword: str, max_results: int = 10) -> dict:
    """搜索产品数据库，返回匹配的产品列表

    Args:
        keyword: 搜索关键词，支持产品名称和描述的模糊匹配
        max_results: 最大返回条数，默认 10，上限 50
    """
    # 实际场景中，这里会查询数据库
    products = [
        {"id": 1, "name": "MCP 开发指南", "price": 59.9, "stock": 100},
        {"id": 2, "name": "AI 应用实战", "price": 79.9, "stock": 50},
    ]
    return {
        "keyword": keyword,
        "total": len(products),
        "products": products
    }
```

#### 3.3.2 工具描述是所有 API 文档

这是一个**必须牢记的核心事实**：

> **LLM 通过 `description`（docstring + 参数注解）来理解工具"何时调用"和"如何调用"。你的 docstring 就是工具的 API 文档——LLM 是这个文档的唯一读者。**

```python
# ❌ 糟糕的工具定义 —— LLM 大概率用错
@mcp.tool()
def search(q: str, t: str = "n") -> list:
    """
    搜索
    """
    return []

# 问题分析：
# - 函数名 search 太泛化，LLM 不知道搜索什么
# - 参数名 q 和 t 不具有自解释性
# - docstring "搜索" 没有提供任何有用信息
# - 返回类型 list 过于宽泛


# ✅ 优秀的工具定义 —— LLM 能准确理解和使用
@mcp.tool()
def search_employees(
    query: str,
    search_by: Literal["name", "email", "department", "employee_id"] = "name",
    max_results: int = 20
) -> dict:
    """在员工数据库中搜索员工信息。

    支持按姓名、邮箱、部门和工号进行精确或模糊搜索。
    返回匹配的员工列表，包括姓名、部门、职位和联系方式。

    使用场景：
    - "帮我找一下市场部的张三" → search_employees("张三", "name")
    - "有没有邮箱是 @example.com 的人" → search_employees("@example.com", "email")
    - "技术部有哪些人" → search_employees("技术部", "department")
    """
    # 实现...
    pass
```

#### 3.3.3 类型注解决定 JSON Schema 生成

```python
from typing import Optional, Literal
from pydantic import BaseModel, Field
from enum import Enum

# ---- 类型注解 → JSON Schema 映射表 ----

# str               → {"type": "string"}
# int               → {"type": "integer"}
# float             → {"type": "number"}
# bool              → {"type": "boolean"}
# list[str]         → {"type": "array", "items": {"type": "string"}}
# dict              → {"type": "object"}
# Optional[str]     → {"type": "string"}（无 required 标记）
# Literal["a","b"]  → {"type": "string", "enum": ["a", "b"]}


# ---- 使用 Pydantic 定义复杂的参数结构 ----

class OrderFilter(BaseModel):
    """订单筛选条件"""
    status: Literal["pending", "shipped", "delivered", "cancelled"] = Field(
        default="pending",
        description="订单状态"
    )
    min_amount: Optional[float] = Field(
        default=None,
        description="最低订单金额，筛选金额 >= 此值的订单",
        ge=0
    )
    max_amount: Optional[float] = Field(
        default=None,
        description="最高订单金额，筛选金额 <= 此值的订单",
        ge=0
    )
    created_after: Optional[str] = Field(
        default=None,
        description="筛选此日期之后创建的订单，格式：YYYY-MM-DD"
    )

@mcp.tool()
def list_orders(filters: OrderFilter) -> dict:
    """根据条件筛选订单列表。支持按状态、金额范围和创建日期筛选。"""
    # FastMCP 会自动将 OrderFilter 的 Pydantic Schema
    # 转换为 JSON Schema 作为工具的 inputSchema
    pass


# ---- 进阶：Annotation 方式添加参数元信息 ----
from typing import Annotated

@mcp.tool()
def send_notification(
    message: Annotated[str, "通知内容，支持 Markdown 格式"],
    recipients: Annotated[list[str], "接收者列表，可填用户名或邮箱"],
    priority: Annotated[Literal["low", "normal", "high"], "优先级"] = "normal",
    channel: Annotated[
        Optional[str],
        "发送渠道，不填则使用默认渠道。可用值：email、slack、sms"
    ] = None
) -> str:
    """向指定用户发送通知消息"""
    return f"通知已通过 {channel or '默认渠道'} 发送给 {len(recipients)} 人"
```

#### 3.3.4 工具编写的十大准则

```
准则 1: DOCSTRING 是最重要的文档
  LLM 根据描述决定调用哪个工具。描述模糊 = 工具白写。

准则 2: 函数名就是 API 名
  使用动词_名词命名法：get_weather、search_employees、send_email

准则 3: 一个工具只做一件事
  ❌ process_data_and_send_email() → 拆成两个工具
  ✅ process_data() + send_email()

准则 4: 参数类型越具体越好
  ❌ data: dict
  ✅ filters: OrderFilter（Pydantic Model）

准则 5: 返回结构尽量固定
  相同工具的不同调用应返回相同结构的 dict，便于 LLM 建立预期

准则 6: 错误信息要"可操作"
  ❌ "查询失败"
  ✅ "未找到匹配的员工。建议：1) 尝试只搜姓氏 2) 检查部门名称拼写 3) 使用 email 搜索"

准则 7: 设置合理的默认值
  max_results=20，不要默认返回全量数据

准则 8: 使用 Annotations 补充 hint
  destructiveHint、readOnlyHint、idempotentHint 帮助 Host 做安全决策

准则 9: 工具应该是幂等的（读操作）
  非幂等的写操作使用 destructiveHint 标记

准则 10: 处理好异常，不要让未捕获的异常变成 JSON-RPC Internal Error
  在工具函数内部 catch 并返回有意义的错误信息
```

#### 3.3.5 全局错误处理中间件

工具函数的未捕获异常会变成 JSON-RPC `-32603 Internal Error`——LLM 收到的是冷冰冰的技术错误，无法有效决策。以下方案覆盖了从异常拦截到 LLM 友好响应的完整链路。

**面向 LLM 的异常类体系：**

```python
# error_middleware.py —— MCP 全局错误处理中间件
import functools
import traceback
import logging
import uuid
import json
from typing import Callable

logger = logging.getLogger(__name__)


class LLMFriendlyError(Exception):
    """面向 LLM 的友好异常——与普通 Exception 的区别在于包含 recovery_hint"""

    def __init__(self, message: str, recovery_hint: str = "DO_NOT_RETRY"):
        self.message = message
        self.recovery_hint = recovery_hint  # RETRY | RETRY_WITH_FIX | RETRY_LATER | DO_NOT_RETRY
        super().__init__(message)

# 预定义友好异常类型
class NotFoundError(LLMFriendlyError):
    def __init__(self, resource: str, suggestion: str = ""):
        super().__init__(
            f"未找到 {resource}。{suggestion}",
            "RETRY_WITH_FIX"
        )

class ExternalServiceError(LLMFriendlyError):
    def __init__(self, service: str, detail: str = ""):
        super().__init__(
            f"{service} 服务暂时不可用{': ' + detail if detail else ''}。建议稍后重试。",
            "RETRY_LATER"
        )

class ParamError(LLMFriendlyError):
    def __init__(self, field: str, reason: str):
        super().__init__(
            f"参数 '{field}' 不正确：{reason}。请修正后重试。",
            "RETRY_WITH_FIX"
        )


def mcp_error_handler(func: Callable) -> Callable:
    """全局错误处理装饰器——三层处理"""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs) -> str:
        try:
            return await func(*args, **kwargs)
        except LLMFriendlyError as e:
            logger.warning(f"[友好异常] {func.__name__}: {e.message}")
            return json.dumps({
                "success": False,
                "error": {"message": e.message, "recovery": e.recovery_hint}
            }, ensure_ascii=False)
        except ValueError as e:
            logger.warning(f"[参数错误] {func.__name__}: {e}")
            return json.dumps({
                "success": False,
                "error": {"message": f"参数错误：{e}。请检查参数格式和取值范围。", "recovery": "RETRY_WITH_FIX"}
            }, ensure_ascii=False)
        except Exception as e:
            error_id = uuid.uuid4().hex[:8]
            logger.error(f"[内部错误] error_id={error_id} {func.__name__}: {e}\n{traceback.format_exc()}")
            return json.dumps({
                "success": False,
                "error": {
                    "message": f"内部处理错误（ID: {error_id}）。请稍后重试，如持续请提供此 ID 给管理员。",
                    "recovery": "DO_NOT_RETRY",
                    "error_id": error_id
                }
            }, ensure_ascii=False)
    return wrapper
```

**使用示例**：

```python
@mcp.tool()
@mcp_error_handler
async def search_employees(query: str) -> str:
    if len(query) < 2:
        raise ParamError("query", "至少 2 个字符")
    try:
        results = await db.search(query)
    except ConnectionError:
        raise ExternalServiceError("数据库")
    if not results:
        raise NotFoundError(f"员工 '{query}'", "尝试只搜姓氏或用邮箱搜索")
    return json.dumps({"success": True, "data": results})
```

**面向 LLM 的错误消息原则——正反例对比：**

```python
# ❌ 面向开发者的错误——LLM 无法利用
"ERROR: SQLSTATE[HY000] Connection refused to 10.0.1.5:5432"
"IndexError: list index out of range at employee_service.py:147"

# ✅ 面向 LLM 的友好错误——LLM 能理解并决策
"数据库暂时不可用，建议稍后重试。如持续请提供错误 ID: a1b2c3d4"
"未找到匹配的员工 '张三'。建议：1) 只搜姓氏 2) 按邮箱搜索"
```

**设计规则速查**：

| 规则 | 说明 |
|------|------|
| **自然语言** | 用自然语言描述，不使用错误码（如 `ECONNREFUSED`） |
| **给出下一步** | recovery_hint 告诉 LLM：`RETRY` / `RETRY_WITH_FIX` / `DO_NOT_RETRY` |
| **提供替代方案** | 给出具体的回退建议或多路径选择 |
| **脱敏** | 内部错误只暴露 error_id（可追溯），不暴露堆栈/SQL/IP |

**isError: true vs JSON-RPC error 的决策树：**

```
发生异常
    │
    ├── 异常发生在 MCP 协议层？（JSON 格式错误 / Method Not Found / Invalid Params）
    │   └── YES → JSON-RPC Error（重试无法修复，需人工介入）
    │
    └── 异常发生在工具业务逻辑？（查不到数据 / 外部服务超时 / 参数语义错误）
        └── YES → result.isError: true（LLM 可根据错误信息调整策略）

经验法则：如果连"请求是否到达了正确的工具函数"都不确定 → JSON-RPC Error
          如果工具正确执行但业务上失败 → result.isError: true
```

### 3.4 Resource 的暴露方式

#### 3.4.1 静态资源

```python
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Resource Demo Server")

# ---- 方式一：装饰器定义静态资源 ----
@mcp.resource("config://app")
def get_app_config() -> str:
    """返回应用配置（JSON 格式）"""
    import json
    return json.dumps({
        "app_name": "MCP Demo",
        "version": "1.0.0",
        "features": ["tools", "resources", "prompts"]
    }, ensure_ascii=False, indent=2)


# ---- 方式二：URI 映射到文件 ----
# 通过 URI file:// 将本地文件暴露为 Resource
# 注意：这不占用装饰器，而是在 run() 时通过参数配置

@mcp.resource("docs://readme")
def get_readme() -> str:
    """返回项目的 README 文档"""
    with open("README.md", "r", encoding="utf-8") as f:
        return f.read()


# ---- 方式三：返回二进制资源 ----
@mcp.resource("images://logo")
def get_logo() -> bytes:
    """返回公司 Logo（PNG 格式）"""
    from mcp.types import ImageContent
    import base64
    with open("logo.png", "rb") as f:
        return f.read()
    # 注意：返回 bytes 时需要在 resource 装饰器中指定 mime_type
```

#### 3.4.2 动态资源（URI 模板）

```python
# ---- 参数化资源：通过 URI 模板暴露数据库记录 ----

# 模拟数据库
users_db = {
    1: {"name": "张三", "email": "zhangsan@example.com", "department": "技术部"},
    2: {"name": "李四", "email": "lisi@example.com", "department": "市场部"},
    3: {"name": "王五", "email": "wangwu@example.com", "department": "技术部"},
}

@mcp.resource("db://users/{user_id}")
def get_user(user_id: int) -> str:
    """获取指定用户的信息

    URI 示例：db://users/1  → 返回用户 1 的 JSON 数据
    """
    import json
    user = users_db.get(user_id)
    if not user:
        return json.dumps({"error": f"用户 {user_id} 不存在"})
    return json.dumps(user, ensure_ascii=False, indent=2)


# ---- 高级模板：跨表查询 ----
@mcp.resource("db://departments/{dept_name}/members")
def get_department_members(dept_name: str) -> str:
    """获取指定部门的所有成员

    URI 示例：db://departments/技术部/members
    """
    import json
    members = [
        u for u in users_db.values()
        if u["department"] == dept_name
    ]
    return json.dumps(members, ensure_ascii=False, indent=2)
```

#### 3.4.3 Resource 与 Tool 的协作模式

```python
# 模式：用 Tool 筛选 → 用 Resource 读取详情

# Step 1: 工具提供筛选能力
@mcp.tool()
def search_files(pattern: str, directory: str = "/data") -> list[str]:
    """搜索匹配模式的文件，返回文件路径列表"""
    import glob
    return glob.glob(f"{directory}/**/{pattern}", recursive=True)

# Step 2: 资源提供读取能力
@mcp.resource("file://{path}")
def read_file(path: str) -> str:
    """读取指定文件的内容"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# LLM 的典型使用流程：
# 1. 用户："帮我找 /data 下所有 report 开头的文件，看看里面写了什么"
# 2. LLM 调用 search_files("report*", "/data")
# 3. LLM 拿到文件列表 ["/data/report_2024.txt", "/data/report_2025.txt"]
# 4. LLM 通过 Resource 读取每个文件的内容
# 5. LLM 整合内容回复用户
```

### 3.5 构建 MCP Client

```python
# client.py —— 一个能连接 MCP Server 的客户端

import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    # 1. 配置 Server 启动参数
    server_params = StdioServerParameters(
        command="python",           # 启动命令
        args=["server.py"],         # Server 脚本路径
        env=None                    # 可传递环境变量
    )

    # 2. 建立连接
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 3. 初始化会话
            await session.initialize()
            print("✅ 已连接到 MCP Server")

            # 4. 获取工具列表
            tools_result = await session.list_tools()
            print(f"\n可用工具 ({len(tools_result.tools)} 个):")
            for tool in tools_result.tools:
                print(f"  - {tool.name}: {tool.description}")

            # 5. 调用工具
            print("\n调用 hello 工具...")
            result = await session.call_tool(
                "hello",
                arguments={"name": "MCP学习者"}
            )
            for content in result.content:
                if content.type == "text":
                    print(f"  结果: {content.text}")

            # 6. 读取资源
            try:
                resources = await session.list_resources()
                if resources.resources:
                    print(f"\n可用资源 ({len(resources.resources)} 个):")
                    for resource in resources.resources:
                        print(f"  - {resource.uri}: {resource.name}")

                    # 读取某个资源
                    content, mime_type = await session.read_resource(
                        "config://app"
                    )
                    print(f"\n资源内容:\n{content}")
            except Exception as e:
                print(f"资源操作跳过: {e}")

asyncio.run(main())
```

#### 3.5.2 构建健壮的 MCP Client

基础 Client 覆盖了 happy path，生产环境需要处理重连、超时、并发和缓存四个维度。

**维度一：重连策略（指数退避 + 自动恢复）**

```python
# robust_client.py —— 生产级 MCP Client
import asyncio
import logging
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

class RobustMCPClient:
    """自动重连 + 缓存恢复的健壮 Client"""

    def __init__(self, server_params: StdioServerParameters, max_retries: int = 10):
        self.server_params = server_params
        self.max_retries = max_retries
        self._session: ClientSession | None = None
        self._tool_cache: list | None = None
        self._read = self._write = None

    async def connect(self):
        for attempt in range(self.max_retries):
            try:
                self._read, self._write = await stdio_client(
                    self.server_params
                ).__aenter__()
                self._session = ClientSession(self._read, self._write)
                await self._session.initialize()
                # 恢复工具缓存
                tools = await self._session.list_tools()
                self._tool_cache = tools.tools
                logger.info(f"连接成功 (attempt {attempt + 1})")
                return
            except Exception as e:
                logger.warning(f"连接失败 (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    delay = min(1.0 * (2 ** attempt), 30.0)  # 指数退避, max 30s
                    await asyncio.sleep(delay)
                else:
                    raise ConnectionError(f"重连 {self.max_retries} 次后仍失败") from e

    async def call_tool(self, name: str, arguments: dict):
        """带重连重试的工具调用"""
        for attempt in range(2):
            try:
                return await self._session.call_tool(name, arguments)
            except (ConnectionError, OSError) as e:
                if attempt == 0:
                    logger.warning(f"调用失败，尝试重连: {e}")
                    await self.connect()
                else:
                    raise
```

**维度二：超时处理（分传输方式推荐值）**

| 传输方式 | connect | initialize | tool_call | 原则 |
|----------|---------|-----------|-----------|------|
| **stdio** | 10s | 5s | 30s | 本地进程，超时最短 |
| **SSE** | 15s | 10s | 60s | 跨网络 + 2 Channel，适当放宽 |
| **Streamable HTTP** | 10s | 10s | 60s | 建议在 tool_call 内再细分 HTTP 请求超时 30s |

设计原则：connect 应快速失败（避免 LLM 长时间等待），tool_call 超时应**明显小于** LLM 请求总超时（确保 LLM 能收到错误并做出决策）。

**维度三：并发调用管理**

MCP Client **可以**同时发起多个 tools/call——每个请求有独立 `id`，JSON-RPC 通过 `id` 匹配响应。但需注意：
- **stdio**：串行处理（单线程读 stdout），并发请求**可能导致响应乱序**
- **Streamable HTTP**：每个请求走独立 HTTP 连接，天然支持并发
- **需要并发能力时优先选 Streamable HTTP**

```python
class ConcurrencyManager:
    """工具调用并发控制"""
    def __init__(self, max_global: int = 10, tool_limits: dict[str, int] = None):
        self._global = asyncio.Semaphore(max_global)
        self._per_tool: dict[str, asyncio.Semaphore] = {}
        self._limits = tool_limits or {}  # 例: {"deploy": 1, "search_db": 20}

    async def acquire(self, tool_name: str):
        await self._global.acquire()
        limit = self._limits.get(tool_name, 5)
        sem = self._per_tool.setdefault(tool_name, asyncio.Semaphore(limit))
        await sem.acquire()

    def release(self, tool_name: str):
        self._global.release()
        self._per_tool.get(tool_name) and self._per_tool[tool_name].release()
```

**维度四：Client 端缓存策略**

| 缓存对象 | 策略 | 失效条件 |
|----------|------|----------|
| `tools/list` | **无 TTL**——永久有效直到收到通知 | `notifications/tools/list_changed` |
| `resources/list` | **无 TTL**——同 tools | `notifications/resources/list_changed` |
| `resources/read` | **TTL 60s**——内容可能变化 | TTL 过期 或 `notifications/resources/updated` |

> **关键认知**：`tools/list` 和 `resources/list` 的缓存**不应有时间 TTL**——它们是事件敏感的而非时间敏感的。Server 声明 `listChanged: false` 时，Client 可以整个 session 永久缓存。这是 MCP 相比 Function Calling（每次对话都携带 Schema）的 Token 节省核心来源。

### 3.6 TypeScript SDK 等价实现

```typescript
// server.ts —— TypeScript 版本的 MCP Server
import { McpServer, ResourceTemplate } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

// 创建 Server 实例
const server = new McpServer({
    name: "TypeScript MCP Server",
    version: "1.0.0"
});

// ---- 注册工具 ----
server.registerTool(
    "get_weather",
    {
        description: "获取指定城市的天气信息",
        inputSchema: {
            city: z.string().describe("城市名称，支持中英文")
        }
    },
    async ({ city }) => {
        // 模拟天气查询
        const weatherData: Record<string, { temp: number; condition: string }> = {
            "北京": { temp: 25, condition: "晴" },
            "上海": { temp: 28, condition: "多云" },
            "tokyo": { temp: 22, condition: "小雨" }
        };

        const data = weatherData[city] ?? { temp: 20, condition: "未知" };
        return {
            content: [{
                type: "text",
                text: `${city}天气：${data.condition}，气温 ${data.temp}°C`
            }]
        };
    }
);

// ---- 注册资源 ----
server.registerResource(
    "System Status",
    "system://status",
    {
        description: "当前系统状态信息",
        mimeType: "application/json"
    },
    async () => ({
        contents: [{
            uri: "system://status",
            mimeType: "application/json",
            text: JSON.stringify({
                status: "healthy",
                uptime: process.uptime(),
                memory: process.memoryUsage()
            }, null, 2)
        }]
    })
);

// ---- 注册带参数提示词 ----
server.registerPrompt(
    "greeting",
    {
        description: "生成个性化的问候语",
        argsSchema: {
            name: z.string().describe("被问候者的名字"),
            language: z.enum(["zh", "en"]).default("zh").describe("语言：zh=中文，en=英文")
        }
    },
    ({ name, language }) => ({
        messages: [{
            role: "user",
            content: {
                type: "text",
                text: language === "zh"
                    ? `请用热情友好的语气向${name}打招呼，并介绍 MCP 是什么。`
                    : `Please greet ${name} warmly and explain what MCP is.`
            }
        }]
    })
);

// 启动 Server
async function main() {
    const transport = new StdioServerTransport();
    await server.connect(transport);
    console.error("MCP Server 已启动");  // 走 stderr，不影响协议
}

main().catch(console.error);
```

```typescript
// client.ts —— TypeScript 版本的 MCP Client
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

async function main() {
    const transport = new StdioClientTransport({
        command: "npx",
        args: ["tsx", "server.ts"]
    });

    const client = new Client({
        name: "demo-client",
        version: "1.0.0"
    });

    await client.connect(transport);

    // 获取工具列表
    const tools = await client.listTools();
    console.log("可用工具:", tools.tools.map(t => t.name));

    // 调用工具
    const result = await client.callTool({
        name: "get_weather",
        arguments: { city: "北京" }
    });
    console.log("工具结果:", result.content);

    // 获取资源
    const resources = await client.listResources();
    console.log("可用资源:", resources.resources.map(r => r.uri));

    // 读取资源
    const resourceData = await client.readResource({
        uri: "system://status"
    });
    console.log("资源内容:", resourceData.contents[0].text);

    await client.close();
}

main().catch(console.error);
```

### 3.7 测试与调试

#### 3.7.1 MCP Inspector（官方调试利器）

```bash
# Inspector 是开发和调试 MCP Server 的首选工具
# 它会启动一个 Web UI，展示 Server 暴露的所有能力

# 基本使用
npx @anthropic-ai/mcp-inspector python server.py

# 带参数启动
npx @anthropic-ai/mcp-inspector node dist/server.js --port 3000

# 连接远程 SSE Server
npx @anthropic-ai/mcp-inspector --transport sse --url http://localhost:8000/mcp
```

**Inspector 的功能分区：**

```
┌─────────────────────────────────────────────────────┐
│  MCP Inspector UI                                   │
├─────────────────────┬───────────────────────────────┤
│  Left Panel         │  Right Panel                  │
│  ┌───────────────┐  │  ┌─────────────────────────┐ │
│  │ Tools         │  │  │ Raw JSON-RPC Messages   │ │
│  │  ├ get_weather│  │  │                         │ │
│  │  ├ search_emp │  │  │ → tools/call            │ │
│  │ Resources     │  │  │ ← result                │ │
│  │  ├ config://  │  │  │                         │ │
│  │ Prompts       │  │  │                         │ │
│  │  ├ code_review│  │  │                         │ │
│  └───────────────┘  │  └─────────────────────────┘ │
│  ┌───────────────┐  │  ┌─────────────────────────┐ │
│  │ Console       │  │  │ Server Logs             │ │
│  │ (手动测试)     │  │  │ (stderr 输出)           │ │
│  └───────────────┘  │  └─────────────────────────┘ │
└─────────────────────┴───────────────────────────────┘
```

#### 3.7.2 单元测试 MCP Server

```python
# test_server.py —— 对 MCP Server 进行单元测试
import pytest
import asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

@pytest.fixture
async def mcp_session():
    """创建与 Server 的测试会话"""
    server_params = StdioServerParameters(
        command="python",
        args=["server.py"]
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


@pytest.mark.asyncio
async def test_tools_list(mcp_session):
    """测试：Server 是否正确暴露了工具列表"""
    result = await mcp_session.list_tools()
    tool_names = [t.name for t in result.tools]
    assert "get_weather" in tool_names
    assert "convert_temperature" in tool_names


@pytest.mark.asyncio
async def test_get_weather(mcp_session):
    """测试：get_weather 工具返回正确格式"""
    result = await mcp_session.call_tool(
        "get_weather",
        arguments={"city": "北京"}
    )
    assert len(result.content) > 0
    assert result.content[0].type == "text"
    assert "Weather in" in result.content[0].text


@pytest.mark.asyncio
async def test_resource_read(mcp_session):
    """测试：Resource 读取正常"""
    content, mime_type = await mcp_session.read_resource("config://app")
    assert content is not None
    assert "app_name" in content


@pytest.mark.asyncio
async def test_invalid_tool_call(mcp_session):
    """测试：调用不存在的工具应返回错误"""
    result = await mcp_session.call_tool(
        "nonexistent_tool",
        arguments={}
    )
    assert result.isError is True
```

#### 3.7.3 集成测试——在 Claude Desktop 中测试

集成测试流程：

```
1. 配置 Claude Desktop
   ├── 编辑 claude_desktop_config.json
   ├── 添加你的 Server 配置
   └── 重启 Claude Desktop

2. 功能验证
   ├── 检查工具是否出现在 Claude 的工具列表中
   ├── 发起自然语言对话，触发工具调用
   ├── 观察工具返回结果是否正确
   └── 测试错误场景（传错误参数、Server 不可用等）

3. 观察点
   ├── 工具的 docstring 是否让 LLM 正确理解了使用场景？
   ├── 参数描述是否足够清晰让 LLM 正确填参？
   ├── 返回结果 LLM 是否理解正确并生成了合理的回复？
   └── 错误处理是否优雅？
```

#### 3.7.4 调试技巧汇总

```python
# ---- 技巧 1：在 Server 端开启详细日志 ----
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="[MCP] %(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr  # 注意：日志走 stderr，不能污染 stdout
)
logger = logging.getLogger(__name__)

@mcp.tool()
def debug_tool(param: str) -> str:
    logger.debug(f"debug_tool 被调用，参数: {param}")
    result = do_something(param)
    logger.debug(f"debug_tool 返回: {result}")
    return result


# ---- 技巧 2：截获原始 JSON-RPC 消息 ----
# 通过继承 StdioServerTransport 来打印所有收发消息

class DebugStdioTransport(StdioServerTransport):
    async def send(self, message):
        print(f"[MCP ←] {json.dumps(message, ensure_ascii=False)}", file=sys.stderr)
        return await super().send(message)

    async def receive(self):
        message = await super().receive()
        print(f"[MCP →] {json.dumps(message, ensure_ascii=False)}", file=sys.stderr)
        return message


# ---- 技巧 3：使用 try-except 隔离工具错误 ----
@mcp.tool()
def safe_tool(param: str) -> str:
    try:
        return potentially_failing_operation(param)
    except ValueError as e:
        return f"参数错误: {e}"
    except ConnectionError:
        return "外部服务连接失败，请稍后重试"
    except Exception as e:
        logging.exception("未预期的错误")
        return f"内部错误: {type(e).__name__}"
```

#### 3.7.5 使用 Mock Transport 进行轻量级测试

启动真实 Server 进程的集成测试成本高（进程启动开销、依赖外部环境）。Mock Transport 通过内存队列模拟通信，实现毫秒级单元测试。

**Mock Transport 实现：**

```python
# tests/mock_transport.py
import asyncio
import json

class MockTransport:
    """内存队列模拟 MCP Transport——不启动真实进程

    核心原理：
    - Client 的 write() → 消息入 _client_requests 队列（测试验证用）
    - 测试代码 write() → 消息入 _server_responses 队列（模拟 Server 响应）
    - 100% 在内存中运行，毫秒级完成
    """

    def __init__(self):
        self._client_requests: asyncio.Queue = asyncio.Queue()   # Client 发出的请求
        self._server_responses: asyncio.Queue = asyncio.Queue()  # 测试注入的响应

    async def read(self):
        return await self._server_responses.get()

    async def write(self, message: dict):
        await self._client_requests.put(message)

    # ---- 测试辅助方法 ----
    async def get_client_request(self, timeout: float = 1.0) -> dict:
        """获取 Client 发送的请求，供测试断言"""
        return await asyncio.wait_for(self._client_requests.get(), timeout=timeout)

    async def send_response(self, response: dict):
        """向 Client 注入响应"""
        await self._server_responses.put(response)

    async def simulate_initialize(self):
        """模拟完整的 initialize 握手"""
        init_req = await self.get_client_request()
        assert init_req["method"] == "initialize"
        await self.send_response({
            "jsonrpc": "2.0", "id": init_req["id"],
            "result": {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {"listChanged": True},
                    "resources": {"subscribe": True}
                },
                "serverInfo": {"name": "mock", "version": "1.0.0"}
            }
        })
        notif = await self.get_client_request()
        assert notif["method"] == "notifications/initialized"

    async def simulate_tool_response(self, request_id, text: str, is_error=False):
        await self.send_response({
            "jsonrpc": "2.0", "id": request_id,
            "result": {"content": [{"type": "text", "text": text}], "isError": is_error}
        })

    async def simulate_error(self, error_msg: str = "模拟错误"):
        await self.send_response({"jsonrpc": "2.0", "error": {"code": -32603, "message": error_msg}})
```

**五个典型测试场景：**

```python
# tests/test_with_mock.py
import pytest
import asyncio
import json
from mcp import ClientSession
from .mock_transport import MockTransport


@pytest.fixture
async def mock_session():
    transport = MockTransport()
    session = ClientSession(transport, transport)
    await asyncio.gather(session.initialize(), transport.simulate_initialize())
    yield session, transport


@pytest.mark.asyncio
async def test_normal_tool_call(mock_session):
    """测试 1：正常工具调用——验证参数传递和结果返回"""
    session, transport = mock_session
    call_task = asyncio.create_task(
        session.call_tool("get_weather", {"city": "北京"})
    )
    req = await transport.get_client_request()
    assert req["method"] == "tools/call"
    assert req["params"]["arguments"] == {"city": "北京"}
    await transport.simulate_tool_response(req["id"], "北京：晴，22°C")
    result = await call_task
    assert result.content[0].text == "北京：晴，22°C"
    assert result.isError is False


@pytest.mark.asyncio
async def test_business_error(mock_session):
    """测试 2：业务错误——isError: true 而非 JSON-RPC Error"""
    session, transport = mock_session
    call_task = asyncio.create_task(
        session.call_tool("get_weather", {"city": "X"})
    )
    req = await transport.get_client_request()
    await transport.simulate_tool_response(req["id"], "未找到该城市", is_error=True)
    result = await call_task
    assert result.isError is True


@pytest.mark.asyncio
async def test_tool_list_cache(mock_session):
    """测试 3：缓存逻辑——验证二次调用不发送请求"""
    session, transport = mock_session
    # 第一次调用 → 应发送 tools/list
    t1 = asyncio.create_task(session.list_tools())
    r1 = await transport.get_client_request()
    await transport.simulate_tool_response(r1["id"], json.dumps({"tools": [{"name": "t1"}]}))
    await t1
    # 验证队列为空（没有额外请求）
    assert transport._client_requests.empty()


@pytest.mark.asyncio
async def test_connection_error(mock_session):
    """测试 4：连接断开——Client 应抛出异常"""
    session, transport = mock_session
    call_task = asyncio.create_task(session.call_tool("x", {}))
    await transport.get_client_request()
    await transport.simulate_error("模拟网络断开")
    with pytest.raises(Exception):
        await call_task


@pytest.mark.asyncio
async def test_timeout(mock_session):
    """测试 5：超时——Client 应有超时保护"""
    session, transport = mock_session
    call_task = asyncio.create_task(
        asyncio.wait_for(session.call_tool("slow", {}), timeout=0.1)
    )
    await transport.get_client_request()
    # 不发送响应 → 等待超时
    with pytest.raises(asyncio.TimeoutError):
        await call_task
```

**三层测试策略速查**：

| 测试类型 | 耗时 | 覆盖场景 |
|----------|------|----------|
| Mock Transport | **毫秒级** | 参数传递、返回格式、错误处理、缓存逻辑、超时/断开 |
| stdio 集成测试 | 秒级 | 进程生命周期、版本协商、端到端功能 |
| 远程集成测试 | 秒级（含网络） | 网络延迟、TLS、认证、Streamable HTTP |

---

## 四、底层原理——SDK 内部机制剖析

### 4.1 FastMCP 装饰器的魔法

FastMCP 的 `@mcp.tool()` 装饰器背后做了大量工作。理解这些有助于写出更好的代码，也能在出错时快速排障。

```python
# FastMCP.tool() 装饰器内部的等价展开

# 你写的代码：
@mcp.tool()
def get_weather(city: str) -> str:
    """获取指定城市的天气信息"""
    return f"Weather in {city}: 22°C"

# ============ 装饰器内部等价于 ============

def get_weather(city: str) -> str:
    """获取指定城市的天气信息"""
    return f"Weather in {city}: 22°C"

# 步骤 1：从类型注解提取 JSON Schema
input_schema = {
    "type": "object",
    "properties": {
        "city": {
            "type": "string",
            "description": ""  # FastMCP 尝试从 docstring 或 Annotated 中提取
        }
    },
    "required": ["city"]  # 无默认值的参数 → required
}

# 步骤 2：从 docstring 提取描述
description = "获取指定城市的天气信息"

# 步骤 3：构造 Tool 对象并注册
tool = Tool(
    name="get_weather",        # 函数名
    description=description,   # docstring 第一段
    inputSchema=input_schema   # 从类型注解推导
)
mcp._tool_manager.register_tool(tool, handler=get_weather)
```

**类型注解 → JSON Schema 的映射细节：**

```
Python 类型              →  JSON Schema 类型
═══════════════════════════════════════════════════
str                      →  {"type": "string"}
int                      →  {"type": "integer"}
float                    →  {"type": "number"}
bool                     →  {"type": "boolean"}
list[T]                  →  {"type": "array", "items": T_Schema}
dict[str, T]             →  {"type": "object", "additionalProperties": T_Schema}
Optional[T]              →  T_Schema（不加入 required 列表）
T | None                 →  同上
Literal["a", "b"]        →  {"type": "string", "enum": ["a", "b"]}
Annotated[T, desc]       →  T_Schema，并用 desc 填充 description 字段
Pydantic BaseModel       →  递归展开模型字段
```

### 4.2 请求的生命周期（Server 端视角）

```
             stdio / SSE / Streamable HTTP
                        │
┌───────────────────────▼──────────────────────────┐
│               Transport Layer                     │
│  接收字节流 → 换行符分帧 → JSON 反序列化           │
└───────────────────────┬──────────────────────────┘
                        │ JSON 对象
┌───────────────────────▼──────────────────────────┐
│             JSON-RPC Dispatcher                   │
│  验证 JSON-RPC 字段（jsonrpc, method, id）        │
│  路由 method → handler                            │
│  错误处理（Parse Error, Invalid Request）         │
└───────────────────────┬──────────────────────────┘
                        │
     ┌──────────────────┼──────────────────────┐
     ▼                  ▼                      ▼
┌─────────┐    ┌──────────────┐    ┌────────────────┐
│Session  │    │Tool Manager  │    │Resource Mgr    │
│Manager  │    │              │    │                │
├─────────┤    ├──────────────┤    ├────────────────┤
│initialize   │tools/list     │    │resources/list   │
│initialized  │tools/call     │    │resources/read   │
│shutdown     │               │    │resources/       │
│ping         │               │    │subscribe        │
└─────────┘    └──────────────┘    └────────────────┘

     ┌──────────────────┼──────────────────────┐
     ▼                  ▼                      ▼
┌──────────┐    ┌───────────────┐    ┌─────────────────┐
│ 你的函数  │    │   你的函数     │    │   你的函数       │
│          │    │               │    │                 │
│get_weather  │  search_products│    │get_user(user_id)│
│(city)    │    │(keyword, max) │    │                 │
└──────────┘    └───────────────┘    └─────────────────┘
```

### 4.3 传输层切换的原理

```python
# FastMCP 的 transport 参数如何切换底层传输

# mcp.run(transport="stdio")
# ↓
mcp.run(transport="stdio")
# 内部等价于：
transport = StdioServerTransport()
await server.connect(transport)

# mcp.run(transport="sse", port=8000)
# ↓
mcp.run(transport="sse", port=8000)
# 内部等价于：
transport = SseServerTransport(host="0.0.0.0", port=8000)
await server.connect(transport)

# mcp.run(transport="streamable-http", port=8000)
# ↓
mcp.run(transport="streamable-http", port=8000)
# 内部等价于：
transport = StreamableHTTPServerTransport(host="0.0.0.0", port=8000)
await server.connect(transport)
```

> 关键点：你的工具函数代码**完全不需要知道底层用的是哪种传输**。这是 SDK 的核心抽象价值——业务逻辑和传输协议解耦。

### 4.4 Client 端协议协商的底层流程

```
Client                          Server
  │                                │
  │  1. 发送 initialize             │
  │  {                             │
  │    protocolVersion: "2025..."  │
  │    capabilities: {             │
  │      roots: {...},             │
  │      sampling: {}              │
  │    }                           │
  │  }                             │
  │ ─────────────────────────────> │
  │                                │
  │  2. 收到 initialize 响应        │
  │  {                             │
  │    protocolVersion: "2025..."  │
  │    capabilities: {             │
  │      tools: {},                │
  │      resources: {              │
  │        subscribe: true         │
  │      }                         │
  │    }                           │
  │  }                             │
  │ <───────────────────────────── │
  │                                │
  │  3. 发送 initialized 通知       │
  │ ─────────────────────────────> │
  │                                │
  │  4. SDK 根据协商结果配置行为：   │
  │     - session.capabilities     │
  │       .tools = True            │
  │       .resources.subscribe     │
  │         = True                 │
  │     - 后续请求自动遵循这些能力  │
```

---

## 五、企业级最佳实践

### 5.1 项目结构推荐

```
my-mcp-project/
├── pyproject.toml              # 项目元数据和依赖
├── README.md                   # 项目说明 + MCP Server 配置示例
├── .env.example                # 环境变量模板（API Key 等）
├── src/
│   └── my_mcp_server/
│       ├── __init__.py
│       ├── server.py           # FastMCP 实例创建和 run() 入口
│       ├── tools/              # 工具函数（按业务域拆分）
│       │   ├── __init__.py
│       │   ├── weather.py      # 天气相关工具
│       │   ├── database.py     # 数据库查询工具
│       │   └── notifications.py # 通知发送工具
│       ├── resources/          # 资源定义
│       │   ├── __init__.py
│       │   ├── files.py        # 文件系统资源
│       │   └── api.py          # 外部 API 资源
│       ├── prompts/            # 提示词模板
│       │   ├── __init__.py
│       │   └── templates.py
│       └── utils/              # 工具函数
│           ├── __init__.py
│           ├── auth.py         # 认证相关
│           └── logging.py      # 日志配置
├── tests/
│   ├── __init__.py
│   ├── conftest.py             # pytest fixtures（MCP session 等）
│   ├── test_tools.py
│   ├── test_resources.py
│   └── test_integration.py
├── scripts/
│   └── run_inspector.sh        # 启动 Inspector 的脚本
└── .github/
    └── workflows/
        └── test.yml            # CI 测试流程
```

### 5.2 工具模块化与注册

```python
# src/my_mcp_server/server.py —— 主入口
from mcp.server.fastmcp import FastMCP
from .tools import register_all_tools
from .resources import register_all_resources
from .prompts import register_all_prompts

def create_server() -> FastMCP:
    """创建并配置 MCP Server 实例"""
    mcp = FastMCP("Enterprise MCP Server")

    # 注册各模块的能力
    register_all_tools(mcp)
    register_all_resources(mcp)
    register_all_prompts(mcp)

    return mcp

if __name__ == "__main__":
    server = create_server()
    server.run(transport="stdio")


# src/my_mcp_server/tools/weather.py —— 按业务域拆分
def register_weather_tools(mcp: FastMCP):
    """注册天气相关的工具"""

    @mcp.tool()
    def get_weather(city: str) -> str: ...

    @mcp.tool()
    def get_forecast(city: str, days: int = 7) -> str: ...


# src/my_mcp_server/tools/__init__.py —— 统一注册
from .weather import register_weather_tools
from .database import register_database_tools
from .notifications import register_notification_tools

def register_all_tools(mcp: FastMCP):
    register_weather_tools(mcp)
    register_database_tools(mcp)
    register_notification_tools(mcp)
```

### 5.3 敏感信息管理

```python
# ❌ 硬编码凭证——绝对禁止
@mcp.tool()
def query_db(sql: str) -> str:
    conn = psycopg2.connect("postgresql://admin:MyP@ssw0rd@10.0.1.5/prod")
    # ...

# ✅ 从环境变量读取
import os
from functools import lru_cache

class Config:
    @property
    def database_url(self) -> str:
        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL 环境变量未设置")
        return url

    @property
    def api_key(self) -> str:
        return os.environ.get("API_KEY", "")

@lru_cache()
def get_config() -> Config:
    return Config()

@mcp.tool()
def query_db(sql: str) -> str:
    conn = psycopg2.connect(get_config().database_url)
    # ...
```

### 5.4 错误处理策略

```python
from enum import Enum
from dataclasses import dataclass

class ErrorCode(str, Enum):
    INVALID_PARAM = "INVALID_PARAM"
    NOT_FOUND = "NOT_FOUND"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    RATE_LIMITED = "RATE_LIMITED"

@dataclass
class ToolError:
    code: ErrorCode
    message: str
    suggestion: str = ""

def make_error_response(code: ErrorCode, message: str, suggestion: str = "") -> str:
    """统一错误响应格式"""
    return json.dumps({
        "success": False,
        "error": {
            "code": code.value,
            "message": message,
            "suggestion": suggestion
        }
    }, ensure_ascii=False)

@mcp.tool()
def get_user(user_id: int) -> str:
    """获取用户信息"""
    try:
        user = user_service.find_by_id(user_id)
        if not user:
            return make_error_response(
                ErrorCode.NOT_FOUND,
                f"用户 {user_id} 不存在",
                "请检查用户 ID 是否正确，或尝试用 search_users 工具搜索"
            )
        return json.dumps(user.to_dict(), ensure_ascii=False)

    except ExternalServiceError as e:
        return make_error_response(
            ErrorCode.EXTERNAL_SERVICE_ERROR,
            f"用户服务暂时不可用: {e}",
            "请稍后重试，或联系管理员"
        )
```

### 5.5 性能优化

```python
# ---- 1. 避免每次调用都重新建立连接 ----
# 使用模块级缓存
from functools import lru_cache
import httpx

@lru_cache()
def get_db_connection():
    """数据库连接缓存（整个 Server 生命周期复用）"""
    return psycopg2.connect(get_config().database_url)

@lru_cache(maxsize=128)
def get_http_client() -> httpx.Client:
    """HTTP Client 复用连接池"""
    return httpx.Client(timeout=10)


# ---- 2. 资源读取结果缓存 ----
_resource_cache: dict[str, tuple[float, str]] = {}  # uri → (expiry, content)
CACHE_TTL = 60  # 秒

async def read_resource_cached(uri: str) -> str:
    """带缓存的资源读取"""
    now = time.time()
    if uri in _resource_cache:
        expiry, content = _resource_cache[uri]
        if now < expiry:
            return content  # 命中缓存
    content = await _do_read_resource(uri)
    _resource_cache[uri] = (now + CACHE_TTL, content)
    return content


# ---- 3. 大结果分批返回 ----
@mcp.tool()
def search_logs(query: str, page: int = 1, page_size: int = 50) -> dict:
    """搜索日志（分页返回）"""
    offset = (page - 1) * page_size
    logs = log_service.search(query, limit=page_size, offset=offset)
    total = log_service.count(query)
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "has_more": offset + page_size < total,
        "logs": logs
    }
```

---

## 六、常见面试题

### 基础开发

**Q1: FastMCP 是什么？与 Low-Level API 有什么区别？**

<details>
<summary>参考答案</summary>

**FastMCP** 是 MCP Python SDK 提供的高层 API，通过装饰器（`@mcp.tool()`、`@mcp.resource()`）简化 Server 开发。它采用"约定优于配置"的设计理念。

**对比：**

| 维度 | FastMCP | Low-Level API |
|------|---------|---------------|
| 工具注册 | `@mcp.tool()` 装饰器 | 手动构造 `Tool` 对象 + 注册 handler |
| Schema 生成 | 从 Python 类型注解自动推导 | 手写 JSON Schema |
| 学习成本 | 5 分钟上手 | 需要理解 MCP 协议细节 |
| 适用场景 | 90% 的常规需求 | 需要完全控制协议行为的场景 |

**核心坑点：** MCP SDK 1.2.0 之前使用的 `server.run()` 写法已被废弃，必须使用 `FastMCP` 或 Low-Level API 的 `stdio_server()`。

</details>

---

**Q2: 工具函数的 docstring 为什么重要？应该怎么写？**

<details>
<summary>参考答案</summary>

LLM 完全依赖 `description`（docstring + 参数注解）来决定：
1. **何时调用这个工具**（在什么场景下选择它）
2. **如何填充参数**（每个参数应该传什么值）

**好的 docstring 应包含：**
1. 工具做什么（一句话概括）
2. 使用场景说明（什么时候该用这个工具）
3. 参数的含义和格式约束
4. 返回值的结构说明

```python
@mcp.tool()
def search_employees(
    query: str,
    search_by: Literal["name", "email", "department"] = "name",
    max_results: int = 20
) -> dict:
    """在员工数据库中搜索员工信息。

    支持按姓名、邮箱和部门进行模糊搜索。返回匹配的员工列表。

    使用场景：
    - "帮我找一下张三" → 按姓名搜索
    - "技术部有哪些人" → 按部门搜索
    - "有没有 @example.com 邮箱的人" → 按邮箱搜索
    """
```

</details>

---

**Q3: 如何在 Python SDK 中定义一个动态 Resource（URI 模板）？**

<details>
<summary>参考答案</summary>

使用 `@mcp.resource()` 装饰器的 URI 模板语法：

```python
@mcp.resource("db://users/{user_id}")
def get_user(user_id: int) -> str:
    """获取指定用户信息"""
    return json.dumps(users_db.get(user_id, {}))
```

**URI 模板规则：**
- `{param_name}` 声明一个路径参数
- 参数名与函数参数名一一对应
- 参数类型从函数类型注解推导
- Client 可通过 `resources/templates/list` 发现模板

</details>

---

### 类型系统与 Schema

**Q4: Python 类型注解是如何映射为 JSON Schema 的？Optional 和 Literal 分别怎么处理？**

<details>
<summary>参考答案</summary>

**映射规则：**

| Python 类型 | JSON Schema |
|-------------|-------------|
| `str` | `{"type": "string"}` |
| `int` | `{"type": "integer"}` |
| `float` | `{"type": "number"}` |
| `bool` | `{"type": "boolean"}` |
| `Optional[str]` | `{"type": "string"}` 且**不加入** `required` 列表 |
| `Literal["a", "b"]` | `{"type": "string", "enum": ["a", "b"]}` |
| `Annotated[T, "desc"]` | T 的 Schema + `description: "desc"` |
| Pydantic `BaseModel` | 递归展开为 `{"type": "object", "properties": {...}}` |

**为什么 Optional 不加入 required？**
`required` 列表包含所有没有默认值的参数。`Optional[T]` 等价于 `T | None`，默认值隐含为 `None`，所以不在 `required` 中。

</details>

---

### 测试与调试

**Q5: 如何测试和调试一个 MCP Server？有哪些工具可用？**

<details>
<summary>参考答案</summary>

**三层测试策略：**

1. **MCP Inspector**（开发期交互测试）：
   ```bash
   npx @anthropic-ai/mcp-inspector python server.py
   ```
   提供 Web UI，可查看工具/资源/提示词列表和原始 JSON-RPC 消息。

2. **单元测试**（功能验证）：
   ```python
   async with stdio_client(params) as (read, write):
       async with ClientSession(read, write) as session:
           await session.initialize()
           result = await session.call_tool("my_tool", {...})
           assert result.content[0].text == expected
   ```

3. **Claude Desktop 集成测试**（端到端验证）：
   在 `claude_desktop_config.json` 注册 Server，通过自然语言对话触发工具，观察 LLM 是否能正确选择和使用工具。

**调试技巧：**
- Server 日志走 `stderr`，不能污染 `stdout`
- 使用 `logging` 模块记录 DEBUG 级别日志
- 可封装 DebugTransport 截获原始 JSON-RPC 消息

</details>

---

### 设计理解

**Q6: MCP SDK 如何实现传输层无关性？换传输方式需要改工具代码吗？**

<details>
<summary>参考答案</summary>

SDK 通过**传输层抽象接口**实现传输无关性。工具函数完全不接触底层传输细节。

```python
# 切换传输只需改一行代码，工具定义完全不变
mcp.run(transport="stdio")             # 本地
mcp.run(transport="sse", port=8000)    # 远程 HTTP
mcp.run(transport="streamable-http")   # 生产环境
```

**原理：** SDK 内部定义了 `Transport` 抽象接口，`StdioServerTransport`、`SseServerTransport`、`StreamableHTTPServerTransport` 都实现了这个接口。Server 只依赖接口，不依赖具体实现。

这就是**依赖倒置原则**（DIP）的体现——业务逻辑（工具函数）不依赖传输细节，双方都依赖抽象（Transport 接口）。

</details>

---

### Go SDK 与跨语言

**Q7: 公司后端是 Go 技术栈，你会如何用 Go SDK 构建 MCP Server？与 Python 有什么不同？**

<details>
<summary>参考答案</summary>

首选社区最活跃的 `mark3labs/mcp-go`。

**与 Python FastMCP 的关键差异**：

1. **Schema 手写成本**：Go 没有装饰器 + 类型推导，每个参数需手写 `mcp.WithString()` / `mcp.WithNumber()` / `mcp.Required()` / `mcp.Description()`。工具数 > 10 时建议写代码生成工具
2. **并发模型**：Go goroutine 天然适合 MCP 并发调用，handler 中需检查 `ctx.Done()` 以支持 Cancelled 通知。注意共享状态的 `sync.Mutex` 保护
3. **部署优势**：编译为单一二进制文件，Docker scratch 镜像 < 10MB（Python 约 100MB+）
4. **选型建议**：小型 Server（< 10 工具）推荐 Python FastMCP（开发效率高），大型 Server / 微服务 / 高并发推荐 Go（性能和部署优势）

</details>

---

**Q8: 如果你要设计一个有 50 个工具的 MCP Server，你会如何组织代码？**

<details>
<summary>参考答案</summary>

**核心思路：按业务域拆分 + 统一注册**

```
src/my_server/
├── server.py          # FastMCP 实例 + run() 入口
├── tools/
│   ├── __init__.py    # register_all_tools(mcp) → 汇总注册
│   ├── user.py        # 用户相关工具（5个）
│   ├── order.py       # 订单相关工具（8个）
│   ├── analytics.py   # 数据分析工具（10个）
│   └── admin.py       # 管理工具（5个）
├── resources/
│   └── ...
└── prompts/
    └── ...
```

**还要考虑：**
1. 工具命名空间前缀避免冲突（`user_search`、`order_search`）
2. 共享逻辑抽到 `utils/` 或 `services/` 层
3. 为高频工具写好 docstring（影响 LLM 选择准确率）
4. 使用 `destructiveHint` 标记写操作工具
5. 统一错误处理中间件/装饰器

</details>

---

**Q9: 一个生产级 MCP Client 需要处理哪些健壮性问题？具体如何实现？**

<details>
<summary>参考答案</summary>

四个核心维度：

1. **重连策略**：指数退避（1s→2s→4s→...→max 30s），最大重试 10 次。重连成功后自动 re-initialize + 恢复缓存
2. **超时处理**：分操作类型（connect: 10-15s / tool_call: 30-60s）和分传输方式（stdio < SSE < Streamable HTTP）设置。tool_call 超时应明显小于 LLM 请求总超时
3. **并发控制**：Streamable HTTP 天然支持（独立 HTTP 连接），stdio 串行。按工具做差异化限流（deploy: 1串行, search_db: 20高并发）
4. **Client 缓存**：`tools/list` 无 TTL（事件驱动失效，收到 `tools/list_changed` 才刷新）；`resources/read` TTL 60s。缓存是 MCP 相比 Function Calling 在 Token 节省上的核心优势

**加分点**：提一句 "stale-while-revalidate" 策略——返回缓存结果的同时异步刷新。

</details>

---

## 附录

### 快速参考：FastMCP 装饰器速查

| 装饰器 | 用途 | 示例 |
|--------|------|------|
| `@mcp.tool()` | 注册可调用的工具函数 | `@mcp.tool()\ndef get_weather(city: str) -> str:` |
| `@mcp.resource(uri)` | 注册可读取的资源 | `@mcp.resource("config://app")` |
| `@mcp.prompt()` | 注册提示词模板 | 需配合 `list_prompts` 和 `get_prompt` |

### 快速参考：mcp.run() transport 参数

| 值 | 含义 | 额外参数 |
|----|------|----------|
| `"stdio"` | 标准输入输出（默认） | 无 |
| `"sse"` | Server-Sent Events | `port`（必填）, `host` |
| `"streamable-http"` | Streamable HTTP | `port`（必填）, `host` |

### 开发命令速查

```bash
# 安装
pip install mcp==1.3.0
npm install @modelcontextprotocol/sdk@1.0.4

# 调试
npx @anthropic-ai/mcp-inspector python server.py

# 运行测试
pytest tests/ -v
pytest tests/ -v -k "test_tool"  # 只跑工具相关测试

# 创建新项目（推荐模板）
pip install mcp[cli]             # 安装 CLI 工具
mcp create my-server             # 交互式创建项目（如果 SDK 支持）
```

### 推荐阅读

- [MCP Python SDK 文档](https://github.com/modelcontextprotocol/python-sdk)
- [MCP TypeScript SDK 文档](https://github.com/modelcontextprotocol/typescript-sdk)
- [MCP Inspector 使用指南](https://modelcontextprotocol.io/docs/tools/inspector)
- [FastMCP 迁移指南（从 server.run() 迁移）](https://github.com/modelcontextprotocol/python-sdk/releases)
