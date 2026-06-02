# MCP（Model Context Protocol）全栈教学

> 从入门到企业级实战的完整学习路径，共 7 个模块，约 40–55 天。
> 每个模块按 **是什么 → 为什么需要 → 如何实现 → 底层原理 → 企业级最佳实践 → 常见面试题**
> 六层递进结构编写。

---

## 学习路线图

```
模块 1（4-5 天）         模块 2（5-6 天）         模块 3（5-6 天）
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  MCP 基础认知    │ ──→ │  协议层深入理解   │ ──→ │  开发入门        │
│  定义·演进·对比  │     │  传输·原语·协商   │     │  SDK·FastMCP    │
└─────────────────┘     └─────────────────┘     └────────┬────────┘
                                                         │
                                                         ▼
                                              ┌─────────────────┐
                                              │  全栈项目实战    │
                                              │  三场景·事务·   │
                                              │  性能基准·部署  │
                                              └────────┬────────┘
                                                       │
模块 6（9-12 天）       模块 5（7-9 天）                 │
┌─────────────────┐     ┌─────────────────┐              │
│  多 Agent 编排   │ ←── │  架构设计与安全  │ ←───────────┘
│  LangGraph·A2A  │     │  Gateway·威胁建模│
└─────────────────┘     └─────────────────┘

模块 7：面试冲刺（贯穿全程）→ 27 道真题 + 高压模拟 + 1h 速查表
```

---

## [第一模块：MCP 基础认知与核心概念](docs/01-mcp-basic-cognition-and-core-concepts.md)（4-5 天）

- 一、是什么——MCP 的定义与定位
  - 1.1 官方定义
  - 1.2 类比理解
  - 1.3 MCP 在 AI 技术栈中的位置
  - 1.4 MCP 不是银弹
  - 1.5 历史与技术演进背景
    - 1.5.1 脉络一：LSP 的成功——范式的证明（2016-2020）
    - 1.5.2 脉络二：ChatGPT Plugins 的失败——不可重蹈的覆辙（2023.03-2024.04）
    - 1.5.3 脉络三：开源模型的崛起——工具的民主化需求（2023-2024）
    - 1.5.4 三条脉络的交汇点：2024 年 11 月
- 二、为什么需要——MCP 解决的核心痛点
  - 2.1 传统 Function Calling 模式的三个核心问题（厂商绑定 / 无统一执行标准 / 功能简陋）
  - 2.2 N×M 集成困境
  - 2.3 真实业务场景的痛点对照
  - 2.4 扩展协议横向对比
    - 2.4.1 MCP（JSON-RPC）与 gRPC 的对比
    - 2.4.2 WebSocket 与 Streamable HTTP 的对比
    - 2.4.3 GraphQL Schema Introspection 与 MCP 工具发现机制
- 三、如何实现——MCP 的核心架构
  - 3.1 三层架构模型（Host / Client / Server）
  - 3.2 MCP 的三个核心原语详解（Tools / Resources / Prompts）
  - 3.3 传输层支持
  - 3.4 设计权衡：MCP 选择牺牲了什么
    - 3.4.1 简单性与灵活性——为何只定义 3+1 个原语？
    - 3.4.2 标准化与性能——JSON 文本协议的代价
    - 3.4.3 安全性与便利性——Server 看不到对话历史的设计
- 四、底层原理——协议细节与消息流转
  - 4.1 协议基础：JSON-RPC 2.0
  - 4.2 完整的生命周期（初始化 → 协商 → 运行 → 关闭）
  - 4.3 完整调用链路——以"查询天气"为例
  - 4.4 错误处理模型
- 五、企业级最佳实践
  - 5.1 是否采用 MCP——决策框架
    - 5.1.1 量化决策标准（Token 临界点 / 延迟模型 / 边际成本 / 综合评分公式）
    - 5.1.2 什么时候不该用 MCP（7 个反面场景）
  - 5.2 MCP Server 设计原则（单一职责 / 最小权限 / 结构化输出 / 工具描述即文档）
  - 5.3 安全最佳实践
  - 5.4 性能优化建议
- 六、常见面试题（Q1-Q14）
  - 基础概念 / 架构理解 / 深入思考 / 扩展协议对比 / 量化决策
- 附录：核心术语速查表 / 学员自查清单 / 推荐阅读

---

## [第二模块：MCP 协议层深入理解](docs/02-mcp-protocol-layer-deep-dive.md)（5-6 天）

- 一、是什么——MCP 协议全景回顾
  - 1.1 MCP 协议的层次结构
  - 1.2 什么是 JSON-RPC 2.0
- 二、为什么需要——传输层演进与核心原语设计动机
  - 2.1 为什么需要三种传输方式（stdio / SSE / Streamable HTTP）
  - 2.2 为什么需要四大核心原语
- 三、如何实现——传输机制与原语详解
  - 3.1 stdio 传输实现（工作原理 / 消息分帧）
  - 3.2 SSE 传输实现（架构 / Client 端 / Server 端 / 排障点）
  - 3.3 Streamable HTTP 传输实现（两种模式 / 完整实现）
  - 3.4 四大核心原语详解
    - 3.4.1 Tools（工具）—— 深度剖析
    - 3.4.2 Resources（资源）—— 深度剖析
    - 3.4.3 Prompts（提示词模板）—— 深度剖析
    - 3.4.4 Sampling（采样）—— 反向请求 LLM（含递归攻击防护 + Token 归属 + 三层安全）
    - 3.4.5 Elicitation（引导模式）—— Server 向用户提问
  - 3.5 传输方式性能基准测试（测试代码 + 基准数据 + 连接数分析 + 选型速查）
- 四、底层原理——JSON-RPC 消息格式与能力协商
  - 4.1 JSON-RPC 消息类型完整规范（四种类型 / 错误码 / 批量请求）
  - 4.2 能力协商机制深度解析（Client/Server 能力声明 / 协商流程 / 渐进式更新）
  - 4.3 通知机制（全部标准通知 / 进度通知 / 取消通知）
  - 4.4 协议版本演进
  - 4.5 协议版本逐项差异对照与兼容策略
    - 4.5.1 initialize 请求/响应的字段变化
    - 4.5.2 capabilities 声明的字段级别差异
    - 4.5.3 新增或废弃的方法
    - 4.5.4 版本兼容性实战（含跨版本适配器代码）
- 五、企业级最佳实践
  - 5.1 传输方式选择决策树
  - 5.2 Architecture 设计模式（聚合 Server / 职责链 / 缓存代理）
  - 5.3 安全加固清单
  - 5.4 排障指南
- 六、常见面试题（Q1-Q12）
  - 传输层 / 核心原语 / 能力协商与协议细节 / 设计理解 / 版本兼容与性能
- 附录：新增术语速查表 / 协议方法速查表 / 推荐阅读

---

## [第三模块：MCP Server/Client 开发入门](docs/03-mcp-server-client-development.md)（5-6 天）

- 一、是什么——MCP SDK 体系概览
  - 1.1 SDK 全景图（含 Go SDK 实战示例 + 面试追问）
  - 1.2 FastMCP vs Low-Level API
  - 1.3 版本对照表
  - 1.4 跨语言 SDK 行为差异与迁移注意事项
    - 1.4.1 `server.run()` 废弃后的完整迁移 checklist
    - 1.4.2 Python SDK vs TypeScript SDK 关键行为差异
    - 1.4.3 Go SDK 的定位
- 二、为什么需要——SDK 解决了哪些开发痛点
  - 2.1 如果没有 SDK——裸写 JSON-RPC 的痛苦
  - 2.2 SDK 的核心价值
- 三、如何实现——从零构建 MCP Server 和 Client
  - 3.1 开发环境搭建（Python / TypeScript / 工具配置）
  - 3.2 第一个 MCP Server（最小示例 / Inspector 测试 / Claude Desktop 注册）
  - 3.3 Tool 的定义与最佳实践
    - 3.3.1-3.3.3 基础定义 / 工具描述即文档 / 类型注解→JSON Schema
    - 3.3.4 工具编写的十大准则
    - 3.3.5 全局错误处理中间件（LLM 友好异常 + isError 决策树）
  - 3.4 Resource 的暴露方式（静态 / 动态 URI 模板 / Tool 协作模式）
  - 3.5 构建 MCP Client
    - 3.5.2 构建健壮的 MCP Client（重连 / 超时 / 并发 / 缓存四维度）
  - 3.6 TypeScript SDK 等价实现
  - 3.7 测试与调试
    - 3.7.1 MCP Inspector
    - 3.7.2 单元测试 MCP Server
    - 3.7.3 集成测试
    - 3.7.4 调试技巧汇总
    - 3.7.5 使用 Mock Transport 进行轻量级测试（5 个完整测试用例）
- 四、底层原理——SDK 内部机制剖析
  - 4.1 FastMCP 装饰器的魔法
  - 4.2 请求的生命周期
  - 4.3 传输层切换的原理
  - 4.4 Client 端协议协商的底层流程
- 五、企业级最佳实践
  - 5.1 项目结构推荐 / 5.2 工具模块化与注册 / 5.3 敏感信息管理 / 5.4 错误处理策略 / 5.5 性能优化
- 六、常见面试题（Q1-Q9）
  - 基础开发 / 类型系统与 Schema / 测试与调试 / 设计理解 / Go SDK 与跨语言
- 附录：FastMCP 装饰器速查 / transport 参数 / 开发命令速查 / 推荐阅读

---

## [第四模块：MCP 全栈项目实战](docs/04-mcp-full-stack-project-practice.md)（7-9 天）

- 一、是什么——全栈 MCP 项目的完整图景
  - 1.1 什么是"全栈 MCP 项目"
  - 1.2 本项目实战目标
- 二、为什么需要——从 Demo 到生产的鸿沟
  - 2.1 Demo 和生产的距离
  - 2.2 核心痛点：N×M 之外还有 "N+1"
- 三、如何实现——全栈 MCP 项目实战
  - 3.1 项目架构设计（分层架构 / 完整项目结构）
  - 3.2 配置管理
  - 3.3 数据访问层（PostgreSQL 客户端 / REST API 客户端 / 文件系统管理器）
  - 3.4 服务层——业务逻辑 + 数据聚合
  - 3.5 工具层——面向 LLM 的工具设计
  - 3.6 统一错误处理
  - 3.7 主入口组装
  - 3.8 提示词模板设计
  - 3.9 生产级部署（多阶段 Docker + Secrets + Fluentd + Prometheus 指标/告警 + 结构化日志）
  - 3.10 不同业务领域的工具设计模式
    - 3.10.1 电商——高并发 + 库存一致性
    - 3.10.2 金融——审计追踪 + 数据脱敏
    - 3.10.3 办公——跨系统权限收敛
    - 3.10.4 三场景对比总结
  - 3.11 跨 Server 事务场景的设计策略
    - 3.11.1 策略一：避免跨 Server（单工具内编排，首选）
    - 3.11.2 策略二：补偿事务（跨 2 个 Server 的兜底方案）
    - 3.11.3 策略三：Saga 编排（3+ 个 Server）
    - 3.11.4 决策树
  - 3.12 性能基准测试（复合 vs 薄封装加速比 / 数据量延迟 / 连接池调优 / 可运行压测脚本）
- 四、底层原理——复合工具与多 Server 协作机制
  - 4.1 N+1 问题的数学分析
  - 4.2 复合工具设计原则
  - 4.3 多 Server 协作原理
- 五、企业级最佳实践
  - 5.1 工具粒度选择决策矩阵 / 5.2 面向 LLM 的错误消息模板 / 5.3 性能优化全景
  - 5.4 安全检查清单 / 5.5 可观测性建议
- 六、常见面试题（Q1-Q11）
  - 项目架构 / 数据源对接 / 多 Server 协作 / 设计理解 / 跨 Server 一致性 / 多场景设计 / 生产部署
- 附录：项目初始化脚本 / GitHub Actions CI/CD 配置 / 推荐阅读

---

## [第五模块：生产级 MCP 架构设计与安全](docs/05-production-architecture-and-security.md)（7-9 天）

- 一、是什么——生产级 MCP 架构全景
  - 1.1 生产级架构全景图
  - 1.2 本地模式 vs 远程模式 vs 混合模式的本质差异
- 二、为什么需要——从单机到生产的核心挑战
  - 2.1 为什么本地 stdio 不够用
  - 2.2 远程化引入的新问题
- 三、如何实现——生产级架构设计与部署
  - 3.1 传输模式选择与远程部署（决策树 / Docker / Kubernetes / 云函数）
  - 3.2 认证与授权体系（方案对比 / OAuth 2.0 集成 / 细粒度 RBAC / 安全沙箱）
  - 3.3 MCP Gateway 架构
    - 3.3.1 什么是 MCP Gateway
    - 3.3.2 Gateway 核心实现
    - 3.3.3 大厂 MCP 生态产品
    - 3.3.4 生产级 MCP Gateway 进阶（高可用多副本 + Redis/etcd 路由表 + 灰度发布）
  - 3.4 性能优化
    - 3.4.1 调用延迟优化全景 / 3.4.2 Resource 缓存策略 / 3.4.3 连接池管理
    - 3.4.4 MCP vs Function Calling 的性能差异
    - 3.4.5 性能优化实战案例（P99 2.3s→120ms 完整闭环 + 缓存三层防护）
  - 3.5 可观测性与监控（三大支柱 / 告警规则）
  - 3.6 MCP 安全威胁建模与防御
    - 3.6.1 STRIDE 威胁总览
    - 3.6.2 Prompt Injection 防御
    - 3.6.3 SSRF 防御
    - 3.6.4 DoS 防御——熔断器
    - 3.6.5 防御矩阵
  - 3.7 多租户 MCP 平台设计（数据隔离 / 配额管理 / 计费模型）
  - 3.8 合规与隐私保护（数据驻留 / 不可篡改审计日志 / 遗忘权）
  - 3.9 容灾与高可用架构（跨 Region 温备 / 备份策略 / 混沌工程）
- 四、底层原理——认证、网关与性能机制
  - 4.1 OAuth 2.0 在 MCP 中的认证流程 / 4.2 Gateway 路由原理 / 4.3 限流算法对比
- 五、企业级最佳实践
  - 5.1 安全加固清单 / 5.2 部署模式选择指南 / 5.3 监控仪表盘设计
- 六、常见面试题（Q1-Q9）
  - 安全与认证 / 架构与部署 / 性能优化 / 安全威胁 / 多租户 / 合规容灾
- 附录：生产环境配置模板 / 推荐阅读

---

## [第六模块：多 Agent 编排与 MCP 生态集成](docs/06-multi-agent-orchestration-and-ecosystem.md)（9-12 天）

- 一、是什么——MCP 在多 Agent 系统中的定位
  - 1.1 MCP 的角色：工具接入标准
  - 1.2 MCP 与 A2A 的关系
- 二、为什么需要——单 Agent 到多 Agent 的演进动力
  - 2.1 单 Agent 的局限
  - 2.2 多 Agent 的优势
- 三、如何实现——框架集成与多 Agent 实战
  - 3.1 LangGraph + MCP（架构设计 + 完整实现，含闭包 Bug 修复）
  - 3.2 CrewAI + MCP（修复版：独立线程 event loop + 公开 API + 异常处理）
  - 3.2.5 OpenAI Agents SDK + MCP 集成（Handoff 三 Agent 编排 + 框架对比）
  - 3.3 大厂 MCP 应用场景解析
    - 3.3.1 Cloudflare——企业可观测性
    - 3.3.2 蚂蚁数科——金融 MCP 服务广场
    - 3.3.3 Hugging Face——AI 模型中心
    - 3.3.4 国内生态汇总
  - 3.4 多 Agent 系统的评测、监控与调试（评测指标体系 / TraceSpan 调用链追踪 / 异常定位 5 步法）
  - 3.5 企业落地 MCP 的实际挑战与应对策略（组织层面 / REST→MCP 迁移三阶段 / 人才缺口）
- 四、底层原理——A2A 协议与工具发现机制
  - 4.1 A2A 协议核心概念（Task 生命周期状态机 / Agent Card 能力声明）
  - 4.2 MCP 与 A2A 的协同（完整代码演示 + MCP vs A2A 边界决策树）
  - 4.3 工具发现与动态注册机制
- 五、企业级最佳实践
  - 5.1 框架选型决策树 / 5.2 多 Agent 设计原则 / 5.3 MCP Server 生态发布指南
- 六、常见面试题（Q1-Q9）
  - 框架集成 / 大厂场景 / 设计理解 / 闭包陷阱 / Handoff 对比 / 评测调试 / MCP vs A2A 边界
- 附录：多 Agent 框架对比速查表 / 推荐阅读

---

## [第七模块：面试冲刺与大厂实战](docs/07-interview-preparation-and-enterprise-practice.md)（贯穿全程）

- 一、面试全景——考什么、怎么考
  - 1.1 大厂 MCP 面试题型分布（饼图：基础 15% / 协议 18% / 开发 18% / 安全 18% / 场景 12% / 故障 8% / 对比 6%）
  - 1.2 面试官在考察什么（Level 1 用过吗 → Level 2 理解多深 → Level 3 能设计吗）
  - 1.3 不同公司/级别的面试侧重点分析
    - 按公司：阿里（架构+多租户）/ 腾讯（安全+生态）/ 字节（性能+实战）/ Google（协议理论）/ Anthropic（安全哲学）
    - 按级别：P6（基础+开发）/ P7（架构+权衡）/ P8（定义问题+行业趋势）
- 二、基础必答题（4 题·全部背诵）—— Q1~Q4
  - 每题附：面试官想听到的关键词 + STAR 法则回答模板
- 三、进阶题（6 题·理解+发挥）—— Q5~Q10
  - 能力协商 / 安全模型 / N+1 优化 / 发展问题 / JSON-RPC vs gRPC / Streamable HTTP 对比
- 四、拔高题（5 题·展示深度）—— Q11~Q15
  - 10 万并发平台 / 工具注册中心 / 连接中断处理 / REST vs MCP / 电商场景设计
- 五、专题题型（8 题·覆盖盲区）—— Q16~Q23
  - 场景设计题（金融 Q16 / 办公 Q17）
  - 故障定位题（工具慢排查 Q18 / 数据不一致修复 Q19）
  - 对比分析题（MCP vs gRPC vs REST Q20 / MCP vs A2A 边界 Q21）
  - 代码审查题（5 类常见问题 Q22）
  - 开放讨论题（协议最大设计缺陷 Q23）
- 六、面试模拟对话
  - 6.1 高压追问模拟（2 组 5 连追问：N+1 主题 + 安全主题）
  - 6.2 跨领域串联模拟（MCP→系统设计→团队协作→技术 四问串联）
  - 6.3 卡壳时的应对策略与话术（5 种场景 + 具体话术表格）
- 七、考前速查与知识索引
  - 7.1 面试前 1 小时速查表（核心定义 30 秒话术 + 关键数字 + 5 条必背金句 + 6 条高频追问回应 + 按公司准备）
  - 7.2 知识体系全景图
  - 7.3 各模块文档索引
  - 完整题库索引（27 题速查表）

---

## 每个文档的六层递进结构

1. **一、是什么** —— 概念定义、全景图、边界认知
2. **二、为什么需要** —— 痛点分析、动机阐述、对比论证
3. **三、如何实现** —— 完整代码、分步实操、可运行示例
4. **四、底层原理** —— 协议机制、源码剖析、数学推导
5. **五、企业级最佳实践** —— 决策框架、设计原则、安全清单
6. **六、常见面试题** —— 参考答案、得分要点、加分金句

---

## 快速跳转——按话题查找

| 话题 | 跳转 |
|------|------|
| MCP 是什么、解决什么问题 | [模块 1 § 一、二](docs/01-mcp-basic-cognition-and-core-concepts.md) |
| 历史演进（LSP → Plugins → 开源模型） | [模块 1 § 1.5](docs/01-mcp-basic-cognition-and-core-concepts.md#15-历史与技术演进背景) |
| MCP vs gRPC / WebSocket / GraphQL | [模块 1 § 2.4](docs/01-mcp-basic-cognition-and-core-concepts.md#24-扩展协议横向对比) |
| 设计权衡（简单性/性能/安全性） | [模块 1 § 3.4](docs/01-mcp-basic-cognition-and-core-concepts.md#34-设计权衡mcp-选择牺牲了什么) |
| 量化决策（Token 临界点 / 延迟模型） | [模块 1 § 5.1.1](docs/01-mcp-basic-cognition-and-core-concepts.md#511-量化决策标准) |
| 三层架构 + 四种原语 | [模块 1 § 三](docs/01-mcp-basic-cognition-and-core-concepts.md) + [模块 2 § 三](docs/02-mcp-protocol-layer-deep-dive.md) |
| 协议版本差异与跨版本兼容 | [模块 2 § 4.5](docs/02-mcp-protocol-layer-deep-dive.md#45-协议版本逐项差异对照与兼容策略) |
| Elicitation 引导模式 | [模块 2 § 3.4.5](docs/02-mcp-protocol-layer-deep-dive.md#345-elicitations引导模式--server-向用户提问) |
| 传输性能基准数据 | [模块 2 § 3.5](docs/02-mcp-protocol-layer-deep-dive.md#35-传输方式性能基准测试) |
| FastMCP 开发 + Go SDK | [模块 3 § 三](docs/03-mcp-server-client-development.md) |
| 全局错误处理中间件 | [模块 3 § 3.3.5](docs/03-mcp-server-client-development.md#335-全局错误处理中间件) |
| 健壮 Client（重连/超时/并发/缓存） | [模块 3 § 3.5.2](docs/03-mcp-server-client-development.md#352-构建健壮的-mcp-client) |
| Mock Transport 单元测试 | [模块 3 § 3.7.5](docs/03-mcp-server-client-development.md#375-使用-mock-transport-进行轻量级测试) |
| N+1 问题与复合工具设计 | [模块 4 § 四](docs/04-mcp-full-stack-project-practice.md) |
| 三场景工具设计（电商/金融/办公） | [模块 4 § 3.10](docs/04-mcp-full-stack-project-practice.md#310-不同业务领域的工具设计模式) |
| 跨 Server 事务策略（补偿/Saga） | [模块 4 § 3.11](docs/04-mcp-full-stack-project-practice.md#311-跨-server-事务场景的设计策略) |
| 性能基准测试 | [模块 4 § 3.12](docs/04-mcp-full-stack-project-practice.md#312-性能基准测试) |
| 生产级部署（Docker/K8s/Secrets/Fluentd） | [模块 4 § 3.9](docs/04-mcp-full-stack-project-practice.md#39-生产级部署) |
| CI/CD（GitHub Actions） | [模块 4 附录](docs/04-mcp-full-stack-project-practice.md#github-actions-cicd-配置) |
| OAuth 2.0 / RBAC 认证授权 | [模块 5 § 3.2](docs/05-production-architecture-and-security.md#32-认证与授权体系) |
| MCP Gateway 架构 | [模块 5 § 3.3](docs/05-production-architecture-and-security.md#33-mcp-gateway-架构) |
| STRIDE 安全威胁建模 | [模块 5 § 3.6](docs/05-production-architecture-and-security.md#36-mcp-安全威胁建模与防御) |
| 性能优化闭环案例（P99 2.3s→120ms） | [模块 5 § 3.4.5](docs/05-production-architecture-and-security.md#345-性能优化实战案例) |
| 多租户平台设计 | [模块 5 § 3.7](docs/05-production-architecture-and-security.md#37-多租户-mcp-平台设计) |
| 合规与容灾 | [模块 5 § 3.8-3.9](docs/05-production-architecture-and-security.md#38-合规与隐私保护) |
| LangGraph + MCP 集成 | [模块 6 § 3.1](docs/06-multi-agent-orchestration-and-ecosystem.md#31-langgraph--mcp) |
| CrewAI + MCP（修复版） | [模块 6 § 3.2](docs/06-multi-agent-orchestration-and-ecosystem.md#32-crewai--mcp修复版) |
| OpenAI Agents SDK + MCP | [模块 6 § 3.2.5](docs/06-multi-agent-orchestration-and-ecosystem.md#325-openai-agents-sdk--mcp-集成) |
| 多 Agent 评测与调试 | [模块 6 § 3.4](docs/06-multi-agent-orchestration-and-ecosystem.md#34-多-agent-系统的评测监控与调试) |
| MCP + A2A 协同代码 | [模块 6 § 4.2](docs/06-multi-agent-orchestration-and-ecosystem.md#42-mcp-与-a2a-的协同完整代码演示与边界决策) |
| 27 道面试真题 + 高压模拟 | [模块 7](docs/07-interview-preparation-and-enterprise-practice.md) |
| 面试前 1 小时速查表 | [模块 7 § 7.1](docs/07-interview-preparation-and-enterprise-practice.md#71-面试前-1-小时速查表) |
| 公司/级别面试侧重点 | [模块 7 § 1.3](docs/07-interview-preparation-and-enterprise-practice.md#13-不同公司级别的面试侧重点分析) |

---

## 项目文件结构

```
study-mcp/
├── README.md                                          ← 你在这里
├── docs/
│   ├── 01-mcp-basic-cognition-and-core-concepts.md     (1,821 行)
│   ├── 02-mcp-protocol-layer-deep-dive.md              (2,353 行)
│   ├── 03-mcp-server-client-development.md             (2,200 行)
│   ├── 04-mcp-full-stack-project-practice.md           (2,249 行)
│   ├── 05-production-architecture-and-security.md      (1,852 行)
│   ├── 06-multi-agent-orchestration-and-ecosystem.md    (1,329 行)
│   └── 07-interview-preparation-and-enterprise-practice.md (810 行)
└── .gitignore
```
