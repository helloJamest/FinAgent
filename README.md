<div align="center">

# 📈 FinAgent

[![GitHub stars](https://img.shields.io/github/stars/helloJamest/FinAgent?style=social)](https://github.com/helloJamest/FinAgent/stargazers)
[![CI](https://github.com/helloJamest/FinAgent/actions/workflows/ci.yml/badge.svg)](https://github.com/helloJamest/FinAgent/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Ready-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/)


**面向 A 股 / 港股 / 美股的智能决策系统**

多智能体博弈 · 情节记忆 · 自我反思 · 领域增强工具链

[**快速开始**](#-快速开始) · [**核心能力**](#-核心能力) · [**WebUI**](#-webui--桌面端) · [**完整文档**](./docs/full-guide.md) · [**FAQ**](./docs/FAQ.md) · [**贡献指南**](./docs/CONTRIBUTING.md)

[English](docs/README_EN.md) · 简体中文 · [繁體中文](docs/README_CHT.md)

</div>

## 🧠 项目概述

**FinAgent** 是一个专为股票高频决策设计的 **Agentic AI 系统**。系统突破了静态的多智能体投票范式，引入**结构化辩论流水线**与**反思式记忆循环**，使系统能够从历史交易片段中持续**自我进化**。

> **范式跃迁**：
> ❌ *「多智能体投票」* → ✅ *「多智能体辩论 + 反思驱动自改进」*

系统融合：
- 🧠 Agent Planning（任务拆解）
- ⚔️ Multi-Agent Debate（多空博弈）
- 🧩 Tool-augmented Execution（工具调用）
- 🧠 Memory + Reflection（复盘与长期记忆）
- 📊 A股特色数据（龙虎榜 / 游资行为）

## ✨ 核心能力

| 模块 | 功能 | 说明 |
|------|------|------|
| AI | 决策仪表盘 | 一句话结论 + 精确买卖点位 + 行动清单 |
| 分析 | 多维度分析 | 技术面 + 筹码分布 + 情绪面 + 实时行情 |
| 市场 | 全球市场 | A股、港股、美股 |
| 搜索 | 智能 autocomplete | 支持代码/名称/拼音/别名匹配，覆盖 A股/港股/美股 |
| 复盘 | 市场综述 | 每日大盘、板块分析、北向资金 |
| 情报 | 公告与资金流 | 上市公司公告 + A股主力资金流向信号 |
| 回测 | AI 回测验证 | 自动评估历史分析准确率，对比 AI 预测与实际走势 |
| 智能体 | 策略对话 | 支持多轮策略问答，内置 11 种交易策略 |
| 通知 | 多渠道推送 | Telegram、Discord、Slack、邮件、企业微信、飞书等 |
| 自动化 | 定时运行 | GitHub Actions 定时执行，零成本 |

### 技术栈 & 数据源

| 类型 | 支持项 |
|------|--------|
| LLM | Gemini、OpenAI 兼容、DeepSeek、通义千问、Claude、Ollama |
| 行情数据 | AkShare、Tushare、Pytdx、Baostock、YFinance、[Longbridge](https://open.longbridge.com/) |
| 新闻搜索 | Tavily、Anspire、SerpAPI、博查、Brave、MiniMax |

## ⚔️ 智能体核心组件

| 组件 | 职能 | 实现细节 |
|-----------|------|-----------------------|
| **Planner Agent** | 任务拆解 | `ReAct` 循环 + 思维链规划 |
| **Executor Agent** | 工具编排 | 面向 AkShare 及自定义接口的函数调用网关 |
| **Bull & Bear Agents** | 对抗分析 | 具有对立提示框架的 LLM 角色 |
| **Judge Agent** | 辩论仲裁 | 多准则评分与收敛检测 |
| **Reflection Module** | 情节学习 | 误差分析 → 向量记忆更新 |

### 1️⃣ 决策机制：从投票到辩论

Bull 🐂 vs Bear 🐻 → 多轮博弈 → Judge ⚖️ 裁决 → 收敛决策

- **结构化对抗**：多轮反驳 + 决策收敛
- **证据驱动**：基于技术面、资金面、情绪面的多维度论证

### 2️⃣ Planner-Executor 架构

```
User Query
    ↓
Planner（任务拆解）
    ↓
Executor（工具调用）
    ↓
Analysis Agents（分析）
    ↓
Debate System（博弈）
```

### 3️⃣ A股增强模块

- **📊 龙虎榜分析**：游资席位识别、资金流向分析、捕捉短期主力动向
- **🚀 打板策略**：连板识别、情绪周期判断、龙头股识别

### 4️⃣ 复盘进化系统

```
真实市场走势
    ↓
Agent 预测 vs 实际结果
    ↓
误差分析 → 写入长期记忆 → 相似案例检索
```

## 🚀 快速开始

### 方式一：GitHub Actions（推荐，零成本）

**无需服务器，自动每日运行！**

#### 1. Fork 本仓库

点击右上角 `Fork` 按钮

#### 2. 配置 Secrets

进入 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`

**AI 模型配置（任选其一）**

| Secret 名称 | 说明 | 必需 |
|------------|------|:----:|
| `GEMINI_API_KEY` | 从 [Google AI Studio](https://aistudio.google.com/) 获取 | ✅* |
| `OPENAI_API_KEY` | OpenAI 兼容 API Key（支持 DeepSeek、通义等） | 可选 |
| `OPENAI_BASE_URL` | OpenAI 兼容 API 地址 | 可选 |
| `OPENAI_MODEL` | 模型名称 | 可选 |

> *配置 `GEMINI_API_KEY`、`OPENAI_API_KEY` 或 Ollama 本地服务之一即可

**股票列表配置**

| Secret 名称 | 说明 | 必需 |
|------------|------|:----:|
| `STOCK_LIST` | 自选股代码，如 `600519,AAPL,hk00700` | ✅ |

> **代码格式**：A股 `600519` | 港股 `hk00700` | 美股 `AAPL`

**通知渠道（至少配置一个）**

| Secret 名称 | 说明 |
|------------|------|
| `TELEGRAM_BOT_TOKEN` | Telegram 机器人 Token |
| `TELEGRAM_CHAT_ID` | Telegram 聊天 ID |
| `DISCORD_WEBHOOK_URL` | Discord Webhook URL |
| `WECHAT_WEBHOOK_URL` | 企业微信 Webhook |
| `FEISHU_WEBHOOK_URL` | 飞书 Webhook |
| `EMAIL_SENDER` / `EMAIL_PASSWORD` | 邮件推送 |

完整通知渠道列表见 [完整指南](docs/full-guide.md)

#### 3. 启用 Actions

进入 `Actions` 标签 → 点击 `I understand my workflows, go ahead and enable them`

#### 4. 手动测试

`Actions` → `Daily Stock Analysis` → `Run workflow`

### 方式二：本地运行

```bash
# 1. 克隆仓库
git clone https://github.com/helloJamest/FinAgent.git
cd FinAgent

# 2. 安装依赖
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 填入 API Key 和股票代码

# 4. 运行
python main.py                    # 单次分析
python main.py --schedule         # 定时模式（每日 18:00）
python main.py --stocks 600519    # 指定股票
python main.py --serve-only       # 启动 WebUI + API
```

## 🖥️ WebUI / 桌面端

### Web 管理界面

启动 `python main.py --serve-only` 后访问 `http://localhost:8000`

- 📝 **配置管理** — 在线编辑 watchlist、AI 模型、通知渠道
- 🚀 **一键分析** — 触发单股/批量分析，实时查看进度
- 📊 **回测验证** — 评估历史分析准确率
- 🤖 **策略对话** — 多轮 Agent 聊天，内置 11 种策略
- 🌗 **深色/浅色主题** — 自动适配系统偏好
- 🔐 **认证保护** — 可选 Web 管理端密码

### 桌面应用

项目支持 Electron 桌面端打包，适用于 Windows/macOS：

```bash
cd apps/finagent-web && npm ci && npm run build
cd ../finagent-desktop && npm install && npm run build
```

## 📖 项目结构

```
FinAgent/
├── main.py              # 主程序入口
├── server.py            # FastAPI 服务入口
├── src/                 # 核心业务逻辑
│   ├── analyzer.py      # AI 分析器
│   ├── config.py        # 配置管理
│   ├── notification.py  # 消息推送
│   ├── market_analyzer.py  # 市场分析
│   └── agent/           # 智能体模块
├── data_provider/       # 多数据源适配器
├── bot/                 # 机器人交互模块
├── api/                 # FastAPI API 服务
├── apps/
│   ├── finagent-web/    # React 前端
│   └── finagent-desktop/# Electron 桌面端
├── strategies/          # 内置交易策略
├── docker/              # Docker 配置
├── docs/                # 文档
└── .github/workflows/   # GitHub Actions
```

## 📖 文档

- [完整配置与部署指南](docs/full-guide.md)
- [常见问题 FAQ](docs/FAQ.md)
- [Docker 部署指南](docs/DEPLOY.md)
- [WebUI 云端部署](docs/deploy-webui-cloud.md)
- [桌面端打包指南](docs/desktop-package.md)
- [LLM 模型配置指南](docs/LLM_CONFIG_GUIDE.md)
- [贡献指南](docs/CONTRIBUTING.md)

## 🤝 参与贡献

欢迎各种形式的贡献！详见 [贡献指南](docs/CONTRIBUTING.md)

## 📄 许可证

本项目基于 [MIT License](LICENSE) 开源

## ⭐ Star 历史

**如果觉得有用，请给个 ⭐ Star 支持一下！**

<a href="https://star-history.com/#helloJamest/FinAgent&Date">
 <picture>
   <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=helloJamest/FinAgent&type=Date&theme=dark" />
   <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=helloJamest/FinAgent&type=Date" />
   <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=helloJamest/FinAgent&type=Date" />
 </picture>
</a>

## ⚠️ 免责声明

本项目仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。作者不对使用本项目产生的任何损失负责。

## 🙏 致谢

- [DSA](https://github.com/ZhuLinsen/daily_stock_analysis) - daily_stock_analysis項目
- [AkShare](https://github.com/akfamily/akshare) - 股票数据源
- [Google Gemini](https://ai.google.dev/) - AI 分析引擎
- [Tavily](https://tavily.com/) - 新闻搜索 API
- 所有为项目做出贡献的开发者

## 📞 联系方式

- GitHub Issues: [报告 Bug 或提出建议](https://github.com/helloJamest/FinAgent/issues)
- Discussions: [参与讨论](https://github.com/helloJamest/FinAgent/discussions)
