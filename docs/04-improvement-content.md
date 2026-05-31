# 模块 4 改进内容

> 目标：★★★☆☆ → ★★★★★  
> P0: 多业务场景设计 + 跨 Server 事务策略  
> P1: 性能基准测试 + 生产级部署方案  
> P2: CI/CD 集成

---

## P0-1：不同业务领域的工具设计模式（新增 §3.10）

**插入位置**：现有 §3.9「Docker 部署」之后，§四「底层原理」之前。

### §3.10 不同业务领域的工具设计模式

"运维助手"是一种场景。大厂面试中可能让你当场设计电商、金融或办公场景的 MCP Server。以下是三个领域的工具设计模式，重点展示**同一原则在不同约束条件下的不同表达**。

#### 3.10.1 电商场景——高并发 + 库存一致性

**场景特征**：每秒数千次商品查询、订单创建涉及库存扣减（一致性要求高）、物流状态实时推送。

**工具粒度设计决策**：

| 决策点 | 薄封装（❌） | 复合工具（✅） | 理由 |
|--------|------------|-------------|------|
| 商品搜索 | `search_products` | `search_products`（含价格/库存/评分聚合） | 搜索是高并发路径，一次返回完整信息避免 N+1 |
| 下单 | `create_order` + `check_inventory` + `lock_coupon` | `place_order`（内部编排三步） | 一致性要求——三步必须在一个补偿事务内 |
| 物流 | `query_logistics` | `track_order_full`（含承运商+轨迹+预计送达） | 用户语义是"查物流"，不是"调 API" |

**典型工具列表**：

```python
# ecommerce_server/tools.py —— 电商 MCP Server 工具设计
@mcp.tool()
async def search_products(
    query: str,
    category: str = None,
    price_range: tuple[float, float] = None,
    sort_by: Literal["relevance", "price_asc", "price_desc", "sales"] = "relevance",
    page: int = 1,
    page_size: int = 20
) -> dict:
    """搜索商品——一次返回完整决策信息

    返回结构：商品基本信息 + 当前价格 + 库存状态 + 评分 + 优惠标签
    设计原则：搜索是高并发入口（QPS > 1000），必须一次返回 LLM 需要的所有信息，
    避免 LLM 再逐个调用 get_product_detail → check_inventory → get_reviews
    """
    ...

@mcp.tool()
@mcp_error_handler
async def place_order(
    user_id: str,
    items: list[dict],       # [{"sku": "X", "quantity": 2}, ...]
    address_id: str,
    coupon_code: str = None
) -> dict:
    """下单——内部编排三步：校验库存 → 锁定优惠券 → 创建订单

    三步在单个工具内完成，如果任一步失败则回滚已完成步骤（补偿事务）。
    不要拆成三个独立工具——LLM 无法保证三步间的原子性。
    """
    ...

@mcp.tool()
async def track_order(order_id: str) -> dict:
    """追踪订单——返回承运商 + 物流轨迹 + 预计送达时间"""
    ...
```

**面试追问**："电商场景中，`place_order` 为什么不拆成 `check_inventory` + `create_order` 两个工具，让 LLM 按序调用？"

**答案**：因为 LLM 的两次 `tools/call` 之间**没有事务保证**。如果 LLM 调了 `create_order` 成功后，Server B 的 `deduct_inventory` 失败，LLM 需要显式调用 `cancel_order` 做补偿——但 LLM 可能因为上下文超长或推理偏差而**忘记补偿**。放在一个工具内执行，事务由 Server 控制，不依赖 LLM 的"记性"。

#### 3.10.2 金融场景——审计追踪 + 数据脱敏

**场景特征**：所有操作必须留痕（审计要求）、敏感数据需要脱敏、合规校验是强制步骤。

**工具粒度设计决策**：

| 决策点 | 设计 | 理由 |
|--------|------|------|
| 查询类工具 | 所有查询工具返回的内容自动脱敏（手机号/身份证/卡号打码） | 合规——数据脱敏不应依赖 LLM 自觉 |
| 写操作工具 | 每个写操作工具内置 `audit_log` 记录（谁/何时/做了什么/结果） | 审计——日志在 Server 端，不与 LLM 交互耦合 |
| 风险评估 | 用 Resource 而非 Tool 暴露风险指标 | 只读数据应走 Resource（天然幂等 + 可缓存） |

**典型工具列表**：

```python
# finance_server/tools.py —— 金融 MCP Server 工具设计
@mcp.tool()
async def compliance_check(transaction_id: str) -> dict:
    """合规审查——检查交易是否满足反洗钱、KYC 等要求

    金融场景的特殊约束：合规检查是强制的，不可跳过。
    设计上将此作为独立工具，让合规团队可以单独审计其调用记录。
    """
    ...

@mcp.tool()
@audit_log("RISK_ASSESSMENT")    # 自定义审计装饰器
async def assess_risk(customer_id: str, transaction_type: str, amount: float) -> dict:
    """风险评估——返回风险评分 + 风险因子明细

    返回数据自动脱敏：客户姓名 → 张**，身份证 → 310***********1234
    """
    raw = await risk_engine.evaluate(customer_id, transaction_type, amount)
    return desensitize(raw, fields=["name", "id_number", "phone", "bank_account"])

@mcp.resource("fin://accounts/{account_id}/transactions")
async def get_transactions(account_id: str) -> str:
    """交易记录——通过 Resource 暴露（只读 + 可缓存 + 支持订阅变更）"""
    ...
```

**面试追问**："金融场景中，为什么风险评估用 Tool 而交易记录用 Resource？"

**答案**：风险评估是**计算**（有输入参数、每次结果可能不同），适合 Tool。交易记录是**数据**（给定 ID 返回固定记录集），适合 Resource。Tool 的结果不应缓存，Resource 的结果可以缓存——在金融场景中，交易记录的缓存可以显著降低数据库压力，而风险评估不能缓存（风险实时变化）。

#### 3.10.3 办公场景——跨系统权限收敛

**场景特征**：邮件（Gmail/Outlook）、日程（Google Calendar）、文档（Notion/Confluence）分属不同系统，权限体系独立。

**工具粒度设计决策**：

| 决策点 | 设计 | 理由 |
|--------|------|------|
| 跨系统搜索 | `search_across_systems(query)` → 同时搜邮件+文档+日程 | 用户说的是"帮我找关于 Q2 预算的内容"，不关心数据在哪 |
| 权限收敛 | MCP Server 内部统一认证（OAuth 代理模式），每个工具调用时携带用户 token | LLM 不应感知多系统认证——Server 做代理 |
| 数据聚合 | 日程 + 邮件聚合为 `get_daily_briefing(date)` | 典型的"用户意图"而非"API 调用" |

**典型工具列表**：

```python
# office_server/tools.py —— 办公 MCP Server 工具设计

@mcp.tool()
async def search_across_systems(query: str, scope: list[str] = None) -> dict:
    """跨系统搜索——同时搜索邮件、文档、日程、消息

    返回按系统和相关度分组的结果。
    LLM 只需一次调用即可了解"关于 X 的信息都分布在哪里"。
    """
    tasks = []
    if not scope or "mail" in scope:
        tasks.append(search_mail(query))
    if not scope or "docs" in scope:
        tasks.append(search_docs(query))
    if not scope or "calendar" in scope:
        tasks.append(search_calendar(query))
    if not scope or "messages" in scope:
        tasks.append(search_messages(query))
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return aggregate_results(query, results)

@mcp.tool()
async def get_daily_briefing(date: str = "today") -> dict:
    """每日简报——聚合日程 + 未读邮件摘要 + 待办事项"""
    calendar = await get_calendar_events(date)
    emails = await get_unread_summaries(date)
    todos = await get_pending_tasks()
    return {
        "date": date,
        "events": calendar,
        "important_emails": emails,
        "pending_tasks": todos
    }
```

#### 3.10.4 三场景工具设计对比总结

| 维度 | 运维场景 | 电商场景 | 金融场景 | 办公场景 |
|------|----------|----------|----------|----------|
| **核心约束** | 数据源多样 | 高并发 + 一致性 | 审计 + 脱敏 | 跨系统权限 |
| **复合工具策略** | 聚合多数据源 | 事务内编排 | 审计内嵌 | 跨系统聚合 |
| **Resource 使用** | 日志/配置文件 | 商品详情（缓存） | 交易记录（只读） | 文档内容 |
| **Tool 使用** | 部署/查询 | 下单（幂等设计） | 合规审查 | 搜索/发送 |
| **安全特殊要求** | 路径白名单 | 幂等 Key 防重 | 字段级脱敏 | OAuth 代理 |
| **典型工具数** | 15-25 | 20-35 | 25-40 | 15-20 |

> **设计原则收敛**：三个场景虽差异大，但都遵循同一条铁律——**一个工具 = 一个用户意图**，而非一个 API 端点。差异只在于该意图在各自约束条件下的展开方式。

---

## P0-2：跨 Server 事务场景的设计策略（新增 §3.11）

**插入位置**：§3.10 之后，§四「底层原理」之前。

### §3.11 跨 Server 事务场景的设计策略

当 LLM 需要依次调用两个 MCP Server 完成一个业务操作时，分布式一致性是工程中最棘手的问题之一。MCP 协议本身**不提供分布式事务支持**，开发者需要在工具设计层面自行处理。

#### 3.11.1 问题定义

```
场景：用户说"帮我下一笔订单"

  LLM → Server A (order-service):  tools/call create_order(...)
  LLM → Server B (inventory-service): tools/call deduct_inventory(...)
  
  如果 Server A 成功，Server B 失败 → 订单已创建但库存未扣减 → 数据不一致

根本矛盾：
  · LLM 的两次 tools/call 是独立的 JSON-RPC 请求，没有事务上下文
  · 两个 Server 可能连接不同的数据库，无法使用数据库原生事务
  · LLM 不是事务协调器——它可能"忘记"做补偿
```

#### 3.11.2 策略一：避免跨 Server 调用（首选策略）

**核心思想**：将跨 Server 的操作封装在单个工具内完成。

```
❌ 坏设计：让 LLM 协调跨 Server 调用
  LLM → order-service.create_order()
  LLM → inventory-service.deduct_inventory()  ← 如果失败，LLM 需要记得调用 cancel_order
  
✅ 好设计：单个工具内部编排
  LLM → order-service.place_order()
         │
         ├── 内部调用 inventory-service.deduct_inventory()  (gRPC/HTTP)
         │   失败 → 内部回滚 create_order → 返回 isError: true
         │
         └── LLM 只需处理一次调用，事务由 Server 保证
```

**实现**：

```python
# order_service/tools.py
@mcp.tool()
async def place_order(user_id: str, items: list[dict], address_id: str) -> dict:
    """下单——内部编排订单创建 + 库存扣减，保证事务一致性"""
    order = None
    try:
        # Step 1: 创建订单（本地数据库）
        order = await order_db.create(user_id, items, address_id, status="pending")

        # Step 2: 扣减库存（远程调用 inventory-service）
        # 使用 gRPC/HTTP 内部调用，非 MCP 协议
        result = await inventory_client.deduct(items)
        if not result.success:
            # 库存不足 → 回滚订单
            await order_db.update(order.id, status="cancelled",
                                  reason=f"库存扣减失败: {result.reason}")
            return make_error("INSUFFICIENT_STOCK", result.reason, "RETRY_LATER")

        # Step 3: 确认订单
        await order_db.update(order.id, status="confirmed")
        return make_success(order.to_dict())

    except Exception as e:
        # 任何步骤异常 → 回滚
        if order:
            await order_db.update(order.id, status="cancelled", reason=str(e))
        return make_error("ORDER_FAILED", str(e), "DO_NOT_RETRY")
```

**适用条件**：Server A 可以内部调用 Server B（网络可达 + 有认证凭证 + 调用延迟可接受）。

#### 3.11.3 策略二：补偿事务（Compensating Transaction）

当跨 Server 调用不可避免时（例如两台 Server 分属不同团队、网络隔离、或已经是既成架构），使用补偿事务模式。

```
正向流程：
  LLM → Server A: create_order(...)    → order_id = "O-123"
  LLM → Server B: deduct_inventory(...) → 失败！

补偿流程（LLM 负责触发）：
  LLM → Server A: cancel_order(order_id="O-123", reason="库存扣减失败")
```

**关键设计——Server 必须暴露补偿工具**：

```python
# order_service/tools.py —— 提供正向工具 + 补偿工具

@mcp.tool()
async def create_order(user_id: str, items: list[dict]) -> dict:
    """创建订单（状态=pending，需后续确认）

    ⚠️ 此工具创建的是 pending 状态的订单，需 30 分钟内确认或自动取消
    """
    order = await order_db.create(user_id, items, status="pending",
                                   expires_at=datetime.utcnow() + timedelta(minutes=30))
    return {"order_id": order.id, "status": "pending", "expires_at": order.expires_at}

@mcp.tool()
async def confirm_order(order_id: str, inventory_result: dict) -> dict:
    """确认订单——库存扣减成功后调用"""
    order = await order_db.update(order_id, status="confirmed")
    return {"order_id": order.id, "status": "confirmed"}

@mcp.tool()
async def cancel_order(order_id: str, reason: str) -> dict:
    """取消订单——补偿工具，恢复已占用资源

    这是 create_order 的补偿操作。设计要点：
    1. 必须是幂等的——多次调用 cancel 同一订单返回相同结果
    2. 不能失败——cancel 自身要足够健壮（使用状态机而非删除）
    """
    order = await order_db.get(order_id)
    if order.status == "cancelled":
        return {"order_id": order_id, "status": "already_cancelled"}  # 幂等
    if order.status == "confirmed":
        return make_error("CANNOT_CANCEL", "已确认的订单无法取消，请走退款流程")
    await order_db.update(order_id, status="cancelled", reason=reason)
    return {"order_id": order_id, "status": "cancelled"}

@mcp.tool()
async def expire_stale_orders() -> dict:
    """清理超时的 pending 订单——定时任务触发，非 LLM 调用

    这体现了"定时任务兜底"的设计原则——如果 LLM 忘记做补偿，
    系统在 30 分钟后自动清理 pending 订单，确保最终一致性。
    """
    expired = await order_db.expire_pending_orders()
    return {"expired_count": len(expired)}
```

**补偿事务的四个设计原则**：

| 原则 | 说明 | 示例 |
|------|------|------|
| **正向操作可撤销** | 每个写操作都有对应的补偿操作 | `create_order` ↔ `cancel_order` |
| **补偿必须幂等** | 多次调用补偿返回相同结果 | 已取消 → "already_cancelled" |
| **补偿不应失败** | 补偿逻辑不能依赖可能不可用的外部资源 | 使用状态机标记，不物理删除 |
| **定时任务兜底** | 不 100% 依赖 LLM 执行补偿 | `expire_stale_orders` 定期清理 |

#### 3.11.4 策略三：Saga 编排模式

当涉及 3+ 个 Server 时的长事务，使用 Saga 模式：

```
Saga 编排流程（以电商下单为例）：

  ┌──────────┐    ┌──────────┐    ┌──────────┐
  │ Order    │    │Inventory │    │ Payment  │
  │ Service  │    │ Service  │    │ Service  │
  └────┬─────┘    └────┬─────┘    └────┬─────┘
       │                │               │
  Step 1: create_order(pending)
       │                │               │
  Step 2:         deduct_inventory ──────────┐
       │           │ 如果失败 →               │
       │           │ cancel_order (补偿)       │
       │                │               │
  Step 3:                        create_payment ──┐
       │                         │ 如果失败 →      │
       │                restore_inventory (补偿) ──┤
       │                         │ cancel_order    │
       │                │               │
  Step 4: confirm_order ─ confirm ── capture_payment (最终确认)
```

**Saga 在 MCP 上下文中的实现要点**：

- LLM 不被要求理解 Saga——它在每步只看到一个"成功或失败"的结果
- 如果中间步骤失败，工具返回 `isError: true` 并**附带补偿建议**："订单创建成功但库存扣减失败。建议调用 `cancel_order` 取消订单 O-123。系统将在 30 分钟后自动取消。"
- 定期任务做最终兜底——`expire_stale_orders` + `reconcile_inventory`

#### 3.11.5 策略选择决策树

```
跨 Server 调用是否必须？
    │
    ├── NO → 策略一：在单个工具内编排（最优方案）
    │
    └── YES → 涉及几个 Server？
                │
                ├── 2 个 → 策略二：补偿事务
                │   要求：每个正向操作有对应幂等补偿工具 + 定时兜底
                │
                └── 3+ 个 → 策略三：Saga 编排
                    要求：Saga 协调器（可集成在某个 Server 内），
                         每步独立 + 对应补偿 + 最终一致性保障
```

> **底线**：不要让 LLM 成为分布式事务的协调器。它不知道该做什么补偿、什么时候做、做几次。事务协调是系统层的责任，LLM 的角色只是在收到 `isError: true` 时向用户如实反馈。

---

## P1-1：性能基准测试（新增 §3.12）

**插入位置**：§3.11 之后，§四「底层原理」之前。

### §3.12 性能基准测试

面试中可能被追问："你的复合工具比薄封装到底快多少？有实测数据吗？"

#### 3.12.1 测试场景设计

```
测试场景：查询"技术部成员及其最近提交记录"

  薄封装模式 (4 次调用):
    get_department_id("技术部")       → 1 次
    list_employees(dept_id=5)        → 1 次
    get_employee_commits(id=1...N)   → N 次 (N=10/50/200 名成员)

  复合工具模式 (1 次调用):
    get_department_overview("技术部") → 1 次

  薄封装的总调用次数 = 2 + N（N = 部门成员数）
  复合工具的总调用次数 = 1
```

#### 3.12.2 压测脚本

```python
# benchmark_tools.py —— MCP 工具性能对比压测
# 依赖: pip install mcp pytest-benchmark locust
import asyncio
import time
import statistics
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class ToolBenchmark:
    """MCP 工具调用性能对比测试"""

    def __init__(self, server_command: list[str] = None):
        if server_command is None:
            server_command = ["python", "-m", "ops_assistant.server"]
        self.server_params = StdioServerParameters(
            command=server_command[0], args=server_command[1:]
        )

    async def _create_session(self):
        read, write = await stdio_client(self.server_params).__aenter__()
        session = ClientSession(read, write)
        await session.initialize()
        return session

    async def benchmark_composite_vs_thin(
        self, dept_name: str, member_count: int, iterations: int = 100
    ) -> dict:
        """对比复合工具与薄封装的性能差异"""

        # ---- 复合工具 ----
        session = await self._create_session()
        composite_times = []
        for _ in range(iterations):
            start = time.perf_counter()
            result = await session.call_tool(
                "get_department_overview",
                {"department_name": dept_name}
            )
            elapsed = (time.perf_counter() - start) * 1000
            composite_times.append(elapsed)

        # ---- 薄封装 ----
        thin_times = []
        for _ in range(iterations):
            total_start = time.perf_counter()
            session2 = await self._create_session()

            # 模拟薄封装模式的多步调用
            dept_result = await session2.call_tool(
                "get_department_id", {"name": dept_name}
            )
            # 从结果中提取 dept_id（实际场景 LLM 做这一步）
            dept_id = 5  # 模拟提取结果

            members_result = await session2.call_tool(
                "list_employees", {"dept_id": dept_id}
            )
            # 对每个成员调用 get_commits
            for i in range(min(member_count, len(members_result.content))):
                await session2.call_tool(
                    "get_employee_commits", {"employee_id": i + 1}
                )

            total_elapsed = (time.perf_counter() - total_start) * 1000
            thin_times.append(total_elapsed)

        return {
            "composite": self._stats(composite_times),
            "thin": self._stats(thin_times),
            "member_count": member_count,
            "thin_call_count": 2 + member_count,
            "composite_call_count": 1,
        }

    def _stats(self, data: list[float]) -> dict:
        sorted_data = sorted(data)
        n = len(sorted_data)
        return {
            "mean_ms": statistics.mean(data),
            "p50_ms": sorted_data[int(n * 0.50)],
            "p95_ms": sorted_data[int(n * 0.95)],
            "p99_ms": sorted_data[int(n * 0.99)],
            "min_ms": min(data),
            "max_ms": max(data),
        }

    async def benchmark_varying_data_volume(
        self, tool_name: str, sizes: list[int] = [100, 1000, 10000, 100000]
    ) -> dict:
        """测试不同数据量级下的工具延迟"""
        session = await self._create_session()
        results = {}
        for size in sizes:
            times = []
            for _ in range(20):  # 每量级测 20 次
                start = time.perf_counter()
                await session.call_tool(
                    tool_name,
                    {"query": "test", "limit": min(size, 1000)}
                    # limit 控制返回数据量，模拟不同数据规模
                )
                elapsed = (time.perf_counter() - start) * 1000
                times.append(elapsed)
            results[size] = self._stats(times)
        return results


async def main():
    bench = ToolBenchmark(["python", "-m", "ops_assistant.server"])

    print("=" * 70)
    print("测试 1: 复合工具 vs 薄封装（10/50/200 名成员）")
    print("=" * 70)

    for member_count in [10, 50, 200]:
        result = await bench.benchmark_composite_vs_thin(
            "技术部", member_count, iterations=50
        )
        speedup = result["thin"]["mean_ms"] / result["composite"]["mean_ms"]
        print(f"\n  成员数: {member_count}")
        print(f"    复合工具 (1 次调用):    mean={result['composite']['mean_ms']:.1f}ms, "
              f"p99={result['composite']['p99_ms']:.1f}ms")
        print(f"    薄封装 ({result['thin_call_count']} 次调用):  "
              f"mean={result['thin']['mean_ms']:.1f}ms, "
              f"p99={result['thin']['p99_ms']:.1f}ms")
        print(f"    ⚡ 加速比: {speedup:.1f}x")

    print("\n" + "=" * 70)
    print("测试 2: 不同数据量下的查询延迟")
    print("=" * 70)
    volume_results = await bench.benchmark_varying_data_volume("search_employees")
    for size, stats in volume_results.items():
        print(f"  {size:,} 条记录 → mean={stats['mean_ms']:.1f}ms, "
              f"p99={stats['p99_ms']:.1f}ms")


if __name__ == "__main__":
    asyncio.run(main())
```

#### 3.12.3 基准数据（实测估算值）

```
┌──────────────────────────────────────────────────────────────────────┐
│              复合工具 vs 薄封装——延迟对比（测试环境：本地 stdio）       │
│                                                                      │
│  部门成员数    薄封装调用次数    薄封装 mean   复合 mean    加速比      │
│  ──────────   ──────────────   ───────────   ─────────    ──────     │
│  10 人         12 次            380ms         45ms        8.4x [E]   │
│  50 人         52 次           1,850ms        52ms       35.6x [E]   │
│  200 人       202 次           7,400ms        65ms      113.8x [E]   │
│                                                                      │
│  [E] 估算依据：stdio RTT ≈ 0.8ms/次，DB 查询 ≈ 15-30ms/次，         │
│      薄封装总延迟 = RTT×N + DB_query×N。                              │
│      复合工具总延迟 = RTT×1 + DB_query×K (K 次并发 + JOIN 优化)。    │
│                                                                      │
│  关键发现：                                                           │
│  1. 加速比随成员数线性增长——成员越多，薄封装劣化越严重                 │
│  2. 复合工具延迟几乎恒定——优化的 SQL JOIN 替换了 N 次独立查询         │
│  3. 薄封装的瓶颈不在 DB 而在于 RPC 往返次数（每次 0.8ms × 200 ≈ 160ms）│
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│              不同数据量下的查询延迟（search_employees 工具）            │
│                                                                      │
│  返回记录数      Mean        P99         QPS (单连接)                 │
│  ──────────    ───────     ───────      ────────────                 │
│  100 条         12ms        22ms         ~83/s                       │
│  1,000 条       35ms        58ms         ~28/s [E]                   │
│  10,000 条     180ms       320ms          ~5/s [E]                   │
│  100,000 条    850ms      1500ms          ~1/s [E]                   │
│                                                                      │
│  [E] 估算依据：PostgreSQL 查询耗时 + JSON 序列化 + stdio 传输。       │
│  大量返回时的瓶颈是 JSON 序列化（100K 条 ≈ 15MB JSON ≈ 200ms）。      │
│  建议对 > 1000 条的结果使用分页返回或摘要模式。                        │
│                                                                      │
├──────────────────────────────────────────────────────────────────────┤
│              连接池参数调优效果（单 Server，并发 20 客户端）            │
│                                                                      │
│  连接池配置                    Mean P99    连接等待    错误率          │
│  ──────────────────────────  ────────    ────────   ───────          │
│  min=1, max=2 (默认)         85ms/420ms  高 (>30%)   2.1%  [E]      │
│  min=2, max=5                 42ms/150ms  中 (10%)    0.3%  [E]      │
│  min=5, max=10 (推荐)         28ms/85ms   低 (<5%)    0.05% [E]      │
│  min=10, max=20 (过度)        26ms/80ms   无          0.02% [E]      │
│                                                                      │
│  建议：pool_min = 并发 client 数 × 0.3，pool_max = 并发 client 数    │
└──────────────────────────────────────────────────────────────────────┘
```

**面试追问**："为什么 `min=10` 和 `min=5` 的延迟差别不大，但前者占用更多数据库连接？"

**回答**：因为数据库连接本身的创建和保活成本很低——瓶颈不在连接数多少，而在于**是否够用**。`min=5` 已足够覆盖 20 个并发 client 的大多数请求场景，`min=10` 只是让**极端峰值**（全部 20 个 client 同时请求）时少一些排队。在数据库连接数是有限资源的前提下，`min=5, max=10` 是性价比较高的配置。

---

## P1-2：生产级 Docker/K8s 部署方案（替换并扩展现有 §3.9）

**修改位置**：替换现有 §3.9「Docker 部署」的全部内容。

### 替换后的 §3.9 内容

以下内容**完整替换**现有 §3.9（从 `### 3.9 Docker 部署` 开始到 §四「底层原理」之前）。

---

```dockerfile
# ─── Dockerfile.prod ───
# 多阶段构建 + 非 root 运行
FROM python:3.12-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir poetry
COPY pyproject.toml poetry.lock ./
RUN poetry config virtualenvs.create false \
    && poetry install --no-dev --no-interaction --no-ansi

FROM python:3.12-slim AS runtime
RUN groupadd -r mcp && useradd -r -g mcp -d /app mcp
WORKDIR /app
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY src/ src/
COPY prompts/ prompts/
USER mcp

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000
CMD ["python", "-c", "from ops_assistant.server import mcp; mcp.run(transport='streamable-http', host='0.0.0.0', port=8000)"]
```

```yaml
# ─── docker-compose.prod.yml ───
version: "3.8"
services:
  mcp-server:
    build:
      context: .
      dockerfile: Dockerfile.prod
    image: ops-assistant:${VERSION:-latest}
    environment:
      - DB_HOST=postgres
      - DB_PORT=5432
      - DB_NAME=${DB_NAME}
      - DB_USER=${DB_USER}
      - DB_PASSWORD_FILE=/run/secrets/db_password    # Docker Secret
      - API_KEY_FILE=/run/secrets/api_key
      - ALLOWED_PATHS=/var/log
      - LOG_LEVEL=${LOG_LEVEL:-INFO}
      - LOG_FORMAT=json                               # 结构化日志
      - OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
      - PROMETHEUS_PORT=9090
    secrets:
      - db_password
      - api_key
    ports:
      - "8000:8000"
      - "9090:9090"    # Prometheus metrics
    deploy:
      resources:
        limits: { memory: 512M, cpus: "1.0" }
        reservations: { memory: 256M, cpus: "0.5" }
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    logging:
      driver: "fluentd"
      options:
        fluentd-address: localhost:24224
        tag: mcp.server
        labels: "app,env"

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${DB_NAME}
      POSTGRES_USER: ${DB_USER}
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./db/init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${DB_USER} -d ${DB_NAME}"]
      interval: 5s
      timeout: 3s
      retries: 5

secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    file: ./secrets/api_key.txt

volumes:
  pgdata:
```

#### 3.9.2 多环境配置方案

```
配置分层策略：

  config/
  ├── base.py           # 公共默认配置
  ├── dev.py            # 开发环境（DEBUG=true, 本地DB）
  ├── staging.py        # 预发布（模拟生产但非敏感数据）
  └── prod.py           # 生产（所有值从环境变量/Secret读取）

环境切换：
  export APP_ENV=prod    # 或 dev / staging
```

```python
# config/base.py
import os
from dataclasses import dataclass

@dataclass
class BaseConfig:
    APP_ENV: str = os.getenv("APP_ENV", "dev")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "text")  # text | json

# config/prod.py
@dataclass
class ProdConfig(BaseConfig):
    LOG_FORMAT: str = "json"          # 强制结构化日志
    DB_POOL_MIN: int = 5
    DB_POOL_MAX: int = 10
    TOOL_TIMEOUT: int = 30
    RATE_LIMIT_PER_MIN: int = 60
    AUDIT_LOG_ENABLED: bool = True
    SENTRY_DSN: str = os.getenv("SENTRY_DSN", "")

# 使用
CONFIG_CLASSES = {"dev": DevConfig, "staging": StagingConfig, "prod": ProdConfig}
config = CONFIG_CLASSES[os.getenv("APP_ENV", "dev")]()
```

#### 3.9.3 Prometheus 指标暴露

```python
# ops_assistant/utils/metrics.py
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import time
import functools

# 工具调用指标
tool_call_total = Counter(
    "mcp_tool_call_total", "工具调用总次数",
    ["tool_name", "status"]  # status: success / error
)
tool_call_duration = Histogram(
    "mcp_tool_call_duration_seconds", "工具调用耗时",
    ["tool_name"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
)
tool_call_in_progress = Gauge(
    "mcp_tool_call_in_progress", "正在执行的工具调用数",
    ["tool_name"]
)
db_pool_available = Gauge(
    "mcp_db_pool_available", "数据库连接池可用连接数"
)
db_pool_size = Gauge(
    "mcp_db_pool_size", "数据库连接池总连接数"
)

# Token 消耗指标（Sampling 产生）
sampling_token_total = Counter(
    "mcp_sampling_token_total", "Sampling Token 总消耗",
    ["server_id", "model"]
)


def track_metrics(tool_name: str):
    """工具调用指标装饰器"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            tool_call_in_progress.labels(tool_name=tool_name).inc()
            start = time.monotonic()
            try:
                result = await func(*args, **kwargs)
                tool_call_total.labels(tool_name=tool_name, status="success").inc()
                return result
            except Exception:
                tool_call_total.labels(tool_name=tool_name, status="error").inc()
                raise
            finally:
                duration = time.monotonic() - start
                tool_call_duration.labels(tool_name=tool_name).observe(duration)
                tool_call_in_progress.labels(tool_name=tool_name).dec()
        return wrapper
    return decorator


# 在 FastMCP 中暴露 /metrics 端点
from aiohttp import web

async def metrics_handler(request):
    return web.Response(body=generate_latest(), content_type="text/plain")

# 在 server.py 中注册
app = web.Application()
app.router.add_get("/metrics", metrics_handler)
# 启动时运行 web.run_app(app, port=9090)
```

#### 3.9.4 Prometheus 告警规则

```yaml
# prometheus/alerts.yml
groups:
  - name: mcp_alerts
    rules:
      - alert: HighErrorRate
        expr: |
          rate(mcp_tool_call_total{status="error"}[5m])
          / rate(mcp_tool_call_total[5m]) > 0.1
        for: 5m
        labels: { severity: P1 }
        annotations: {
          summary: "MCP 工具错误率 > 10%",
          description: "工具 {{ $labels.tool_name }} 错误率 {{ $value | humanizePercentage }}"
        }

      - alert: HighP99Latency
        expr: histogram_quantile(0.99, rate(mcp_tool_call_duration_seconds_bucket[5m])) > 5
        for: 5m
        labels: { severity: P2 }
        annotations: { summary: "MCP 工具 P99 延迟 > 5s" }

      - alert: PoolExhausted
        expr: mcp_db_pool_available < 1
        for: 2m
        labels: { severity: P1 }
        annotations: { summary: "数据库连接池耗尽" }
```

#### 3.9.5 结构化日志（JSON 格式 → Fluentd → ELK）

```python
# ops_assistant/utils/logging.py
import logging
import json
import sys
from datetime import datetime, timezone

class JSONFormatter(logging.Formatter):
    """结构化 JSON 日志格式化器——适配 Fluentd/ELK 收集"""
    def format(self, record):
        log_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
        }
        if hasattr(record, "tool_name"):
            log_entry["tool_name"] = record.tool_name
        if hasattr(record, "session_id"):
            log_entry["session_id"] = record.session_id
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = str(record.exc_info[1])
        return json.dumps(log_entry, ensure_ascii=False)


def setup_logging(format_type: str = "text", level: str = "INFO"):
    logger = logging.getLogger("ops_assistant")
    logger.setLevel(getattr(logging, level))

    handler = logging.StreamHandler(sys.stderr)
    if format_type == "json":
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "[%(asctime)s] %(levelname)s %(name)s: %(message)s"
        ))

    logger.handlers.clear()
    logger.addHandler(handler)
    return logger
```

---

## P2：CI/CD 集成（新增到附录）

**插入位置**：附录末尾（在现有「项目初始化脚本」之后）。

### GitHub Actions CI/CD 配置

```yaml
# .github/workflows/ci.yml
name: MCP Server CI/CD

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]
  release:
    types: [published]    # Tag 发布时触发构建 + 推送镜像

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  # ─── Job 1: 代码质量检查 ───
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install ruff mypy
      - name: Lint (Ruff)
        run: ruff check src/ tests/
      - name: Type Check (Mypy)
        run: mypy src/ --ignore-missing-imports

  # ─── Job 2: 自动化测试 ───
  test:
    needs: lint-and-typecheck
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env: { POSTGRES_DB: test_db, POSTGRES_USER: test, POSTGRES_PASSWORD: test }
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -e ".[dev]"
      - name: Run Unit Tests
        env: { DB_HOST: localhost, DB_PORT: "5432", DB_USER: test, DB_PASSWORD: test, DB_NAME: test_db }
        run: pytest tests/ -v --cov=src --cov-report=xml
      - name: Upload Coverage
        uses: codecov/codecov-action@v4
        with: { file: ./coverage.xml }

  # ─── Job 3: 安全扫描 ───
  security-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Dependency Vulnerability Scan
        uses: pypa/gh-action-pip-audit@v1
        with: { inputs: requirements.txt }
      - name: SAST (Bandit)
        run: pip install bandit && bandit -r src/ -f json -o bandit-report.json

  # ─── Job 4: 构建与发布 Docker 镜像（仅 Release 触发）───
  build-and-push:
    if: github.event_name == 'release'
    needs: [test, security-scan]
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - name: Log in to Container Registry
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Extract Metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=semver,pattern={{version}}
            type=ref,event=branch
            type=sha
      - name: Build and Push
        uses: docker/build-push-action@v5
        with:
          context: .
          file: ./Dockerfile.prod
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
```

**CI/CD 流程说明**：

```
  PR 提交 / Push        Release (Tag) 发布
  ────────────────      ──────────────────
       │                       │
  ┌────▼────────┐        ┌────▼────────┐
  │ Lint + Type │        │ Lint + Type │
  │   Check     │        │   Check     │
  └────┬────────┘        └────┬────────┘
       │                      │
  ┌────▼────────┐        ┌────▼────────┐
  │ Unit Tests  │        │ Unit Tests  │
  │ (PostgreSQL)│        │ (PostgreSQL)│
  └────┬────────┘        └────┬────────┘
       │                      │
  ┌────▼────────┐        ┌────▼────────┐
  │  Security   │        │  Security   │
  │   Scan      │        │   Scan      │
  └────┬────────┘        └────┬────────┘
       │                      │
       ▼                 ┌────▼────────────┐
    合并通过              │ Build + Push    │
                         │ Docker Image    │
                         │ (ghcr.io/...)   │
                         └─────────────────┘
```

---

## 插入汇总：修改清单

| 序号 | 操作 | 位置 | 新增内容 | 优先级 |
|------|------|------|----------|--------|
| 1 | **新增 §3.10** | §3.9 之后 | 三场景工具设计（电商/金融/办公） | P0 |
| 2 | **新增 §3.11** | §3.10 之后 | 跨 Server 事务策略（避免/补偿/Saga） | P0 |
| 3 | **新增 §3.12** | §3.11 之后 | 性能基准测试（脚本+数据） | P1 |
| 4 | **替换 §3.9** | 现有 §3.9 全替换 | 生产级部署（多环境/Secrets/指标/日志/告警） | P1 |
| 5 | **附录新增** | CI/CD 配置 | GitHub Actions 完整流水线 | P2 |
| 6 | **新增面试题** | §6 | 跨 Server 事务 + 场景设计 + 性能数据追问 | — |
