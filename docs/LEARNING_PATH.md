# FinAgent 项目学习路径

> 面向新成员的系统性导览，覆盖主流程、Agent 调用链、数据流、优化方向等。

---

## 一、项目总览

**FinAgent** 是一个面向 **A 股短线交易**（尤其打板策略）的 **Agentic AI 决策系统**。核心范式：

```
用户查询 / 定时触发
    ↓
数据获取 (多数据源 fallback)
    ↓
技术分析 (趋势/筹码)
    ↓
Agent 决策 (单 Agent ReAct 或 多 Agent 编排)
    ↓
生成报告 (决策仪表盘 JSON)
    ↓
通知推送 (多渠道)
```

### 架构分层

| 层级 | 目录 | 职责 |
|------|------|------|
| 入口层 | `main.py`, `server.py` | CLI/定时/Web/Bot 启动 |
| 编排层 | `src/core/pipeline.py` | 个股分析主流水线 |
| Agent 层 | `src/agent/` | ReAct 循环、多 Agent 编排、工具系统、技能系统 |
| 分析层 | `src/analyzer.py` | LLM 调用（LiteLLM 统一多模型）、报告生成 |
| 数据层 | `data_provider/` | 多数据源策略（AkShare/BaoStock/Tushare/Longbridge/yFinance 等） |
| 搜索层 | `src/search_service.py` | 多搜索引擎（Bocha/Tavily/Brave/SerpAPI/SearXNG） |
| 通知层 | `src/notification.py` + `src/notification_sender/` | 多渠道推送 |
| API 层 | `api/` | FastAPI REST 服务 |
| Bot 层 | `bot/` | 钉钉/飞书/Discord 机器人 |
| 前端层 | `apps/dsa-web/` | Vue 3 Web 前端 |
| 桌面层 | `apps/dsa-desktop/` | Electron 桌面端 |

---

## 二、主流程路径（从入口到输出）

### 2.1 CLI 单次分析流程

```
main.py (入口)
  ├── parse_arguments()          # 解析命令行参数
  ├── get_config()               # 加载 .env 配置
  ├── setup_logging()            # 初始化日志
  │
  └── run_full_analysis()        # 完整分析流程
        │
        ├── StockAnalysisPipeline.run()     # 核心流水线
        │     │
        │     ├── DataFetcherManager        # 1. 获取行情/K线/筹码数据
        │     │     ├── AkShareFetcher     #    主力数据源
        │     │     ├── BaoStockFetcher    #    备用数据源
        │     │     ├── TushareFetcher     #    备用数据源
        │     │     ├── LongbridgeFetcher  #    港股/美股
        │     │     └── yFinanceFetcher    #    美股
        │     │
        │     ├── StockTrendAnalyzer        # 2. 技术分析（MA/MACD/RSI/筹码）
        │     │
        │     ├── SearchService             # 3. 新闻搜索（多引擎 fallback）
        │     │
        │     ├── GeminiAnalyzer.analyze()  # 4. LLM 分析生成报告
        │     │     └── LiteLLM Router      #    多模型路由（Gemini/Anthropic/OpenAI 等）
        │     │
        │     ├── NotificationService       # 5. 通知推送
        │     │     ├── WeChatSender       #    企业微信
        │     │     ├── FeishuSender       #    飞书
        │     │     ├── TelegramSender     #    Telegram
        │     │     ├── EmailSender        #    邮件
        │     │     └── ...                #    其他渠道
        │     │
        │     └── FeishuDocManager          # 6. 飞书云文档生成
        │
        └── run_market_review()      # 大盘复盘（如果启用）
```

**入口文件**: `main.py`
**流水线文件**: `src/core/pipeline.py` — `StockAnalysisPipeline.run()`
**分析引擎**: `src/analyzer.py` — `GeminiAnalyzer.analyze()`

### 2.2 定时任务模式

```
main.py --schedule
    ↓
run_with_schedule()              # src/scheduler.py
    ↓
scheduled_task()
    → _reload_runtime_config()   # 热加载最新配置
    → run_full_analysis()        # 执行完整分析
```

同时可启动后台 `EventMonitor`（`src/agent/events.py`）进行价格监控。

### 2.3 API 服务模式

```
main.py --serve
    ↓
start_api_server()               # 后台线程启动 FastAPI
    ↓
api/app.py → api/v1/router.py    # 路由注册
    ↓
端点：
  /api/v1/analysis/analyze       # 触发分析
  /api/v1/stocks/*               # 股票查询
  /api/v1/history/*              # 历史记录
  /api/v1/backtest/*             # 回测
  /api/v1/portfolio/*            # 组合管理
  /api/v1/system_config/*        # 系统配置
```

**API 入口**: `api/app.py`, `api/v1/router.py`
**认证中间件**: `api/middlewares/auth.py`

### 2.4 Bot 交互模式

```
钉钉/飞书 Stream 连接
    ↓
bot/handler.py                   # 消息分发
    ↓
bot/dispatcher.py                # 命令路由
    ↓
bot/commands/
  ├── analyze.py                 # /analyze 个股分析
  ├── chat.py                    # /chat 自由对话
  ├── ask.py                     # /ask 快捷查询
  ├── market.py                  # /market 行情查询
  ├── batch.py                   # /batch 批量分析
  ├── research.py                # /research 深度调研
  └── ...
    ↓
build_agent_executor()           # 构建 Agent 执行器
    ↓
AgentExecutor / AgentOrchestrator
```

**Bot 入口**: `bot/handler.py`
**命令注册**: `bot/dispatcher.py`
**平台适配**: `bot/platforms/`（钉钉/飞书/Discord）

---

## 三、Agent 调用路径（核心）

### 3.1 两种 Agent 架构

系统通过配置 `AGENT_ARCH` 切换：

| 模式 | 配置值 | 实现 | 说明 |
|------|--------|------|------|
| 单 Agent | `single`（默认） | `AgentExecutor` | 经典 ReAct 循环，一个 LLM 完成所有工作 |
| 多 Agent | `multi` | `AgentOrchestrator` | 多智能体流水线，分工协作 |

**构建入口**: `src/agent/factory.py` — `build_agent_executor()`

### 3.2 单 Agent 路径（`AgentExecutor`）

```
AgentExecutor.run(task)
    │
    ├── 1. 构建 System Prompt
    │     ├── 市场角色 (A股/港股/美股)
    │     ├── 技能指令 (激活的交易技能)
    │     └── 输出语言
    │
    ├── 2. 构建消息列表 [system, user]
    │
    ├── 3. run_agent_loop()    # src/agent/runner.py
    │     │
    │     ├── for step in range(max_steps):
    │     │     ├── LLM call with tool declarations
    │     │     ├── if tool_calls:
    │     │     │     ├── ToolRegistry.execute()   # 并行执行
    │     │     │     ├── 结果缓存 (stock_code 归一化)
    │     │     │     └── 不可重试工具缓存
    │     │     └── else:
    │     │         └── stream_final_answer()      # 流式输出
    │     │
    │     └── RunLoopResult
    │
    └── 4. 解析 Dashboard JSON (dashboard 模式) 或返回文本 (chat 模式)
```

**核心文件**:
- `src/agent/executor.py` — `AgentExecutor` 类，构建 prompt 和适配结果
- `src/agent/runner.py` — `run_agent_loop()`, 共享 ReAct 循环实现
- 工具调用并行化，支持 timeout 和缓存

### 3.3 多 Agent 路径（`AgentOrchestrator`）

```
AgentOrchestrator.run(task)
    │
    └── _execute_pipeline(ctx)
          │
          ├── _build_agent_chain(ctx)    # 根据 mode 构建 Agent 链
          │     │
          │     ├── quick:    [Technical, Decision]
          │     ├── standard: [Technical, Intel, Decision]
          │     ├── full:     [Technical, Intel, Risk, Decision]
          │     └── specialist: [Technical, Intel, Risk, Specialist*, Decision]
          │
          ├── 顺序执行各阶段 Agent
          │     │
          │     ├── TechnicalAgent       # 技术面分析
          │     ├── IntelAgent           # 情报收集
          │     ├── RiskAgent            # 风险评估
          │     ├── SkillAgent (xN)      # 技能专家（最多 3 个）
          │     └── DecisionAgent        # 最终决策
          │
          ├── _aggregate_skill_opinions()  # 技能意见聚合
          ├── _apply_risk_override()       # 风控否决/降级
          └── _resolve_final_output()      # 生成最终 Dashboard
```

**模式对比**:

```
quick (最快, ~2 LLM 调用):
  Technical → Decision

standard (默认):
  Technical → Intel → Decision

full (最全面):
  Technical → Intel → Risk → Decision

specialist (专家模式):
  Technical → Intel → Risk → [SkillAgent x1-3] → Decision
```

**核心文件**:
- `src/agent/orchestrator.py` — `AgentOrchestrator` 主类
- `src/agent/agents/technical_agent.py` — 技术分析 Agent
- `src/agent/agents/intel_agent.py` — 情报收集 AGENT
- `src/agent/agents/risk_agent.py` — 风险评估 AGENT
- `src/agent/agents/decision_agent.py` — 决策 AGENT
- `src/agent/agents/portfolio_agent.py` — 组合管理 AGENT
- `src/agent/skills/skill_agent.py` — 技能专家 AGENT

### 3.4 Agent 间数据流

```
AgentContext (共享上下文)
  ├── query: 用户查询
  ├── stock_code: 股票代码
  ├── stock_name: 股票名称
  ├── opinions: 各 Agent 的意见 (StageResult)
  ├── risk_flags: 风险标记
  └── data: 键值数据存储
        ├── realtime_quote
        ├── daily_history
        ├── chip_distribution
        ├── trend_result
        ├── news_context
        ├── intel_opinion
        └── final_dashboard
```

### 3.5 工具系统

```
ToolRegistry (工具注册中心)
    │
    ├── 注册 (@tool 装饰器)
    │     ├── src/agent/tools/data_tools.py      # 数据工具
    │     ├── src/agent/tools/analysis_tools.py   # 分析工具
    │     ├── src/agent/tools/search_tools.py     # 搜索工具
    │     ├── src/agent/tools/market_tools.py     # 市场工具
    │     └── src/agent/tools/backtest_tools.py   # 回测工具
    │
    ├── 执行 (ToolRegistry.execute)
    │     ├── 参数标准化 (stock_code 归一化)
    │     ├── 缓存 (相同参数跳过)
    │     ├── 并行执行 (ThreadPoolExecutor, 最多 5 并发)
    │     └── 超时处理
    │
    └── 工具调用流程
          LLM 返回 tool_calls
            ↓
          ToolRegistry.execute(tool_name, **args)
            ↓
          结果返回给 LLM 作为下一条消息
```

**可用工具** (部分):
- `get_realtime_quote` — 实时行情
- `get_daily_history` — 历史 K 线
- `analyze_trend` — 技术指标分析
- `get_chip_distribution` — 筹码分布
- `search_stock_news` — 新闻搜索
- `search_comprehensive_intel` — 综合情报搜索
- `get_market_indices` — 市场概览
- `get_sector_rankings` — 行业板块分析
- `get_skill_backtest_summary` — 技能回测概览
- `get_stock_backtest_summary` — 个股回测

### 3.6 技能系统（Skill System）

```
SkillManager
    │
    ├── 加载技能
    │     ├── load_builtin_skills()    # 内置技能（YAML 定义）
    │     └── load_custom_skills(dir)  # 自定义技能目录
    │
    ├── 激活技能
    │     └── activate(skill_ids)      # 运行时激活
    │
    └── 技能路由 (SkillRouter)
          └── select_skills(ctx)       # 根据上下文自动选择适用技能
```

**技能执行链路** (specialist 模式):
```
TechnicalAgent 完成
    ↓
SkillRouter 根据技术面结果选择适用技能
    ↓
创建 SkillAgent 实例（最多 3 个）
    ↓
每个 SkillAgent 独立执行，产生 opinion
    ↓
SkillAggregator 聚合为 consensus
    ↓
写入 AgentContext.opinions
    ↓
DecisionAgent 参考所有意见做最终决策
```

**核心文件**:
- `src/agent/skills/base.py` — `SkillManager`
- `src/agent/skills/router.py` — `SkillRouter`
- `src/agent/skills/skill_agent.py` — `SkillAgent`
- `src/agent/skills/aggregator.py` — `SkillAggregator`
- `src/agent/skills/defaults.py` — 默认技能策略

---

## 四、数据流与降级机制

### 4.1 数据获取链路

```
DataFetcherManager (策略管理器)
    │
    ├── 主数据源: AkShare (A 股)
    ├── 备用源 1: BaoStock (A 股)
    ├── 备用源 2: Tushare (A 股)
    ├── 港股: Longbridge
    ├── 美股: yFinance / Longbridge
    └── 实时: efinance / pytdx / TickFlow
```

**降级策略**:
1. 每个 Fetcher 内置流控（Rate Limit）
2. 失败自动切换到下一个数据源
3. 指数退避重试
4. 数据字段标准化（`STANDARD_COLUMNS`）

### 4.2 LLM 调用链路

```
LiteLLM Router (统一入口)
    │
    ├── Channel 模式 (推荐): 通过 YAML 配置多个 deployment
    │     └── simple-shuffle 策略负载均衡
    │
    └── Legacy 模式: 多 API Key 列表
          └── simple-shuffle 策略

模型回退:
  litellm_model → litellm_fallback_models[0] → ...
```

### 4.3 搜索服务链路

```
SearchService
    │
    ├── Bocha API
    ├── Tavily API
    ├── Brave Search
    ├── SerpAPI
    ├── SearXNG (自建实例)
    └── Minimax (备选)
```

多 Key 轮转 + 重试 + 缓存。

---

## 五、关键设计模式

| 模式 | 位置 | 说明 |
|------|------|------|
| **策略模式** | `data_provider/` | 多数据源策略管理器，自动切换 |
| **工厂模式** | `src/agent/factory.py` | 统一构建 AgentExecutor / AgentOrchestrator |
| **ReAct 模式** | `src/agent/runner.py` | Reasoning + Action 交替循环 |
| **观察者模式** | `progress_callback` | 贯穿全链路的进度回调 |
| **Pipeline 模式** | `src/core/pipeline.py` | 阶段式流水线 |
| **多 Agent 编排** | `src/agent/orchestrator.py` | 阶段链 + 意见聚合 + 风控否决 |

---

## 六、优化方向

### 6.1 性能优化

| 方向 | 现状 | 优化建议 |
|------|------|----------|
| **工具缓存** | 已有 stock_code 归一化缓存 | 扩展跨 session 缓存（Redis），避免重复数据获取 |
| **LLM 调用** | 已有 model fallback 和 Router | 引入请求合并（batching），减少 API 调用次数 |
| **数据预取** | 流水线串行获取 | 行情/K线/筹码可并行预取 |
| **并发控制** | ThreadPoolExecutor 控制个股并发 | Agent 内部工具调用也可限制最大并发数 |
| **Agent 超时** | 已有 wall-clock timeout | 支持 per-stage budget 动态调整 |

### 6.2 架构优化

| 方向 | 现状 | 优化建议 |
|------|------|----------|
| **Agent 并行** | 多 Agent 串行执行 | 独立 Agent 可并行（如 IntelAgent 和 RiskAgent 无依赖） |
| **状态管理** | AgentContext 内存传递 | 引入持久化状态存储，支持跨 session 恢复 |
| **工具解耦** | ToolRegistry 全局单例 | 支持 per-agent 工具子集，减少 prompt 膨胀 |
| **Prompt 管理** | 硬编码在 executor.py | 提取为模板文件（Jinja2/YAML），支持热更新 |

### 6.3 功能扩展

| 方向 | 说明 |
|------|------|
| **RL-based Trading Agent** | README 标注的 Future Work，强化学习驱动交易 |
| **实盘交易接口** | 对接券商 API，从分析到执行闭环 |
| **多模态分析** | K 线图视觉理解 + 新闻 NLP |
| **Agent 并行调度** | 当前 specialist 模式最多 3 个 SkillAgent，可扩展为 DAG 编排 |
| **记忆系统增强** | 已有 `src/agent/memory.py`，可扩展为向量数据库 + 案例检索 |

### 6.4 代码质量

| 方向 | 说明 |
|------|------|
| **测试覆盖** | 已有 pytest 测试，可扩展网络依赖测试 (`pytest -m network`) |
| **类型标注** | 部分文件缺少类型提示 |
| **文档完善** | 已有 AGENTS.md/README.md，可补充 API 文档和部署文档 |
| **CI/CD** | 已有 GitHub Actions，可扩展安全扫描和性能测试 |

### 6.5 成本优化

| 方向 | 说明 |
|------|------|
| **LLM 成本控制** | AgentOrchestrator 的 max_steps 可能产生大量 LLM 调用，建议加入 token budget 限制 |
| **数据源成本** | 部分数据源（Tushare/Longbridge）有 API 调用限制，建议增加本地缓存层 |
| **搜索成本控制** | 新闻搜索可引入缓存和增量更新策略 |

---

## 七、学习路径建议

### 第一阶段：理解主流程（1-2 天）

1. 阅读 `main.py` — 理解入口和命令行参数
2. 阅读 `src/core/pipeline.py` — 理解 StockAnalysisPipeline 完整流程
3. 阅读 `src/analyzer.py` — 理解 LLM 分析过程和报告格式
4. 运行 `python main.py --debug --dry-run` — 观察数据获取流程

### 第二阶段：理解 Agent 系统（2-3 天）

1. 阅读 `src/agent/factory.py` — 理解 Agent 构建
2. 阅读 `src/agent/executor.py` — 理解单 Agent ReAct 循环
3. 阅读 `src/agent/runner.py` — 理解核心执行循环
4. 阅读 `src/agent/orchestrator.py` — 理解多 Agent 编排
5. 阅读 `src/agent/tools/registry.py` — 理解工具系统
6. 阅读各 Agent 文件 (`src/agent/agents/*.py`)

### 第三阶段：理解数据与外部服务（1-2 天）

1. 阅读 `data_provider/base.py` — 理解数据源策略
2. 阅读 `data_provider/akshare_fetcher.py` — 理解主力数据源
3. 阅读 `src/search_service.py` — 理解搜索服务
4. 阅读 `src/notification.py` — 理解通知系统

### 第四阶段：理解 API 与 Bot（1-2 天）

1. 阅读 `api/app.py` 和 `api/v1/router.py` — 理解 API 结构
2. 阅读 `bot/dispatcher.py` — 理解命令系统
3. 阅读 `bot/platforms/dingtalk_stream.py` — 理解 Stream 模式

### 第五阶段：扩展与优化（持续）

1. 添加自定义技能 (`src/agent/skills/`)
2. 添加自定义工具 (`src/agent/tools/`)
3. 修改 Prompt 模板
4. 性能调优

---

## 八、关键配置项速查

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `STOCK_LIST` | 分析股票列表 | `.env` 配置 |
| `LITELLM_MODEL` | 主 LLM 模型 | 未设置 |
| `AGENT_ARCH` | Agent 架构 | `single` |
| `AGENT_ORCHESTRATOR_MODE` | 编排模式 | `standard` |
| `AGENT_MAX_STEPS` | 最大步骤 | `10` |
| `AGENT_SKILL_DIR` | 自定义技能目录 | 未设置 |
| `AGENT_SKILLS` | 激活技能列表 | 默认内置 |
| `MAX_WORKERS` | 最大并发线程 | 配置值 |
| `SCHEDULE_TIME` | 定时执行时间 | `18:00` |
| `MARKET_REVIEW_ENABLED` | 大盘复盘 | 配置值 |
| `REPORT_TYPE` | 报告类型 | `simple` |
| `REPORT_LANGUAGE` | 报告语言 | `zh` |

---

## 九、核心文件索引

### 入口
- `main.py` — CLI 入口，调度所有模式
- `server.py` — FastAPI 服务入口

### 核心流程
- `src/core/pipeline.py` — 主流水线
- `src/core/market_review.py` — 大盘复盘
- `src/core/trading_calendar.py` — 交易日历
- `src/core/backtest_engine.py` — 回测引擎

### Agent
- `src/agent/factory.py` — Agent 工厂
- `src/agent/executor.py` — 单 Agent 执行器
- `src/agent/orchestrator.py` — 多 Agent 编排器
- `src/agent/runner.py` — ReAct 循环核心
- `src/agent/llm_adapter.py` — LLM 适配层
- `src/agent/memory.py` — 记忆系统
- `src/agent/protocols.py` — 协议定义

### Agent 子模块
- `src/agent/agents/` — 各专用 Agent
- `src/agent/tools/` — 工具定义
- `src/agent/skills/` — 技能系统
- `src/agent/strategies/` — 策略系统
- `src/agent/conversation.py` — 对话管理

### 数据
- `data_provider/` — 数据源
- `src/search_service.py` — 搜索服务
- `src/stock_analyzer.py` — 技术分析器

### 服务
- `src/analyzer.py` — LLM 分析
- `src/notification.py` — 通知服务
- `src/services/` — 业务服务层
- `src/repositories/` — 数据访问层

### API
- `api/v1/endpoints/` — API 端点
- `api/v1/schemas/` — API Schema

### Bot
- `bot/dispatcher.py` — 命令分发
- `bot/commands/` — 命令实现
- `bot/platforms/` — 平台适配
