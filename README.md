<div align="center">

# 📈 FinAgent

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

> 🤖  面向A股短线交易的智能体决策系统
> 多智能体博弈 · 情节记忆 · 自我反思 · 领域增强工具链

## 🧠 项目概述

**FinAgent** 是一个专为 A 股高频决策（尤其针对**打板策略**）设计的 **Agentic AI 系统**。
系统突破了静态的多智能体投票范式，引入**结构化辩论流水线**与**反思式记忆循环**，使系统能够从历史交易片段中持续**自我进化**。

> **范式跃迁**：
> ❌ *「多智能体投票」* → ✅ *「多智能体辩论 + 反思驱动自改进」*

系统融合：

- 🧠 Agent Planning（任务拆解）
- ⚔️ Multi-Agent Debate（多空博弈）
- 🧩 Tool-augmented Execution（工具调用）
- 🧠 Memory + Reflection（复盘与长期记忆）
- 📊 A股特色数据（龙虎榜 / 游资行为）

### 🔬 智能体核心组件

| 组件 | 职能 | 实现细节 |
|-----------|------|-----------------------|
| **Planner Agent（规划智能体）** | 任务拆解 | `ReAct` 循环 + 思维链规划 |
| **Executor Agent（执行智能体）** | 工具编排 | 面向 AkShare 及自定义接口的函数调用网关 |
| **Bull & Bear Agents（多空博弈智能体）** | 对抗分析 | 具有对立提示框架的 LLM 角色 |
| **Judge Agent（裁决智能体）** | 辩论仲裁 | 多准则评分与收敛检测 |
| **Reflection Module（反思模块）** | 情节学习 | 误差分析 → 向量记忆更新 |


---

## 🧠 Core Innovations（核心创新）

### 1️⃣ From Voting → Debate（决策机制升级）

Bull 🐂 vs Bear 🐻 → 多轮博弈 → Judge ⚖️裁决 → 收敛决策
👉 实现：

- 结构化对抗（Structured Debate）
- 多轮反驳（Iterative Rebuttal）
- 决策收敛（Convergence）

### 2️⃣ Planner–Executor Agent Architecture

引入 Agent Planning：
User Query
↓
Planner（任务拆解）
↓
Executor（工具调用）
↓
Analysis Agents（分析）
↓
Debate System（博弈）

### 3️⃣ Multi-Agent Debate System（核心模块）

#### 🐂 Bull Agent（看多）

- 专注上涨逻辑
- 强化趋势 & 资金流

#### 🐻 Bear Agent（看空）

- 专注风险识别
- 强调情绪退潮

#### ⚖️ Judge Agent（裁决）

评估维度：

- 证据强度（Evidence Strength）
- 逻辑一致性（Logical Consistency）
- 反驳质量（Rebuttal Quality）
- 幻觉风险（Hallucination Risk）

### 4️⃣ A-Share Alpha Module（A股增强模块）

#### 📊 龙虎榜分析（游资行为建模）

- 每日龙虎榜数据解析
- 游资席位识别
- 资金流向分析

👉 用于：

- 捕捉短期主力动向
- 提升打板成功率

#### 🚀 打板策略（Limit-Up Strategy）

系统支持：

- 连板识别
- 情绪周期判断
- 龙头股识别

👉 专注：

> 短线交易 / 超短策略 / 情绪驱动市场

### 5️⃣ Reflection & Memory System（复盘进化）

#### 🧠 Agent复盘机制

真实市场走势
↓
Agent预测 vs 实际结果
↓
误差分析
↓
写入长期记忆

| Vector Memory | 相似案例检索 |

---

## ⚙️ Tech Stack

- **Agent Framework**: LangGraph / LangChain
- **Architecture**: Planner–Executor / ReAct
- **Memory**: FAISS + RAG
- **Backend**: Flask / FastAPI
- **Data Source**:
  - AkShare

---

## ⭐ Star

**如果觉得有用，请给个 ⭐ Star 支持一下！**

## ⚠️ 免责声明

本项目仅供学习和研究使用，不构成任何投资建议。股市有风险，投资需谨慎。作者不对使用本项目产生的任何损失负责。

---

