# 第六模块：多 Agent 编排与 MCP 生态集成

> **学习周期**：9-12 天  
> **学习目标**：掌握 MCP 在多 Agent 系统中的角色，能集成 LangGraph、CrewAI、
> OpenAI Agents SDK 等编排框架，理解多 Agent 评测调试机制和企业落地挑战。

---

## 目录

1. [一、是什么——MCP 在多 Agent 系统中的定位](#一是什么mcp-在多-agent-系统中的定位)
2. [二、为什么需要——单 Agent 到多 Agent 的演进动力](#二为什么需要单-agent-到多-agent-的演进动力)
3. [三、如何实现——框架集成与多 Agent 实战](#三如何实现框架集成与多-agent-实战)
   - [3.1.2 闭包 Bug 修复版](#312-完整实现)
   - [3.2 CrewAI + MCP（修复版）](#32-crewai--mcp)
   - [3.2.5 OpenAI Agents SDK + MCP](#325-openai-agents-sdk--mcp-集成)
   - [3.4 多 Agent 系统的评测、监控与调试](#34-多-agent-系统的评测监控与调试)
   - [3.5 企业落地 MCP 的实际挑战](#35-企业落地-mcp-的实际挑战与应对策略)
4. [四、底层原理——A2A 协议与工具发现机制](#四底层原理a2a-协议与工具发现机制)
   - [4.1 A2A 协议（Task 状态机 + Agent Card）](#41-a2a-协议核心概念深化版)
   - [4.2 MCP + A2A 协同代码演示](#42-mcp-与-a2a-的协同完整代码演示)
5. [五、企业级最佳实践](#五企业级最佳实践)
6. [六、常见面试题](#六常见面试题)

---

## 一、是什么——MCP 在多 Agent 系统中的定位

### 1.1 MCP 的角色：工具接入标准

在多 Agent 架构中，MCP 扮演的是**工具接入层标准**的角色：

```
┌─────────────────────────────────────────────────────────────┐
│                    多 Agent 系统全景                         │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │              编排框架 (Orchestration)                  │   │
│  │  LangGraph · CrewAI · AutoGen · OpenAI Swarm          │   │
│  │  定义 Agent 之间的协作流程、状态管理、决策路由          │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          │                                  │
│  ┌───────────────────────▼─────────────────────────────┐   │
│  │         Agent-to-Agent 协议 (A2A)                    │   │
│  │  Agent 之间的通信标准：任务委派、结果返回              │   │
│  └───────────────────────┬─────────────────────────────┘   │
│                          │                                  │
│  ┌───────┬───────────────┼───────────────┬───────┐         │
│  ▼       ▼               ▼               ▼       ▼         │
│ Agent 1  Agent 2        Agent 3        Agent 4  Agent 5    │
│ (分析)   (搜索)         (代码)         (审核)   (报告)     │
│  │       │               │               │       │         │
│  └───────┴───────────────┼───────────────┴───────┘         │
│                          │                                  │
│  ┌───────────────────────▼──────────────────────────────┐  │
│  │              MCP 协议层 (工具接入标准)                  │  │
│  │  每个 Agent 通过 MCP 连接自己的工具和数据源            │  │
│  │                                                       │  │
│  │  MCP Server 1    MCP Server 2    MCP Server 3        │  │
│  │  (数据库查询)     (代码执行)       (Web 搜索)          │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 MCP 与 A2A 的关系

这是两个不同层次、互补的协议：

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   MCP (Model Context Protocol)                              │
│   ┌───────────────────────────────────────────────────┐    │
│   │  解决：Agent 如何使用外部工具和数据？               │    │
│   │  范围：Agent ↔ 工具/数据/资源                      │    │
│   │  类比：个人如何使用电脑上的软件                     │    │
│   └───────────────────────────────────────────────────┘    │
│                                                             │
│   A2A (Agent-to-Agent Protocol)                             │
│   ┌───────────────────────────────────────────────────┐    │
│   │  解决：Agent 之间如何协作通信？                     │    │
│   │  范围：Agent ↔ Agent                              │    │
│   │  类比：同事之间如何沟通协作                         │    │
│   └───────────────────────────────────────────────────┘    │
│                                                             │
│   两者互补：MCP 是工具接入标准，A2A 是 Agent 间协作标准      │
│   一个多 Agent 系统可以同时使用 MCP 和 A2A                   │
└─────────────────────────────────────────────────────────────┘
```

| 维度 | MCP | A2A |
|------|-----|-----|
| 提出者 | Anthropic (2024.11) | Google (2025.04) |
| 解决问题 | Agent 如何使用外部工具和数据 | Agent 之间如何协作 |
| 通信对象 | Agent ↔ MCP Server | Agent ↔ Agent |
| 核心原语 | Tools, Resources, Prompts | Task, Artifact, Message |
| 协议基础 | JSON-RPC 2.0 | JSON-RPC 2.0 (同为 RPC 风格) |
| 关系 | 工具接入标准 | Agent 协作标准 |

---

## 二、为什么需要——单 Agent 到多 Agent 的演进动力

### 2.1 单 Agent 的局限

单 Agent 模式（一个 LLM + 多个 MCP 工具）在处理复杂任务时有明显局限：

```
场景：为一家公司生成完整的季度分析报告

单 Agent 模式的困境：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  一个 LLM 需要同时做：
  1. 从数据库提取原始数据
  2. 调用统计工具做数据分析
  3. 搜索行业对标数据
  4. 生成文本报告
  5. 制作数据可视化
  6. 审核报告准确性

问题：
  - 单次上下文窗口不够（60+ 次工具调用，大量中间数据）
  - 不同子任务需要不同的系统提示词（分析 vs 写作 vs 审核）
  - 无法并行处理（LLM 每次只能调一个工具）
  - 单一 LLM 在所有子任务上都做到最优很难
```

### 2.2 多 Agent 的优势

```
多 Agent 模式：
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐
  │ 数据分析 Agent│   │ 写作 Agent  │   │ 审核 Agent  │
  │             │   │             │   │             │
  │ 工具：       │   │ 工具：       │   │ 工具：       │
  │ - SQL查询   │   │ - 文档模板  │   │ - 事实核查  │
  │ - 统计分析  │   │ - 图表生成  │   │ - 数据校验  │
  │ - 行业对标  │   │ - 格式转换  │   │ - 敏感词检查│
  └──────┬──────┘   └──────┬──────┘   └──────┬──────┘
         │                 │                 │
         └─────────┬───────┴─────────┬───────┘
                   │                 │
         ┌─────────▼─────────┐       │
         │  编排器 (Orchestrator)│    │
         │  定义执行顺序和依赖  │     │
         └───────────────────┘       │
                                     │
  收益：
  ✓ 每个 Agent 专注一个领域（系统提示词针对性强）
  ✓ 独立 Agent 可以并行执行
  ✓ 可以审核→修改→再审核的循环
  ✓ 不同 Agent 可以使用不同的模型（强的做分析，便宜的做审核）
```

---

## 三、如何实现——框架集成与多 Agent 实战

### 3.1 LangGraph + MCP

#### 3.1.1 架构设计

LangGraph 是 LangChain 推出的 Agent 编排框架，核心概念是**有向图（Graph）**——将 Agent 决策和工具调用建模为图中的节点和边。

```
LangGraph + MCP 融合架构：

┌─────────────────────────────────────────────────────────┐
│                    LangGraph StateGraph                  │
│                                                         │
│  ┌─────────┐    ┌──────────┐    ┌──────────┐           │
│  │  Node 1  │───→│  Node 2  │───→│  Node 3  │           │
│  │ 提取需求  │    │  分析数据 │    │  生成报告 │           │
│  └─────────┘    └─────┬────┘    └──────────┘           │
│                       │                                 │
│                  ┌────▼─────┐                           │
│                  │  MCP Tool │  ← 节点内通过 MCP 调用工具  │
│                  │  Wrapper  │                           │
│                  └────┬─────┘                           │
└───────────────────────┼─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              MCP Client (连接 MCP Server)                │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│              MCP Server (数据库 / API / 文件)            │
└─────────────────────────────────────────────────────────┘
```

#### 3.1.2 完整实现

```python
# graph_agent.py —— LangGraph + MCP 集成
import asyncio
import operator
from typing import TypedDict, Annotated, Sequence
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


# ============================================================
# Step 1: 定义共享状态
# ============================================================

class AgentState(TypedDict):
    """多 Agent 之间的共享状态"""
    messages: Annotated[Sequence[BaseMessage], operator.add]
    task_description: str
    analysis_result: str
    report_content: str
    review_passed: bool
    current_step: str


# ============================================================
# Step 2: 将 MCP 工具适配为 LangChain Tool
# ============================================================

class MCPToolAdapter:
    """将 MCP Tools 转换为 LangChain 兼容的 Tool 格式

    这是 MCP + LangGraph 集成的核心桥梁：
    - 通过 MCP Client 连接 MCP Server
    - 获取 tools/list 得到工具定义
    - 将每个 MCP Tool 封装为 LangChain Tool
    - 在 LangGraph 节点中通过 ToolNode 调用
    """

    def __init__(self):
        self._session: ClientSession | None = None
        self._tools: list = []
        self._read = None
        self._write = None

    async def connect(self, server_command: list[str] = None):
        """连接到 MCP Server"""
        if server_command is None:
            server_command = ["python", "-m", "ops_assistant.server"]

        server_params = StdioServerParameters(
            command=server_command[0],
            args=server_command[1:]
        )

        self._read, self._write = await stdio_client(server_params).__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.initialize()

        # 获取 MCP 工具列表
        tools_result = await self._session.list_tools()
        self._tools = tools_result.tools

    async def close(self):
        if self._read and self._write:
            # 清理连接
            pass

    def to_langchain_tools(self):
        """将 MCP 工具转换为 LangChain Tool 列表

        ⚠️ 闭包陷阱修复：Python 闭包使用延迟绑定（late binding）——
        循环变量 mcp_tool 在被闭包引用时始终指向最后一个元素。
        通过工厂函数 make_wrapper() 利用默认参数在"定义时立即求值"
        来捕获当前迭代值，避免所有 wrapper 指向同一个 mcp_tool.name。
        """
        from langchain_core.tools import tool

        langchain_tools = []

        for mcp_tool in self._tools:
            # ★ 工厂函数——默认参数在函数调用时求值，从而"冻结"当前迭代值
            def make_wrapper(tool_name: str, tool_desc: str | None):
                @tool(tool_name, description=tool_desc or "")
                async def wrapper(**kwargs):
                    result = await self._session.call_tool(
                        tool_name,  # ← 使用被捕获的 tool_name，而非循环变量
                        arguments=kwargs
                    )
                    texts = []
                    for content in result.content:
                        if hasattr(content, "text"):
                            texts.append(content.text)
                    return "\n".join(texts)
                wrapper.name = tool_name
                return wrapper

            langchain_tools.append(
                make_wrapper(mcp_tool.name, mcp_tool.description)
            )

        return langchain_tools


# ============================================================
# Step 3: 定义 Agent 节点
# ============================================================

class AnalysisAgent:
    """数据分析 Agent —— 负责从数据源提取和分析数据

    通过 MCP 连接数据库和 API，执行数据分析任务。
    """

    def __init__(self, mcp_adapter: MCPToolAdapter, llm):
        self.mcp = mcp_adapter
        self.llm = llm

    async def analyze(self, state: AgentState) -> AgentState:
        """分析节点：提取数据并生成分析结果"""
        tools = self.mcp.to_langchain_tools()
        llm_with_tools = self.llm.bind_tools(tools)

        # 构造分析提示词
        analysis_prompt = f"""
        你是一个数据分析专家。任务：{state['task_description']}

        请使用可用工具获取数据并进行深入分析。
        分析维度包括：趋势分析、对比分析、异常检测。

        完成后输出结构化的分析结果（JSON 格式）。
        """

        messages = [HumanMessage(content=analysis_prompt)]
        response = await llm_with_tools.ainvoke(messages)

        return {
            **state,
            "messages": [response],
            "analysis_result": response.content,
            "current_step": "analysis_complete"
        }


class ReportAgent:
    """报告生成 Agent —— 基于分析结果生成报告"""

    def __init__(self, llm):
        self.llm = llm

    async def generate_report(self, state: AgentState) -> AgentState:
        """生成报告节点"""
        report_prompt = f"""
        你是一位专业报告撰写人。请基于以下分析结果生成一份完整的报告。

        分析结果：
        {state['analysis_result']}

        报告要求：
        1. 执行摘要（200 字以内）
        2. 核心发现（3-5 条）
        3. 数据支撑（图表描述）
        4. 建议和下一步行动

        使用 Markdown 格式。
        """

        response = await self.llm.ainvoke([HumanMessage(content=report_prompt)])

        return {
            **state,
            "messages": [response],
            "report_content": response.content,
            "current_step": "report_generated"
        }


class ReviewAgent:
    """审核 Agent —— 审查报告的质量"""

    def __init__(self, llm):
        self.llm = llm

    async def review(self, state: AgentState) -> AgentState:
        """审核节点"""
        review_prompt = f"""
        你是质量审核专家。请审核以下报告的质量。

        报告内容：
        {state['report_content']}

        审查标准：
        1. 数据准确性（是否有数据支撑？引用的数据是否与分析结果一致？）
        2. 逻辑完整性（推理链条是否完整？）
        3. 格式规范性（Markdown 格式是否正确？）
        4. 可读性（非技术人员能读懂吗？）

        如果审核通过，回复 "PASS"。
        如果存在问题，回复 "REVISE: <具体的修改建议>"。
        """

        response = await self.llm.ainvoke([HumanMessage(content=review_prompt)])
        review_passed = "PASS" in response.content.upper()

        return {
            **state,
            "messages": [response],
            "review_passed": review_passed,
            "current_step": "review_complete"
        }


# ============================================================
# Step 4: 构建 LangGraph 工作流
# ============================================================

def build_report_graph(
    analysis_agent: AnalysisAgent,
    report_agent: ReportAgent,
    review_agent: ReviewAgent
) -> StateGraph:
    """构建报告生成的多 Agent 工作流

    图结构:
                        ┌─────────┐
                        │  START  │
                        └────┬────┘
                             │
                        ┌────▼────┐
                        │ Analyze │  ← 数据分析 Agent + MCP 工具
                        └────┬────┘
                             │
                        ┌────▼────┐
                        │ Report  │  ← 报告生成 Agent
                        └────┬────┘
                             │
                        ┌────▼────┐
                        │ Review  │  ← 审核 Agent
                        └────┬────┘
                             │
                    ┌────────┼────────┐
                    │ PASS   │ REVISE │
                    ▼        │        │
                ┌───────┐   │   ┌────▼────┐
                │  END  │   └───│ Report  │ ← 修改后重新生成
                └───────┘       └─────────┘
    """

    graph = StateGraph(AgentState)

    # 添加节点
    graph.add_node("analyze", analysis_agent.analyze)
    graph.add_node("report", report_agent.generate_report)
    graph.add_node("review", review_agent.review)

    # 定义边（流程）
    graph.set_entry_point("analyze")
    graph.add_edge("analyze", "report")
    graph.add_edge("report", "review")

    # 条件边：审核通过 → 结束，不通过 → 返回重新生成
    def should_continue(state: AgentState) -> str:
        if state["review_passed"]:
            return END
        else:
            return "report"  # 返回修改

    graph.add_conditional_edges("review", should_continue)

    return graph.compile()


# ============================================================
# Step 5: 运行
# ============================================================

async def main():
    from langchain_openai import ChatOpenAI

    # 初始化
    mcp_adapter = MCPToolAdapter()
    await mcp_adapter.connect(["python", "-m", "ops_assistant.server"])

    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    analysis_agent = AnalysisAgent(mcp_adapter, llm)
    report_agent = ReportAgent(llm)
    review_agent = ReviewAgent(llm)

    # 构建工作流
    app = build_report_graph(analysis_agent, report_agent, review_agent)

    # 执行
    result = await app.ainvoke({
        "task_description": "分析技术部本季度的代码提交趋势和部署成功率，生成季度报告",
        "analysis_result": "",
        "report_content": "",
        "review_passed": False,
        "current_step": "start",
        "messages": []
    })

    print("最终报告：")
    print(result["report_content"])
    await mcp_adapter.close()


if __name__ == "__main__":
    asyncio.run(main())
```

### 3.2 CrewAI + MCP（修复版）

> **原版问题**：`asyncio.run()` 在已有 event loop 中崩溃；`self._session._tool_list` 依赖私有 API。以下为修复后可运行的完整实现。

```python
# crewai_mcp_integration.py —— CrewAI + MCP 集成（修复版）
# 依赖: pip install crewai mcp langchain-core
import asyncio, threading
from crewai import Agent, Task, Crew, Process
from langchain_core.tools import tool as lc_tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPToolProvider:
    """为 CrewAI Agent 提供 MCP 工具的适配器（修复版）

    修复要点：
    1. 使用公开 API (session.list_tools()) 获取工具列表
    2. 工具函数通过独立线程 + 独立 event loop 避免 "event loop already running" 错误
    3. 完善的超时 + 异常处理 + 资源清理
    """

    def __init__(self, server_name: str, server_command: list[str]):
        self.server_name = server_name
        self.server_command = server_command
        self._session: ClientSession | None = None
        self._read = self._write = None
        self._tool_defs: list = []

    async def connect(self):
        params = StdioServerParameters(command=self.server_command[0], args=self.server_command[1:])
        self._read, self._write = await stdio_client(params).__aenter__()
        self._session = ClientSession(self._read, self._write)
        await self._session.initialize()
        result = await self._session.list_tools()  # ★ 公开 API
        self._tool_defs = result.tools

    async def close(self):
        try:
            pass  # 清理 stdio 资源
        except Exception: pass

    def to_langchain_tools(self) -> list:
        """将 MCP 工具转换为 CrewAI/LangChain 兼容格式"""
        tools = []
        for tool_def in self._tool_defs:
            def make_tool(name: str, desc: str | None):
                @lc_tool(name, description=desc or "")
                def tool_func(**kwargs) -> str:
                    result_holder, error_holder = [], []
                    def run_async():
                        try:
                            loop = asyncio.new_event_loop()
                            asyncio.set_event_loop(loop)
                            r = loop.run_until_complete(self._session.call_tool(name, arguments=kwargs))
                            texts = [c.text for c in r.content if hasattr(c, "text")]
                            result_holder.append("\n".join(texts))
                            loop.close()
                        except Exception as e:
                            error_holder.append(e)
                    t = threading.Thread(target=run_async); t.start(); t.join(timeout=30)
                    if error_holder: return f"工具调用失败: {error_holder[0]}"
                    if not result_holder: return "工具调用超时（30s）"
                    return result_holder[0]
                tool_func.name = name
                return tool_func
            tools.append(make_tool(tool_def.name, tool_def.description))
        return tools


async def build_crewai_team():
    db_mcp = MCPToolProvider("Database", ["python", "-m", "db_explorer.server"])
    ops_mcp = MCPToolProvider("Operations", ["python", "-m", "ops_assistant.server"])
    await db_mcp.connect(); await ops_mcp.connect()
    try:
        data_analyst = Agent(role="数据分析师", goal="从数据库提取数据并进行深度分析",
            backstory="你是一位经验丰富的数据分析师，擅长 SQL 查询和统计分析方法。",
            tools=db_mcp.to_langchain_tools(), verbose=True)
        ops_engineer = Agent(role="运维工程师", goal="检查系统健康状态和部署情况",
            backstory="你是一位资深 SRE。", tools=ops_mcp.to_langchain_tools(), verbose=True)
        report_writer = Agent(role="报告撰写人", goal="整合数据和运维信息生成专业报告",
            backstory="你擅长将技术数据转化为管理层可读的商业报告。", tools=[], verbose=True)
        extract_data = Task(description="提取技术部近 30 天提交和审查数据", agent=data_analyst,
            expected_output="结构化数据表：提交数、审查通过率、活跃度排名")
        check_infra = Task(description="检查核心服务健康状态和部署统计", agent=ops_engineer,
            expected_output="基础设施健康报告")
        generate_report = Task(description="整合分析报告和运维报告生成月度报告", agent=report_writer,
            expected_output="Markdown 格式月度技术报告", context=[extract_data, check_infra])
        crew = Crew(agents=[data_analyst, ops_engineer, report_writer],
            tasks=[extract_data, check_infra, generate_report], process=Process.sequential, verbose=True)
        return crew.kickoff()
    finally:
        await db_mcp.close(); await ops_mcp.close()

if __name__ == "__main__":
    print(asyncio.run(build_crewai_team()))
```

### 3.2.5 OpenAI Agents SDK + MCP 集成

OpenAI Agents SDK 于 2025 年正式发布，`handoff`（交接）机制天然契合 MCP 工具接入。

```python
# openai_agents_mcp.py —— OpenAI Agents SDK + MCP
# 依赖: pip install openai-agents mcp
import asyncio
from agents import Agent, Runner, function_tool, handoff
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPToolBridge:
    """将 MCP 工具桥接到 OpenAI Agents SDK function_tool"""
    def __init__(self):
        self._session: ClientSession | None = None
        self._tools = []

    async def connect(self, command: list[str]):
        params = StdioServerParameters(command=command[0], args=command[1:])
        read, write = await stdio_client(params).__aenter__()
        self._session = ClientSession(read, write)
        await self._session.initialize()
        result = await self._session.list_tools()
        self._tools = result.tools

    def to_openai_tools(self):
        openai_tools = []
        for t in self._tools:
            t_name, t_desc = t.name, t.description
            @function_tool(name_override=t_name, description_override=t_desc or "")
            async def tool_func(**kwargs, _name=t_name, _session=self._session):
                result = await _session.call_tool(_name, arguments=kwargs)
                return "\n".join([c.text for c in result.content if hasattr(c, "text")])
            openai_tools.append(tool_func)
        return openai_tools


async def build_openai_agent_team():
    db_bridge = MCPToolBridge(); ops_bridge = MCPToolBridge()
    await db_bridge.connect(["python", "-m", "db_explorer.server"])
    await ops_bridge.connect(["python", "-m", "ops_assistant.server"])

    data_agent = Agent(name="DataAnalyst", instructions="你是数据分析专家。使用工具提取和分析数据。",
        tools=db_bridge.to_openai_tools(), model="gpt-4o")
    ops_agent = Agent(name="OpsEngineer", instructions="你是资深 SRE。检查服务状态和部署指标。",
        tools=ops_bridge.to_openai_tools(), model="gpt-4o")
    report_agent = Agent(name="ReportWriter", instructions="你是报告专家。基于数据生成综合性月度技术报告。",
        tools=[], model="gpt-4o")

    orchestrator = Agent(name="Orchestrator",
        instructions="你是协调器。1. handoff DataAnalyst 获取数据 2. handoff OpsEngineer 获取运维 3. handoff ReportWriter 生成报告",
        handoffs=[
            handoff(data_agent, tool_name_override="delegate_to_analyst",
                    tool_description_override="委派数据分析任务"),
            handoff(ops_agent, tool_name_override="delegate_to_ops",
                    tool_description_override="委派运维检查任务"),
            handoff(report_agent, tool_name_override="delegate_to_writer",
                    tool_description_override="委派报告撰写任务"),
        ], model="gpt-4o")

    result = await Runner.run(orchestrator, "请生成技术部本月度综合报告")
    return result.final_output

if __name__ == "__main__":
    print(asyncio.run(build_openai_agent_team()))
```

| Handoff (OpenAI) vs Graph (LangGraph) | 编程模型 | 控制粒度 | 与 MCP 关系 |
|---|---|---|---|
| OpenAI Handoff | LLM 自主决定交接 | Agent 级别 | function_tool 接入 |
| LangGraph StateGraph | 开发者显式定义边 | 节点级别 | ToolNode 接入 |

### 3.3 大厂 MCP 应用场景解析

### 3.3 大厂 MCP 应用场景解析

#### 3.3.1 Cloudflare —— 企业可观测性

```
Cloudflare MCP 应用场景：

┌─────────────────────────────────────────────────────────┐
│                  AI Agent (SRE 助手)                     │
└──────────────────────┬──────────────────────────────────┘
                       │ MCP Protocol
┌──────────────────────▼──────────────────────────────────┐
│              MCP Gateway (统一入口)                       │
└──────────────────────┬──────────────────────────────────┘
        ┌──────────────┼──────────────┬──────────────┐
        ▼              ▼              ▼              ▼
   ┌─────────┐   ┌─────────┐   ┌─────────┐   ┌──────────┐
   │ 日志 MCP │   │ 指标 MCP │   │ 链路 MCP │   │ 告警 MCP │
   │ Server  │   │ Server  │   │ Server  │   │ Server   │
   │(ELK)    │   │(Prometh)│   │(Jaeger) │   │(PagerDuty│
   └─────────┘   └─────────┘   └─────────┘   └──────────┘

关键价值：
  AI Agent 通过 MCP 同时查询多个异构监控系统，
  自动做关联分析（日志中的错误 ↔ 指标中的异常 ↔ 链路中的慢请求），
  实现跨系统的根因定位。
```

#### 3.3.2 蚂蚁数科 —— 金融 MCP 服务广场

```
蚂蚁数科的金融 MCP 生态：

┌─────────────────────────────────────────────────────────┐
│              MCP 服务广场 (Service Marketplace)           │
│                                                         │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐        │
│  │ 基金投顾    │  │ 股票分析    │  │ 风险评估    │        │
│  │ MCP Server │  │ MCP Server │  │ MCP Server │        │
│  │            │  │            │  │            │        │
│  │ - 基金净值  │  │ - K线数据  │  │ - 信用评分  │        │
│  │ - 持仓查询  │  │ - 技术指标  │  │ - 风险敞口  │        │
│  │ - 收益计算  │  │ - 研报摘要  │  │ - 合规校验  │        │
│  └────────────┘  └────────────┘  └────────────┘        │
│                                                         │
│  特色：国内首个金融领域 MCP 广场                         │
│  核心价值：金融数据通过 MCP 标准化接入，AI Agent 合规使用  │
└─────────────────────────────────────────────────────────┘
```

#### 3.3.3 Hugging Face —— AI 模型中心

```
Hugging Face MCP Server：

┌─────────────────────────────────────────────────────────────┐
│              用户 / AI 应用                                  │
│  "帮我找一个适合中文情感分析的模型，看看它的使用示例"         │
└──────────────────────┬──────────────────────────────────────┘
                       │ MCP Protocol
┌──────────────────────▼──────────────────────────────────────┐
│          Hugging Face MCP Server                             │
│                                                             │
│  Tools:                                                     │
│  ├── search_models(query, task, language)                   │
│  ├── get_model_info(model_id)                               │
│  ├── get_model_readme(model_id)                             │
│  ├── search_datasets(query)                                 │
│  └── recommend_models(use_case)                             │
│                                                             │
│  连接：Hugging Face Hub API                                  │
│  覆盖：数千个 AI 应用和模型                                    │
└─────────────────────────────────────────────────────────────┘
```

#### 3.3.4 国内生态汇总

| 厂商 | 产品 | 特色能力 | MCP 定位 |
|------|------|----------|----------|
| **百度千帆** | MCP 广场 | 搜索、地图、OCR 等百度核心能力 | "模型-MCP-应用"三层体系 |
| **阿里云百炼** | MCP 服务 | 插件市场、自定义插件接入 | 大模型平台的工具扩展机制 |
| **腾讯知识引擎** | MCP 插件 | 位置服务、微信读书、自定义插件 | 知识引擎的能力扩展 |
| **蚂蚁数科** | 金融 MCP 广场 | 基金投顾、股票分析、风控 | 国内首个垂直领域 MCP 生态 |
| **HubSpot** | CRM MCP Server | 客户数据查询、营销活动管理 | 让 AI 操作 CRM 系统 |

---

### 3.4 多 Agent 系统的评测、监控与调试

#### 3.4.1 评测指标体系

| 指标 | 定义 | 计算 | 目标 |
|------|------|------|------|
| **任务完成率** | 端到端成功完成的任务比例 | `success / total_tasks` | > 90% |
| **首轮正确率** | 无需人工修正即完成的比例 | `correct / total` | > 70% |
| **平均工具调用数** | 每任务 tools/call 次数 | `total_calls / tasks` | < 5（越少越好） |
| **Token 效率** | 每任务 Token 总消耗 | `total_tokens / tasks` | 持续优化趋势 |
| **端到端延迟 P95** | 用户请求到最终回复 | p95 分位值 | < 30s |
| **Agent 交接次数** | 任务在 Agent 间传递的次数 | 每任务均值 | < 3 |

#### 3.4.2 调用链追踪（TraceSpan）

```python
import uuid, time, json, logging
from contextvars import ContextVar

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_parent_span: ContextVar[str] = ContextVar("parent_span", default="")

class TraceSpan:
    """一次工具调用或 Agent 推理的 Span"""
    def __init__(self, operation: str, agent: str, tool: str = ""):
        self.span_id = uuid.uuid4().hex[:8]
        self.trace_id = _trace_id.get() or uuid.uuid4().hex[:16]
        self.operation = operation  # "tool_call" | "agent_reasoning" | "handoff"
        self.agent = agent; self.tool = tool
        self.start = time.perf_counter(); self.parent = _parent_span.get()

    def finish(self, output: str = "", error: str = None):
        duration = (time.perf_counter() - self.start) * 1000
        logger.info(json.dumps({"trace_id": self.trace_id, "span_id": self.span_id,
            "parent": self.parent, "operation": self.operation, "agent": self.agent,
            "tool": self.tool, "duration_ms": round(duration, 2), "error": error}))

    def __enter__(self): _parent_span.set(self.span_id); return self
    def __exit__(self, *a): _parent_span.set(self.parent); self.finish()


# 使用：with TraceSpan("tool_call", "DataAnalyst", "search_employees"): ...
```

#### 3.4.3 异常定位 5 步法

```
Step 1: 确定异常 Agent——Trace 日志中最早出现 error 的 Span
Step 2: 还原现场——提取该 Agent 完整输入，隔离复现
Step 3: 检查工具输出——MCP 工具的 LLM 友好错误是否被误读？
Step 4: 检查 Prompt 注入——上游输出是否含 [系统提示] 等隐藏指令？
Step 5: 检查 Handoff 边界——交接时上下文是否完整？工具权限是否充足？
```

### 3.5 企业落地 MCP 的实际挑战与应对策略

#### 3.5.1 组织层面

| 挑战 | 应对 |
|------|------|
| **安全审批**（安全团队对"AI 直接调生产工具"的谨慎） | 分阶段：先只读工具→灰度写操作→建立自动化安全审查 |
| **基础设施适配**（内网/自签证书/不支持 HTTP/2） | 先用 stdio 试点→逐步升级；提供 MCP-to-Legacy 适配网关 |
| **跨团队协作**（工具归属团队不愿维护"为别人的 AI"服务） | 内部 MCP 工具市场 + OKR 关联 + 内部开源贡献榜 |
| **标准选型争议**（MCP vs OpenAI FC vs 自研） | 小团队 POC 用数据说话："MCP 方案节省 X 人天/月" |

#### 3.5.2 REST API → MCP 迁移三阶段

```
Phase 1（1-3 月）：并行期
  · 新建 MCP Server 包装现有 REST API（薄封装过渡）
  · 新旧协议同时提供，监控迁移比例

Phase 2（3-6 月）：优化期
  · 重构为领域优化的复合工具，消除 N+1
  · 废弃不再被调用的 REST API 端点

Phase 3（6+ 月）：治理期
  · MCP 成为新工具唯一接入标准
  · 旧 REST API 仅安全修复 → 制定下线时间表
```

#### 3.5.3 人才缺口（2025 年估算）

```
了解概念 ~50K → 能写工具 ~10K → 有生产经验 ~2K → 能设计平台 ~500 → 协议贡献者 ~50
```

应对：内部用本教材 7 模块做培训 + 面试考查复合工具/跨 Server 事务/安全建模 + 鼓励社区贡献。

---

## 四、底层原理——A2A 协议与工具发现机制

### 4.1 A2A 协议核心概念（深化版）

A2A（Agent-to-Agent Protocol）由 Google 于 2025 年 4 月提出，同样基于 JSON-RPC 2.0。

#### 4.1.1 Task 生命周期状态机

```
                 ┌─────────┐
                 │ pending │ ← Agent Card 匹配后，任务进入待分配
                 └────┬────┘
                      │ assign
                 ┌────▼────┐
                 │ working │ ← Agent 正在执行任务
                 └────┬────┘
                      │
           ┌──────────┼──────────┐
           ▼          ▼          ▼
     ┌─────────┐ ┌──────┐ ┌──────────┐
     │completed│ │failed│ │cancelled │
     └─────────┘ └──┬───┘ └──────────┘
                    │
               ┌────▼────┐
               │  retry  │ ← 可重试错误 → 回到 working（有最大次数限制）
               └─────────┘
```

#### 4.1.2 Agent Card——Agent 能力声明

Agent Card 是 A2A 中 Agent 向其他 Agent 声明自身能力的元数据文件，类似于 MCP 的 `tools/list` 但面向 Agent 间协作。

```json
{
    "name": "DataAnalystAgent",
    "description": "数据分析专家，擅长 SQL 查询和统计分析",
    "url": "https://agents.internal/data-analyst",
    "capabilities": { "streaming": true, "pushNotifications": false },
    "skills": [{
        "id": "sql_analysis",
        "name": "SQL 数据分析",
        "description": "对结构化数据库执行复杂 SQL 查询和分析",
        "tags": ["sql", "analytics"],
        "inputSchema": { "type": "object", "properties": { "query_description": { "type": "string" } } },
        "outputSchema": { "type": "object", "properties": { "analysis_report": { "type": "string" }, "data": { "type": "array" } } }
    }],
    "security": { "authentication": "oauth2" }
}
```

| Agent Card vs MCP tools/list | Agent Card | tools/list |
|---|---|---|
| 服务对象 | 其他 Agent | LLM / Host |
| 声明粒度 | Skill 级别（粗粒度） | Tool 级别（细粒度） |
| 包含内容 | Skill + 端点 URL + 安全信息 | 工具名 + 描述 + JSON Schema |

### 4.2 MCP 与 A2A 的协同——完整代码演示与边界决策

```python
# mcp_a2a_orchestration.py —— MCP + A2A 协同编排
"""
场景：用户说"分析技术部的代码质量并生成改进建议"

  Step 1: Orchestrator 解析意图 → 需要 (a) 数据获取 (b) 代码分析
  Step 2a: 数据获取 → MCP（tools/call: search_employees + get_employee_commits）
  Step 2b: 代码分析 → A2A（委托给 CodeReviewAgent，内部通过 MCP 使用工具）
  Step 3: 合并 MCP 结果 + A2A 结果 → LLM 生成最终回复

关键边界决策：
  · 确定性的、即时返回的数据操作 → MCP
  · 需要专业领域推理、不确定步骤的任务 → A2A
"""

import asyncio, uuid, httpx
from dataclasses import dataclass
from mcp import ClientSession

@dataclass
class A2ATaskRequest:
    task_id: str; skill_id: str; input_data: dict
    callback_url: str; max_retries: int = 3

class OrchestratorAgent:
    def __init__(self, mcp_session: ClientSession, a2a_registry_url: str):
        self.mcp = mcp_session        # MCP 连接（工具调用）
        self.registry = a2a_registry_url  # A2A 注册中心

    async def execute(self, request: str) -> str:
        intent = await self._analyze_intent(request)
        tasks = []

        # ★ MCP 路径：数据获取（确定、即时）
        if intent["needs_data"]:
            data = await self.mcp.call_tool("get_department_overview",
                {"department_name": intent["department"]})
            tasks.append(("data", data))

        # ★ A2A 路径：代码分析（需要专业 Agent）
        if intent["needs_code_review"]:
            agents = await httpx.get(f"{self.registry}/agents?skill=code_review")
            code_agent = agents.json()[0]
            a2a_result = await httpx.post(f"{code_agent['url']}/tasks",
                json=A2ATaskRequest(task_id=str(uuid.uuid4()),
                    skill_id="code_review", input_data={"repo": intent["repo"]},
                    callback_url="https://orchestrator/callback").__dict__)
            tasks.append(("code_review", a2a_result.json()))

        return await self._synthesize(tasks)
```

**MCP vs A2A 边界决策树**：

```
这是"调用一个工具"还是"委托一个任务"？

├── "查北京天气"                    → MCP（确定、即时、参数明确）
├── "部署 v2.1.0 到 staging"       → MCP（步骤确定、参数明确）
├── "分析技术部代码质量"             → A2A（需要代码领域专业知识）
├── "生成月度财务报告"               → A2A（需要财务 Agent 推理）
└── "找关于 Q2 预算的所有信息"       → 混合：MCP 跨系统搜索 + A2A 委托分析 Agent 解读

原则：如果你能明确说出操作的每一步 → MCP
      如果操作需要"专家判断"且步骤不确定 → A2A
```

### 4.3 工具发现与动态注册机制

```
传统的 Function Calling 工具发现：
  ┌─────────┐
  │ 开发者   │ ──→ 在代码中硬编码工具列表
  │         │ ──→ 需要重启应用才能更新
  └─────────┘

MCP 的工具发现：
  ┌─────────┐
  │ 开发者   │ ──→ 部署 MCP Server
  └─────────┘
       │
  ┌────▼────────────────────────────────────┐
  │  MCP Server 启动                         │
  │  → Client 连接 Server                    │
  │  → Client 调用 tools/list                 │
  │  → Server 返回完整工具列表（含 Schema）    │
  │  → Client 缓存工具定义                    │
  │  → 运行时通过 tools/list_changed 通知更新 │
  └─────────────────────────────────────────┘

动态注册的优势：
  1. AI 应用启动时自动发现所有可用工具
  2. 新增工具无需修改 AI 应用代码
  3. 工具 Schema 不在对话上下文中（省 token）
  4. 支持运行时热更新工具列表
```

**社区生态数据**：截至 2025 年，社区已贡献超过 **1,000 个** MCP Server，覆盖数据库、云服务、开发工具、办公协作等数十个领域。OpenAI 和 Google 也已宣布支持 MCP 协议。

---

## 五、企业级最佳实践

### 5.1 框架选型决策树

```
                    你的场景是什么？
                          │
         ┌────────────────┼────────────────┐
         ▼                ▼                ▼
   简单的顺序流程    复杂的多步推理    需要动态任务分配
    (A→B→C)        (条件分支+循环)    (多个独立 Agent)
         │                │                │
         ▼                ▼                ▼
     CrewAI           LangGraph         AutoGen
     (最简单)         (最灵活)          (微软生态)
         │                │                │
         └────────────────┼────────────────┘
                          │
                    都通过 MCP 接入工具
```

### 5.2 多 Agent 设计原则

```
原则 1: 一个 Agent 只做一类事
  ❌ 一个 Agent 既做数据提取又做报告撰写又做代码生成
  ✅ 数据分析 Agent + 报告 Agent + 代码 Agent

原则 2: Agent 之间通过结构化输出传递信息
  ❌ Agent A 返回自然语言文本，Agent B 从文本中再提取数据
  ✅ Agent A 返回 JSON，Agent B 直接用结构化数据

原则 3: 审核 Agent 应该是独立的
  生成 Agent 和审核 Agent 使用不同的系统提示词
  最好使用不同的模型（避免"自产自审"）

原则 4: MCP 工具分配给最内行的 Agent
  数据库工具 → 数据分析 Agent
  部署工具 → 运维 Agent
  不要让报告 Agent 直接操作数据库

原则 5: 控制 Agent 数量
  2-5 个 Agent 是最佳范围
  < 2 个：不如用单 Agent
  > 5 个：协调开销超过分工收益
```

### 5.3 MCP Server 生态发布指南

```
发布一个 MCP Server 到社区的标准步骤：

1. 代码准备
   ├── README.md（安装说明 + 工具列表 + 配置示例）
   ├── LICENSE
   ├── Dockerfile（推荐提供容器镜像）
   └── 完善的 docstring（这是 LLM 的使用手册）

2. 安全审计
   ├── 无硬编码凭证
   ├── 最小权限原则
   ├── 输入校验
   └── 路径白名单（文件系统类 Server）

3. 发布渠道
   ├── GitHub 仓库（开源）
   ├── npm / PyPI 注册（包管理器）
   ├── MCP 官方目录（https://github.com/modelcontextprotocol/servers）
   └── 大厂 MCP 广场（百炼、千帆、知识引擎）

4. 文档要求
   ├── 每个工具的用途和使用场景
   ├── 配置示例（环境变量、参数说明）
   ├── 权限需求说明
   └── 常见问题 FAQ
```

---

## 六、常见面试题

### 框架集成

**Q1: LangGraph 中如何集成 MCP 工具？核心适配做了什么？**

<details>
<summary>参考答案</summary>

核心工作是在 MCP 工具和 LangChain Tool 之间建立**适配层**：

1. 通过 `stdio_client` 或 `streamable_http_client` 连接 MCP Server
2. 调用 `session.initialize()` 完成协议握手
3. 调用 `session.list_tools()` 获取所有工具定义
4. 对每个 MCP Tool，创建一个对应的 LangChain Tool：
   - `name` → 工具名称
   - `description` → 工具描述
   - `func` → 包装 `session.call_tool()` 调用
5. 在 LangGraph 节点中通过 `ToolNode` 或 `bind_tools()` 使用这些工具

关键代码模式：
```python
for mcp_tool in self._session.list_tools():
    @tool(mcp_tool.name, description=mcp_tool.description)
    def wrapper(**kwargs):
        result = await self._session.call_tool(mcp_tool.name, arguments=kwargs)
        return result.content[0].text
```

</details>

---

**Q2: MCP 和 A2A 协议有什么区别？分别在什么场景下使用？**

<details>
<summary>参考答案</summary>

| 维度 | MCP | A2A |
|------|-----|-----|
| 提出者 | Anthropic (2024.11) | Google (2025.04) |
| 解决的问题 | Agent **如何使用**外部工具和数据 | Agent **之间如何**协作 |
| 通信模式 | Client ↔ Server（工具调用） | Agent ↔ Agent（任务委派） |
| 核心概念 | Tools, Resources, Prompts | Task, Artifact, Message |
| 底层协议 | JSON-RPC 2.0 | JSON-RPC 2.0 |

**两者互补**：一个多 Agent 系统中，Agent 之间通过 A2A 协作，每个 Agent 通过 MCP 接入工具。A2A 是横向的（Agent 协作），MCP 是纵向的（工具接入）。

</details>

---

### 大厂场景

**Q3: 请描述一个你了解的 MCP 大厂应用案例，分析其中 MCP 的核心价值。**

<details>
<summary>参考答案</summary>

以 **Cloudflare 企业可观测性**为例：

**场景**：SRE 需要一个 AI Agent 能同时查询日志（ELK）、指标（Prometheus）、链路追踪（Jaeger）三个异构监控系统，自动做关联分析。

**传统方式的痛点**：三个系统有各自的 API，SRE 需要手动切换、手动关联。

**MCP 方案**：
- 为每个监控系统构建一个 MCP Server
- AI Agent 通过 MCP 统一调用三个系统
- Agent 自动做关联分析："日志中的这个错误时间点，对应指标的 CPU 飙升和链路中的 DB 超时"

**核心价值**：
1. 统一接入标准：不同监控系统用相同的 MCP 协议暴露能力
2. AI 驱动的关联分析：Agent 不需要预先知道三套 API 的差异
3. 工具可扩展：新增监控系统只需新建一个 MCP Server

</details>

---

**Q4: 百度千帆的"模型-MCP-应用"三层体系是怎样的？**

<details>
<summary>参考答案</summary>

```
┌─────────────────────────────────────┐
│        应用层 (Application)          │
│  智能客服 │ 代码助手 │ 数据分析 │ ... │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│        MCP 层 (协议标准)              │
│  MCP Server 市场                    │
│  ├── 百度搜索 MCP                   │
│  ├── 百度地图 MCP                   │
│  ├── OCR 识别 MCP                   │
│  └── 第三方 MCP Server             │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│        模型层 (Model)                │
│  文心一言 · 千帆大模型平台           │
└─────────────────────────────────────┘
```

**核心策略**：
1. 百度将核心能力（搜索、地图、OCR）封装为 MCP Server
2. 开发者可以在千帆平台自由选择和组合这些 MCP Server
3. 不同 AI 应用共享同一套 MCP 工具生态
4. 第三方开发者也可以贡献 MCP Server 到广场

</details>

---

### 设计理解

**Q5: MCPToolAdapter.to_langchain_tools() 中的闭包陷阱是什么？如何修复？**

<details>
<summary>参考答案</summary>

Python 闭包延迟绑定：`for mcp_tool in tools` 中所有内部函数引用同一个循环变量，循环结束后指向最后一个元素 → 所有 wrapper 调用最后一个工具。修复：工厂函数 `make_wrapper(name, desc)` 利用默认参数在调用时求值来"冻结"当前值。这是 Python 面试经典考点。

</details>

---

**Q5.5: 多 Agent 系统中，MCP 工具应该如何分配给不同的 Agent？**

<details>
<summary>参考答案</summary>

**分配原则：**

1. **按专业领域分配**：数据库工具 → 数据分析 Agent，部署工具 → 运维 Agent
2. **最小权限原则**：每个 Agent 只获得完成其任务所需的最少工具
3. **避免工具重叠**：两个 Agent 不应拥有相同的破坏性工具（如部署、删除）
4. **读工具可共享**：查询类工具可以分配给多个 Agent

**反例：** 不要给"报告生成 Agent"分配数据库写操作工具——它只应该读数据做分析，不应直接修改数据。

</details>

---

**Q6: 什么是 MCP 的"动态工具发现"？相比 Function Calling 的静态定义有什么优势？**

<details>
<summary>参考答案</summary>

**动态工具发现**：MCP Client 通过 `tools/list` 在运行时从 Server 获取可用工具列表，Server 也可以通过 `tools/list_changed` 通知 Client 列表已更新。

**优势对比：**

| 维度 | Function Calling（静态） | MCP（动态） |
|------|-------------------------|------------|
| 工具定义位置 | 编译时硬编码在代码中 | 运行时从 Server 获取 |
| 新增工具 | 需要修改应用代码 + 重新部署 | 部署新 MCP Server 即可 |
| Schema 传输 | 每次对话都携带 | 一次获取，缓存复用 |
| Token 消耗 | Schema 计入 prompt token | 不计入对话上下文 |
| 工具热更新 | 不支持 | 支持（tools/list_changed） |

</details>

---

**Q7: OpenAI Agents SDK 的 Handoff 和 LangGraph 的 StateGraph 有什么区别？**

<details>
<summary>参考答案</summary>

| 维度 | Handoff | StateGraph |
|------|---------|------------|
| 控制者 | LLM 自主决定何时交接、交给谁 | 开发者显式定义节点和边 |
| 可预测性 | 低（LLM 可能选错 Agent） | 高（确定性路径） |
| 适合场景 | 灵活任务委派、探索性任务 | 确定性工作流、审批流程 |

步骤固定且需审计跟踪 → LangGraph。任务分配灵活且 LLM 判断力好 → OpenAI Handoff。

</details>

---

**Q8: 如何对多 Agent 系统进行评测和调试？**

<details>
<summary>参考答案</summary>

**评测五指标**：任务完成率（>90%）、首轮正确率（>70%）、平均工具调用数（<5）、Token 效率、端到端 P95 延迟（<30s）。

**调试五步法**：① Trace 日志找到最早 error 的 Span → 确定异常 Agent ② 还原输入，隔离复现 ③ 检查 MCP 工具返回值是否被 LLM 误读 ④ 检查上游输出是否含注入指令 ⑤ 检查 Handoff 上下文完整性和工具权限。

**TraceSpan**：协程安全的上下文变量 + span_id/parent_span_id 构建调用树，JSON 日志结构化输出。

</details>

---

**Q9: MCP 和 A2A 的边界如何划分？**

<details>
<summary>参考答案</summary>

**决策原则**：能明确说出操作的每一步 → MCP（确定、即时、参数明确）。需要"专家判断"且步骤不确定 → A2A（需要专业 Agent 推理）。

"查天气"/"部署" → MCP。"分析代码质量"/"生成财务报告" → A2A。复杂任务可混合：MCP 跨系统搜索 + A2A 委托分析。

</details>

---

## 附录

### 多 Agent 框架对比速查表

| 框架 | 语言 | 编程模型 | 适用场景 | MCP 集成难度 |
|------|------|----------|----------|-------------|
| LangGraph | Python/JS | 有向图 | 复杂多步推理、条件分支 | 低（工具适配器） |
| CrewAI | Python | 角色扮演 | 顺序任务链 | 低（Tool 格式兼容） |
| AutoGen | Python | 对话驱动 | 微软生态、多人对话 | 中（需自定义适配） |
| OpenAI Swarm | Python | 轻量路由 | 简单 Agent 切换 | 低（Function 格式兼容） |

### 推荐阅读

- [LangGraph 官方文档](https://langchain-ai.github.io/langgraph/)
- [CrewAI 官方文档](https://docs.crewai.com/)
- [Google A2A 协议介绍](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)
- [Hugging Face MCP Server](https://huggingface.co/spaces/huggingface/mcp-server)
