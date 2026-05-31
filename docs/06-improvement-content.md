# 模块 6 改进内容

> 目标：★★★☆☆ → ★★★★★  
> 六项：修复闭包Bug + 重写CrewAI + OpenAI SDK + 评测调试 + 企业落地 + A2A深化

---

## 任务 1：修复 LangGraph 闭包 Bug（替换 §3.1.2 中的 to_langchain_tools）

**问题代码**（当前第 254-268 行附近）：

```python
# ❌ 闭包 Bug：所有 wrapper 最终指向循环中最后一个 mcp_tool
def to_langchain_tools(self):
    from langchain_core.tools import tool
    langchain_tools = []
    for mcp_tool in self._tools:
        @tool(mcp_tool.name, description=mcp_tool.description or "")
        async def mcp_tool_wrapper(**kwargs):
            result = await self._session.call_tool(
                mcp_tool.name,  # ← Bug! mcp_tool 是循环变量，延迟绑定
                arguments=kwargs
            )
            ...
```

**原因**：Python 闭包的**延迟绑定**特性——循环变量 `mcp_tool` 在 `for` 循环结束后才被闭包引用，此时 `mcp_tool` 指向的是最后一个元素。

**修复**：通过默认参数在定义时立即捕获当前值：

```python
# ✅ 修复后——通过默认参数捕获当前 mcp_tool
def to_langchain_tools(self):
    from langchain_core.tools import tool
    langchain_tools = []
    for mcp_tool in self._tools:
        # 关键修复：利用默认参数在函数定义时立即求值，捕获当前 mcp_tool
        def make_wrapper(tool_name: str, tool_desc: str | None, _tool: object):
            @tool(tool_name, description=tool_desc or "")
            async def wrapper(**kwargs):
                result = await self._session.call_tool(tool_name, arguments=kwargs)
                texts = []
                for content in result.content:
                    if hasattr(content, "text"):
                        texts.append(content.text)
                return "\n".join(texts)
            wrapper.name = tool_name
            return wrapper

        wrapper = make_wrapper(mcp_tool.name, mcp_tool.description, mcp_tool)
        langchain_tools.append(wrapper)

    return langchain_tools
```

**面试追问**："为什么要用 `make_wrapper` 工厂函数？不用工厂函数会怎样？"

**答案**：Python 闭包使用延迟绑定（late binding）——内部函数引用外部变量时，取的是调用时的值而非定义时的值。`for mcp_tool in tools` 中，循环结束后 `mcp_tool` 始终指向最后一个。工厂函数 `make_wrapper(name, desc, tool)` 在**每次循环迭代时立即调用**，参数在函数调用时求值，从而"冻结"了当前迭代的值。这是 Python 面试中的经典考点。

---

## 任务 2：重写 CrewAI 集成（替换 §3.2 全部内容）

**问题**：① `asyncio.run()` 在已有 event loop 中会崩溃 ② `self._session._tool_list` 依赖私有 API ③ 无异常处理和资源管理。

**替换后的完整实现**：

```python
# crewai_mcp_integration.py —— CrewAI + MCP 集成（修复版）
# 依赖: pip install crewai mcp langchain-core
import asyncio
from crewai import Agent, Task, Crew, Process
from langchain_core.tools import tool as lc_tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPToolProvider:
    """为 CrewAI Agent 提供 MCP 工具的适配器

    关键设计：
    1. 使用公开 API (session.list_tools()) 获取工具列表，不依赖私有属性
    2. 工具函数 await 真正的异步调用（而非 asyncio.run()），与 CrewAI 的 async 兼容
    3. 完善的异常处理和资源清理
    """

    def __init__(self, server_name: str, server_command: list[str]):
        self.server_name = server_name
        self.server_command = server_command
        self._session: ClientSession | None = None
        self._read = None
        self._write = None
        self._tool_defs: list = []  # 工具定义缓存

    async def connect(self):
        """连接到 MCP Server 并获取工具列表"""
        server_params = StdioServerParameters(
            command=self.server_command[0],
            args=self.server_command[1:]
        )
        self._read, self._write = (
            await stdio_client(server_params).__aenter__()
        )
        self._session = ClientSession(self._read, self._write)
        await self._session.initialize()

        # ★ 使用公开 API 获取工具列表
        result = await self._session.list_tools()
        self._tool_defs = result.tools

    async def close(self):
        """清理资源"""
        if self._read and self._write:
            try:
                # 清理 stdio 连接
                pass
            except Exception:
                pass

    def to_langchain_tools(self) -> list:
        """将 MCP 工具转换为 CrewAI/LangChain 兼容格式"""
        tools = []

        for tool_def in self._tool_defs:
            # 闭包修复：通过工厂函数捕获当前 tool_def
            def make_tool(name: str, desc: str | None):

                @lc_tool(name, description=desc or "")
                def tool_func(**kwargs) -> str:
                    """同步包装器——CrewAI 工具目前要求同步函数"""
                    # 在独立线程中运行 async 调用
                    import threading
                    result_holder = []
                    error_holder = []

                    def run_async():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            result = loop.run_until_complete(
                                self._session.call_tool(name, arguments=kwargs)
                            )
                            texts = []
                            for c in result.content:
                                if hasattr(c, "text"):
                                    texts.append(c.text)
                            result_holder.append("\n".join(texts))
                        except Exception as e:
                            error_holder.append(e)
                        finally:
                            loop.close()

                    thread = threading.Thread(target=run_async)
                    thread.start()
                    thread.join(timeout=30)

                    if error_holder:
                        return f"工具调用失败: {error_holder[0]}"
                    if not result_holder:
                        return "工具调用超时（30s）"
                    return result_holder[0]

                tool_func.name = name
                return tool_func

            tool = make_tool(
                tool_def.name,
                tool_def.description
            )
            tools.append(tool)

        return tools


async def build_crewai_team():
    """构建 CrewAI 多 Agent 团队（完整生产级示例）"""

    # 初始化 MCP 工具提供者
    db_mcp = MCPToolProvider("Database", ["python", "-m", "db_explorer.server"])
    ops_mcp = MCPToolProvider("Operations", ["python", "-m", "ops_assistant.server"])

    await db_mcp.connect()
    await ops_mcp.connect()

    try:
        # ---- 定义 Agent ----
        data_analyst = Agent(
            role="数据分析师",
            goal="从数据库提取数据并进行深度分析",
            backstory="你是一位经验丰富的数据分析师，擅长 SQL 查询和统计分析方法。",
            tools=db_mcp.to_langchain_tools(),
            verbose=True
        )

        ops_engineer = Agent(
            role="运维工程师",
            goal="检查系统健康状态和部署情况",
            backstory="你是一位资深 SRE，熟悉各种运维工具和基础设施监控。",
            tools=ops_mcp.to_langchain_tools(),
            verbose=True
        )

        report_writer = Agent(
            role="报告撰写人",
            goal="整合数据和运维信息，生成专业的分析报告",
            backstory="你擅长将技术数据转化为管理层可读的商业报告。",
            tools=[],
            verbose=True
        )

        # ---- 定义 Task ----
        extract_data = Task(
            description="从数据库提取技术部所有成员近 30 天的提交记录和代码审查数据",
            agent=data_analyst,
            expected_output="结构化的数据表，包含提交数、代码审查通过率、活跃度排名"
        )

        check_infra = Task(
            description="检查所有核心服务的健康状态，汇总部署成功率和事故记录",
            agent=ops_engineer,
            expected_output="基础设施健康报告，包含服务状态、部署统计和事故列表"
        )

        generate_report = Task(
            description="整合数据分析和基础设施报告，生成完整的月度技术报告",
            agent=report_writer,
            expected_output="Markdown 格式的月度技术报告，包含数据、图表描述和建议",
            context=[extract_data, check_infra]
        )

        # ---- 创建 Crew ----
        crew = Crew(
            agents=[data_analyst, ops_engineer, report_writer],
            tasks=[extract_data, check_infra, generate_report],
            process=Process.sequential,
            verbose=True
        )

        result = crew.kickoff()
        return result

    finally:
        await db_mcp.close()
        await ops_mcp.close()


if __name__ == "__main__":
    report = asyncio.run(build_crewai_team())
    print(report)
```

---

## 任务 3：OpenAI Agents SDK + MCP 集成（新增 §3.2.5）

**插入位置**：在重写的 CrewAI §3.2 之后，大厂案例 §3.3 之前。

### §3.2.5 OpenAI Agents SDK + MCP 集成

OpenAI Agents SDK 于 2025 年正式发布，已成为多 Agent 编排主流选择。其核心特性 `handoff`（交接）天然契合 MCP 的工具接入模式。

```python
# openai_agents_mcp.py —— OpenAI Agents SDK + MCP 集成
# 依赖: pip install openai-agents mcp
import asyncio
from agents import Agent, Runner, function_tool, handoff
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPToolBridge:
    """将 MCP 工具桥接到 OpenAI Agents SDK 的 @function_tool 格式"""

    def __init__(self):
        self._session: ClientSession | None = None
        self._tools: list = []

    async def connect(self, command: list[str]):
        params = StdioServerParameters(command=command[0], args=command[1:])
        read, write = await stdio_client(params).__aenter__()
        self._session = ClientSession(read, write)
        await self._session.initialize()
        result = await self._session.list_tools()
        self._tools = result.tools

    def to_openai_tools(self):
        """将 MCP 工具转换为 OpenAI Agents SDK function_tool"""
        openai_tools = []
        for t in self._tools:
            t_name = t.name
            t_desc = t.description

            @function_tool(name_override=t_name, description_override=t_desc or "")
            async def tool_func(**kwargs, _name=t_name, _session=self._session):
                result = await _session.call_tool(_name, arguments=kwargs)
                texts = [c.text for c in result.content if hasattr(c, "text")]
                return "\n".join(texts)

            openai_tools.append(tool_func)
        return openai_tools


async def build_openai_agent_team():
    """构建 OpenAI Agents SDK 多 Agent 团队（MCP 工具 + Handoff）"""

    # 连接 MCP Server
    db_bridge = MCPToolBridge()
    ops_bridge = MCPToolBridge()
    await db_bridge.connect(["python", "-m", "db_explorer.server"])
    await ops_bridge.connect(["python", "-m", "ops_assistant.server"])

    # ---- 定义 Agent ----

    # 数据分析 Agent（拥有 MCP 数据库工具）
    data_agent = Agent(
        name="DataAnalyst",
        instructions="你是数据分析专家。使用可用工具从数据库提取和分析数据。完成后输出结构化的 JSON 分析报告。",
        tools=db_bridge.to_openai_tools(),
        model="gpt-4o",
    )

    # 运维 Agent（拥有 MCP 运维工具）
    ops_agent = Agent(
        name="OpsEngineer",
        instructions="你是资深 SRE。使用可用工具检查服务健康状态、部署状态和系统指标。",
        tools=ops_bridge.to_openai_tools(),
        model="gpt-4o",
    )

    # 报告生成 Agent（无工具，接收前两个 Agent 的结果）
    report_agent = Agent(
        name="ReportWriter",
        instructions="你是报告撰写专家。基于数据和运维报告，生成综合性的月度技术报告。",
        tools=[],  # 纯文本处理，无需工具
        model="gpt-4o",
    )

    # ---- 编排 Agent（协调 + Handoff）----
    orchestrator = Agent(
        name="Orchestrator",
        instructions=(
            "你是任务协调器。收到用户请求后：\n"
            "1. 先 handoff 到 DataAnalyst 获取数据分析\n"
            "2. 同时 handoff 到 OpsEngineer 获取运维报告\n"
            "3. 将两份结果交给 ReportWriter 生成最终报告\n"
            "4. 将最终报告返回给用户"
        ),
        handoffs=[
            handoff(data_agent, tool_name_override="delegate_to_analyst",
                    tool_description_override="将数据分析任务委派给数据分析 Agent"),
            handoff(ops_agent, tool_name_override="delegate_to_ops",
                    tool_description_override="将运维检查任务委派给运维 Agent"),
            handoff(report_agent, tool_name_override="delegate_to_writer",
                    tool_description_override="将报告撰写任务委派给报告 Agent"),
        ],
        model="gpt-4o",
    )

    # 执行
    result = await Runner.run(
        orchestrator,
        "请生成技术部本月度的综合报告，包括代码提交分析和服务健康状态。"
    )
    return result.final_output


if __name__ == "__main__":
    output = asyncio.run(build_openai_agent_team())
    print(output)
```

**OpenAI Agents SDK 的 Handoff 机制 vs LangGraph 的 Graph 机制**：

| 维度 | OpenAI Handoff | LangGraph StateGraph |
|------|---------------|---------------------|
| 编程模型 | LLM 自主决定何时交接、交给谁 | 开发者显式定义节点和边 |
| 控制粒度 | 粗（Agent 级别） | 细（节点级别） |
| 适合场景 | 灵活的任务委派 | 确定性多步流程 |
| 与 MCP 的关系 | Agent 通过 function_tool 使用 MCP 工具 | 节点通过 ToolNode 使用 MCP 工具 |

---

## 任务 4：多 Agent 系统的评测与调试（新增 §3.4）

**插入位置**：大厂案例 §3.3 之后，§四「底层原理」之前。

### §3.4 多 Agent 系统的评测、监控与调试

#### 3.4.1 评测指标体系

| 指标 | 定义 | 计算方法 | 目标 |
|------|------|----------|------|
| **任务完成率** | 端到端任务成功完成的比例 | `success / total_tasks` | > 90% |
| **首轮正确率** | 无需人工修正即完成任务的比例 | `correct_on_first_try / total` | > 70% |
| **平均工具调用数** | 每个任务的平均 tools/call 次数 | `total_tool_calls / total_tasks` | < 5 |
| **Token 效率** | 每任务的 Token 消耗 | `total_tokens / total_tasks` | 持续优化趋势 |
| **端到端延迟** | 用户请求到最终回复的时间 | p50 / p95 / p99 | p95 < 30s |
| **Agent 间交接次数** | 任务在 Agent 间传递的次数 | 人均 | < 3（频繁交接 = 设计问题） |

#### 3.4.2 调用链追踪

```python
# trace.py —— 跨 Agent 调用链追踪
import uuid, time, json, logging
from contextvars import ContextVar

# 协程安全的 Trace 上下文
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_parent_span_id: ContextVar[str] = ContextVar("parent_span_id", default="")

class TraceSpan:
    """一次工具调用或 Agent 推理的追踪 Span"""
    def __init__(self, operation: str, agent: str, tool: str = ""):
        self.span_id = uuid.uuid4().hex[:8]
        self.trace_id = _trace_id.get() or uuid.uuid4().hex[:16]
        self.operation = operation   # "tool_call" | "agent_reasoning" | "handoff"
        self.agent = agent
        self.tool = tool
        self.start = time.perf_counter()
        self.end: float = 0
        self.parent_span_id = _parent_span_id.get()
        self.input_summary = ""
        self.output_summary = ""
        self.error: str | None = None

    def finish(self, output: str = "", error: str = None):
        self.end = time.perf_counter()
        self.output_summary = output[:200]
        self.error = error
        duration_ms = (self.end - self.start) * 1000
        log_entry = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "operation": self.operation,
            "agent": self.agent,
            "tool": self.tool,
            "duration_ms": round(duration_ms, 2),
            "error": error,
        }
        logging.getLogger("mcp.trace").info(json.dumps(log_entry, ensure_ascii=False))

    def __enter__(self):
        _parent_span_id.set(self.span_id)
        return self

    def __exit__(self, *args):
        _parent_span_id.set(self.parent_span_id)
        self.finish()


class AgentTrace:
    """Agent 级别的追踪上下文管理器"""
    def __init__(self, agent_name: str, task_id: str):
        self.agent = agent_name
        self.task_id = task_id

    async def __aenter__(self):
        self.trace_id = uuid.uuid4().hex[:16]
        _trace_id.set(self.trace_id)
        return self

    async def __aexit__(self, *args):
        _trace_id.set("")
        # 汇总该 Agent 的所有 Span 统计
        print(f"[Trace {self.trace_id}] Agent={self.agent} 任务完成")


# 使用示例：在 LangGraph 的每个 Agent 节点中包裹
async def analysis_node(state: AgentState):
    async with AgentTrace("DataAnalyst", state.get("task_id", "")):
        with TraceSpan("agent_reasoning", "DataAnalyst") as span:
            # LLM 推理...
            span.finish(output="分析完成")
        with TraceSpan("tool_call", "DataAnalyst", tool="search_employees"):
            # 工具调用...
            pass
```

#### 3.4.3 异常定位方法论

当多 Agent 系统行为异常时，按以下步骤排查：

```
Step 1: 确定异常 Agent
  看 Trace 日志 → 找到最早出现 error 的 Span → 确定是哪个 Agent

Step 2: 还原现场
  从 Trace 中提取该 Agent 的完整输入（用户指令 + 上游 Agent 传递的上下文）
  用相同输入单独运行该 Agent（隔离测试）

Step 3: 检查工具输出
  查看该 Agent 调用了哪些 MCP 工具 → 工具的返回值是否异常？
  常见：LLM 友好的错误信息被 LLM 误解，导致错误传播

Step 4: 检查 Prompt 注入
  上游 Agent 的输出是否包含类似 [系统提示] 的指令片段？
  这可能导致下游 Agent 被"劫持"

Step 5: 检查 Handoff 边界
  交接时传递的上下文是否完整？是否存在信息截断？
  交接的 Agent 是否具备完成子任务所需的工具？
```

---

## 任务 5：企业落地 MCP 的挑战（新增 §3.5）

**插入位置**：§3.4 之后，§四「底层原理」之前。

### §3.5 企业落地 MCP 的实际挑战与应对策略

大厂的 MCP 产品看起来光鲜，但企业内部落地面临三个维度的阻力。

#### 3.5.1 组织层面

| 挑战 | 具体表现 | 应对策略 |
|------|----------|----------|
| **安全审批** | 安全团队对"让 AI 直接调用生产工具"极为谨慎，审批流程可能长达数月 | 分阶段推进：先开放只读工具（查询）→ 灰度开放写操作（部署）→ 建立自动化安全审查流水线 |
| **基础设施适配** | 现有系统可能运行在内网、使用自签证书、不支持 HTTP/2，与 MCP 的 Streamable HTTP 不兼容 | 先用 stdio 模式在本地试点，逐步升级基础设施；提供 MCP-to-Legacy 协议适配网关 |
| **跨团队协作** | 工具归属团队可能不愿意为"别人的 AI"维护工具接口 | 建立内部 MCP 工具市场 + 工具贡献激励机制（如 OKR 关联、内部开源贡献榜） |
| **标准选型争议** | MCP vs OpenAI Function Calling vs 自研方案——团队间存在技术路线分歧 | 先在小团队 POC（Proof of Concept），用数据说话（如：MCP 方案节省了 X 人天/月） |

#### 3.5.2 技术债务

**REST API → MCP 的迁移策略**：

```
Phase 1: 并行期（1-3 个月）
  · 新建 MCP Server 包装现有 REST API（薄封装过渡方案）
  · REST API 和 MCP Server 同时提供，逐步引导内部消费者迁移
  · 监控迁移比例（MCP 调用量 / 总调用量）

Phase 2: 优化期（3-6 个月）
  · 重构为领域优化的复合工具，消除薄封装的 N+1 问题
  · 废弃不再被调用的 REST API 端点

Phase 3: 治理期（6+ 个月）
  · MCP 成为新工具的唯一接入标准
  · 旧 REST API 进入维护模式（仅安全修复）
  · 建立工具质量审查和废弃机制
```

**新旧协议并存治理**：

```python
# 协议适配网关——让旧 REST API 也能通过 MCP 协议访问
# 在组织迁移期，这是一个重要的过渡组件

@mcp.tool()
async def legacy_order_lookup(order_id: str) -> dict:
    """查询订单——MCP 包装旧 REST API"""
    # 内部调用旧系统的 REST API
    response = await httpx.get(
        f"https://legacy-api.internal/orders/{order_id}",
        headers={"X-API-Key": os.environ["LEGACY_API_KEY"]}
    )
    data = response.json()
    # MCP 化的关键：在返回前做 LLM 友好处理
    return {
        "order_id": data["id"],
        "status": _humanize_status(data["status"]),  # "pending_payment" → "待支付"
        "items": _simplify_items(data["line_items"]),  # 简化字段
        "total": data["total_amount"],
    }
```

#### 3.5.3 人才缺口

```
当前 MCP 人才市场现状（2025 年估算）：

  了解 MCP 概念                   ~50,000 人（看过文章/文档）
  能用 FastMCP 写简单工具          ~10,000 人（跑过 Quickstart）
  能设计复合工具 + N+1 优化        ~2,000 人（有生产经验）
  能设计 MCP Gateway + 多租户平台   ~500 人（大厂核心团队）
  能贡献 MCP 协议级别代码           ~50 人（Anthropic + 核心贡献者）

企业应对：
  · 内部培训：用本教材 7 模块做 2 个月脱产培训
  · 外部招聘：面试中考查复合工具设计、跨 Server 事务策略、安全威胁建模
  · 社区贡献：鼓励工程师向 MCP 开源社区提交 PR，培养深度理解
```

---

## 任务 6：A2A 协议深化（扩展 §4.1-4.2）

### 替换并扩展 §4.1「A2A 协议核心概念」和 §4.2「MCP 与 A2A 的协同」

**替换后内容**：

### 4.1 A2A 协议核心概念（深化版）

#### 4.1.1 Task 生命周期状态机

```
                    ┌─────────┐
                    │ pending │  ← Agent Card 声明的能力匹配后，任务进入待分配
                    └────┬────┘
                         │ assign
                    ┌────▼────┐
                    │ working │  ← Agent 正在执行任务
                    └────┬────┘
                         │
              ┌──────────┼──────────┐
              ▼          ▼          ▼
        ┌─────────┐ ┌──────────┐ ┌──────────┐
        │completed│ │  failed  │ │ cancelled│
        └─────────┘ └────┬─────┘ └──────────┘
                         │
                    ┌────▼────┐
                    │  retry  │ ← 可重试错误 → 返回 working（有最大重试次数）
                    └─────────┘
```

#### 4.1.2 Agent Card 机制

Agent Card 是 A2A 中 Agent 向其他 Agent **声明自身能力**的元数据文件，类似于 MCP 的 `tools/list` 但面向的是 Agent 之间的协作。

```json
// agent_card.json —— Agent 向 A2A 网络声明自己的能力
{
    "name": "DataAnalystAgent",
    "description": "数据分析专家，擅长 SQL 查询、统计分析和趋势预测",
    "url": "https://agents.internal.example.com/data-analyst",
    "version": "1.0.0",
    "capabilities": {
        "streaming": true,
        "pushNotifications": false,
        "stateTransitionHistory": true
    },
    "skills": [
        {
            "id": "sql_analysis",
            "name": "SQL 数据分析",
            "description": "对结构化数据库执行复杂 SQL 查询和分析",
            "tags": ["sql", "analytics", "database"],
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query_description": {
                        "type": "string",
                        "description": "用自然语言描述分析需求"
                    }
                }
            },
            "outputSchema": {
                "type": "object",
                "properties": {
                    "analysis_report": {"type": "string"},
                    "data": {"type": "array"}
                }
            }
        }
    ],
    "defaultInputModes": ["text", "json"],
    "defaultOutputModes": ["text", "json"],
    "security": {
        "authentication": "oauth2",
        "authorization_url": "https://auth.internal.example.com/authorize"
    }
}
```

#### 4.1.3 Agent Card vs MCP tools/list

| 维度 | Agent Card | MCP tools/list |
|------|-----------|----------------|
| 服务对象 | 其他 Agent | LLM / Host |
| 声明粒度 | Skill 级别（比 Tool 更粗，一个 Skill 可能包含多个工具） | Tool 级别（一个工具一个声明） |
| 包含内容 | Skill 描述 + 端点 URL + 安全信息 + 输入输出 Schema | 工具名 + 描述 + 参数 JSON Schema |
| 发现方式 | Agent 主动注册到 A2A 网络 | Client 连接 Server 后调用 tools/list |
| 更新通知 | 通过 Agent Card 重新发布 | `notifications/tools/list_changed` |

### 4.2 MCP 与 A2A 的协同——完整代码演示

```python
# mcp_a2a_orchestration.py —— MCP + A2A 协同编排
"""
场景：用户说"分析技术部的代码质量并生成改进建议"

流程：
  1. Orchestrator Agent 解析用户意图 → 决定需要两个子任务
  2. 子任务 A：数据提取 → 通过 MCP 调用 search_employees + get_employee_commits
  3. 子任务 B：代码分析 → 通过 A2A 委托给 CodeReviewAgent
  4. 合并结果 → 生成最终回复

关键边界决策：
  · 数据获取 → MCP（直接的工具调用）
  · 复杂分析 → A2A（委托给专业 Agent，专业 Agent 内部可能又通过 MCP 使用工具）
"""

import asyncio
from dataclasses import dataclass

@dataclass
class A2ATaskRequest:
    """A2A 任务请求"""
    task_id: str
    skill_id: str          # 对应 Agent Card 中的 skill
    input_data: dict
    callback_url: str      # 完成后通知的 URL
    max_retries: int = 3

@dataclass
class A2ATaskResponse:
    """A2A 任务响应"""
    task_id: str
    status: str            # "completed" | "failed" | "working"
    result: dict | None = None
    error: str | None = None


class OrchestratorAgent:
    """协调 Agent——融合 MCP 工具调用和 A2A 任务委派"""

    def __init__(self, mcp_session: ClientSession, a2a_registry_url: str):
        self.mcp_session = mcp_session      # MCP 连接（工具调用）
        self.a2a_registry = a2a_registry_url # A2A 注册中心（Agent 发现）

    async def execute(self, user_request: str) -> str:
        # Step 1: 分析意图
        intent = await self._analyze_intent(user_request)

        tasks = []

        # Step 2: 需要从数据库获取数据 → 走 MCP
        if intent["needs_data"]:
            # ★ MCP 调用：直接工具调用
            dept_data = await self.mcp_session.call_tool(
                "get_department_overview",
                {"department_name": intent["department"]}
            )
            tasks.append(("data", dept_data))

        # Step 3: 需要专业代码分析 → 走 A2A
        if intent["needs_code_review"]:
            # ★ A2A 委派：发现具有 code_review skill 的 Agent
            capable_agents = await self._discover_agents_by_skill("code_review")
            if capable_agents:
                code_agent = capable_agents[0]
                # 发送 A2A 任务
                a2a_task = A2ATaskRequest(
                    task_id=str(uuid.uuid4()),
                    skill_id="code_review",
                    input_data={
                        "repository": intent["repo"],
                        "branch": intent.get("branch", "main"),
                        "focus": "quality_and_security"
                    },
                    callback_url="https://orchestrator.internal/callback"
                )
                # 异步委派（不阻塞）
                a2a_result = await self._delegate_to_agent(code_agent, a2a_task)
                tasks.append(("code_review", a2a_result))

        # Step 4: 合并 MCP 数据 + A2A 分析结果
        return await self._synthesize_results(tasks)

    async def _discover_agents_by_skill(self, skill_id: str) -> list[dict]:
        """通过 A2A 注册中心发现具有指定 skill 的 Agent"""
        # A2A 注册中心查询
        agents = await httpx.get(f"{self.a2a_registry}/agents?skill={skill_id}")
        return agents.json()

    async def _delegate_to_agent(
        self, agent_info: dict, task: A2ATaskRequest
    ) -> A2ATaskResponse:
        """向 Agent 发送 A2A 任务"""
        response = await httpx.post(
            f"{agent_info['url']}/tasks",
            json=task.__dict__
        )
        return A2ATaskResponse(**response.json())

    async def _synthesize_results(self, tasks: list) -> str:
        # LLM 合成 MCP 工具结果 + A2A Agent 输出
        prompt = f"基于以下 MCP 数据和 A2A 分析生成综合报告:\n{tasks}"
        ...


# MCP 边界 vs A2A 边界的决策规则
"""
什么时候用 MCP（直接工具调用）？
  · 操作是确定的、步骤明确的（查数据库、调 API、读文件）
  · 不需要另一个 Agent 的领域知识
  · 延迟要求低（需要即时返回）
  · 调用方完全控制参数

什么时候用 A2A（委派给其他 Agent）？
  · 任务需要另一个领域的专业知识和推理能力
  · 任务步骤不确定，需要 Agent 自主规划
  · 任务耗时较长，适合异步执行
  · 需要利用其他 Agent 的 MCP 工具（Agent 可以有自己的 MCP Server）
"""
```

**MCP vs A2A 的边界决策树**：

```
这个操作是"调用一个工具"还是"委托一个任务"？

├── "查北京天气"                    → MCP（确定、即时、参数明确）
├── "部署 v2.1.0 到 staging"       → MCP（步骤确定，参数明确）
├── "分析技术部代码质量"             → A2A（需要代码领域专业知识）
├── "生成月度财务报告"               → A2A（需要财务领域 Agent 推理）
└── "找关于 Q2 预算的所有信息"       → 混合：MCP 跨系统搜索 + A2A 委托分析 Agent 解读
```

---

## 插入汇总

| 序号 | 操作 | 位置 | 内容 |
|------|------|------|------|
| 1 | **修复** §3.1.2 | 替换 `to_langchain_tools()` | 闭包 Bug 修复 + 原理解释 + 面试追问 |
| 2 | **重写** §3.2 | 完整替换 | 修复 asyncio.run() + 私有 API + 异常处理 + 资源清理 |
| 3 | **新增** §3.2.5 | §3.2 后 | OpenAI Agents SDK + Handoff + 三框架对比 |
| 4 | **新增** §3.4 | §3.3 后 | 评测指标 + TraceSpan 调用链 + 异常定位 5 步法 |
| 5 | **新增** §3.5 | §3.4 后 | 组织/技术/人才三维落地挑战 + REST→MCP 迁移策略 |
| 6 | **扩展** §4.1-4.2 | 替换 | Task 状态机 + Agent Card + MCP+A2A 协同代码 + 决策树 |
| 7 | **新增 Q5-Q8** | §6 | 闭包 Bug / Handoff对比 / 评测体系 / 边界决策 |
