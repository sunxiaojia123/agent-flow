# 架构设计

> 最后更新：2026-05-29

## 概述

基于 LangManus 层级化多智能体架构的交易 Demo。核心能力：

1. **Supervisor 循环调度** — Supervisor 通过结构化输出 (JSON) 动态决定每一步，非固定流水线
2. **渐进式技能加载** — Supervisor prompt 只含技能摘要，需要时通过工具加载完整 SKILL.md
3. **多轮工具调用** — 先用户画像 → 再加载供应商技能 → 查库存 → 报价格 → 问物流 → 生成卡片
4. **流式输出** — SSE 推送 meta / text / popup / card 多种事件
5. **内外技能分离** — public/ 内部技能 (5供应商+1用户画像)，custom/ 外部技能 (可热加载)

## 技术栈

| 层 | 技术 |
|---|---|
| 编排引擎 | LangGraph + MemorySaver checkpointer |
| HTTP 框架 | FastAPI + SSE streaming |
| LLM | langchain-openai (DeepSeek 等兼容接口) |
| 数据模型 | Pydantic v2 |
| 前端 | 单页 HTML + 原生 JS (零依赖) |
| 技能存储 | SKILL.md (YAML frontmatter + Markdown body) |

## 架构概览

```
静态文件 (static/)
    │
    ▼
FastAPI 入口 (app/main.py)
    │
    ▼
SSE 流式端点 (/api/v1/chat/stream)
    │
    ▼
LangGraph 图 (app/graph/)
    │
    ├── Coordinator    ── 入口分流 (闲聊直接回复 / 交易→Planner)
    ├── Planner        ── 结构化 JSON 执行计划
    ├── Supervisor     ── 核心循环决策 (structured JSON output)
    ├── ToolNode       ── 工具分发执行
    └── Formatter      ── 最终格式化 (text/popup/card)
    │
    ▼
Skill 系统 (skills/ + app/skills/)
    ├── public/   (内部技能) ── 5供应商 + 1用户画像
    └── custom/   (外部技能) ── 可热加载
    │
    ▼
Tool 工具 (app/tools/)
    ├── load_skill_detail ── 渐进式加载 SKILL.md
    ├── get_api_schema   ── 获取 API 参数结构
    ├── call_api         ── 执行 mock API 调用
    └── get_user_context ── 加载用户画像
```

## Graph 结构

参考 LangManus 的 7 Agent 架构，简化为 5 节点：

```
START
  │
  ▼
coordinator ──── (chitchat) ──→ formatter_text ──→ END
  │
  │ (trading intent → Command(goto="planner"))
  ▼
planner ──→ Command(goto="supervisor")
  │
  ▼
supervisor ←──────────────────────────┐
  │                                   │
  │ Command(goto="tools")             │ Command(goto="supervisor")
  │   update={tool_name, tool_args}   │
  ▼                                   │
tools ────────────────────────────────┘
  │
  ├── Command(goto="formatter_text")  → formatter_text → END
  ├── Command(goto="formatter_popup") → formatter_popup → END
  └── Command(goto="formatter_card")  → formatter_card → END
```

**关键**: 所有边通过 `Command(goto=...)` 动态决定，与 LangManus 一致。

### 节点说明

| 节点 | 类型 | 职责 | 输出路由 |
|------|------|------|----------|
| `coordinator` | 路由 | LLM 判断意图: 闲聊/交易 | `planner` 或 `formatter_text` |
| `planner` | 处理 | 结构化 JSON 计划 (需要哪些技能/API) | `supervisor` |
| `supervisor` | 核心循环 | 结构化输出决策: tools/formatter_text/formatter_popup/formatter_card | 动态 4 路 |
| `tools` | 工具执行 | 分发执行 4 种工具 | `supervisor` (loop back) |
| `formatter_text` | 终端 | 输出文字回复 | END |
| `formatter_popup` | 终端 | 输出弹窗表单 | END |
| `formatter_card` | 终端 | 输出结果卡片 | END |

## LangManus 对照

| LangManus | 本系统 | 说明 |
|-----------|--------|------|
| Coordinator | **coordinator** | 入口分流 (闲聊直接回复，交易→Planner) |
| Planner | **planner** | 制定结构化 JSON 计划 |
| Supervisor | **supervisor** | 核心循环，structured JSON output 路由 |
| Researcher/Coder/Browser | **tools** | 执行 Supervisor 指定的工具 |
| Reporter | **formatter** | 格式化最终输出 (text/popup/card) |

## State 设计

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # 完整对话 + 工具调用历史
    conversation_id: str
    plan: dict | None                         # Planner 的结构化计划
    supervisor_decision: dict | None          # 最近一次 Supervisor 路由决策
    coordinator_reply: str | None             # Coordinator 直接回复内容
    final_action: str                         # "text" | "popup" | "card" | ""
    popup_message: str                        # 弹窗提示文案
    popup_fields: list[dict]                  # 弹窗字段定义
    card_type: str                            # "trade" | "selection"
    card_data: dict                           # 卡片数据
```

**关键**: messages 包含完整历史，不做上下文压缩，Supervisor 读取完整历史做决策。

## 技能系统

### SKILL.md 格式 (标准 Markdown + YAML frontmatter)

每个技能目录包含一个 `SKILL.md`:

```markdown
---
name: shagang-supplier
display_name: 沙钢供应商
description: 沙钢集团简介
category: supplier
version: "1.0"
---

## 公司信息   (Key-Value, 解析为 company_info)
- 名称: 沙钢集团有限公司
- 地区: 华东
- 主营产品: 螺纹钢、线材

## API 接口
### check_inventory        (解析为 ApiEndpoint)
- **描述**: 查询库存
- **方法**: GET
- **参数**:               (解析为 ApiParam[])
  - product_category: string (必填) - 产品品类
- **Mock 返回**:          (解析为 mock_response)
  ```json
  {"available": true, "stock": 3000}
  ```

## 执行说明              (解析为 execution_guide)
1. 先查库存 → 再报价格 → 后问物流
```

### 双源加载

| 来源 | 目录 | 说明 |
|------|------|------|
| 内部技能 | `skills/public/` | 系统内置，启动时自动加载 |
| 外部技能 | `skills/custom/` | 可热加载 (POST /api/v1/skills/reload) |

### 6 个内置技能

| 技能 | 类别 | API | 说明 |
|------|------|-----|------|
| `user-profile` | internal | get_profile, get_history | 用户画像 + 采购历史 |
| `shagang-supplier` | supplier | check_inventory, get_quote, check_logistics | 沙钢集团 (螺纹钢/线材/热轧) |
| `ganglian-supplier` | supplier | check_inventory, get_quote, check_logistics | 钢联贸易 (上海本地) |
| `huadong-supplier` | supplier | check_inventory, get_quote, check_logistics | 华东钢材 (中厚板/热轧/冷轧) |
| `xingcheng-supplier` | supplier | check_inventory, get_quote, check_logistics | 兴澄特钢 (不锈钢/镀锌板) |
| `nanjing-supplier` | supplier | check_inventory, get_quote, check_logistics | 南京钢铁 (H型钢/工字钢/槽钢) |

### 工具定义

Supervisor 可调度的 4 种工具:

| 工具 | 参数 | 功能 |
|------|------|------|
| `load_skill_detail` | `skill_name: str` | 渐进式加载完整 SKILL.md |
| `get_api_schema` | `skill_name, api_name` | 获取 API 参数 schema |
| `call_api` | `skill_name, api_name, params` | 执行 mock API 调用 |
| `get_user_context` | 无 | 加载用户画像+采购历史 |

## SSE 事件模型

| event | 来源 | 携带数据 |
|-------|------|----------|
| `meta` | 各节点 start/end | `{node, message, status}` — 调度进度 |
| `meta` (tool_planned) | supervisor 结束后 | `{phase, tool_name, tool_args}` — 展示 Supervisor 决策 |
| `meta` (supervisor_end) | supervisor 结束后 | `{phase, next, reasoning}` — 结束决策信息 |
| `text_delta` | formatter_text | `{content}` — 流式文字 |
| `text_done` | 流结束 | `{}` |
| `popup` | formatter_popup | `{fields, message}` — 弹窗表单 |
| `card` | formatter_card | `{card_type, data}` — 结果卡片 |
| `error` | 异常 | `{code, message}` |
| `done` | 完成 | `{conversation_id}` |

## 完整执行流程示例

```
用户: "我想在上海买500吨螺纹钢"

coordinator → LLM 判断 "handoff_to_planner" → goto planner
  [meta: coordinator → planner]

planner → {"thought": "...", "steps": [{"skill": "user-profile", ...}, {"skill": "shagang-supplier", ...}]} → goto supervisor
  [meta: planner → supervisor]

supervisor(1) → {"next": "tools", "tool_name": "get_user_context"} → goto tools
  [meta: tool_planned → get_user_context]

tools → 执行 get_user_context → 返回用户画像数据 → goto supervisor
  [meta: tools → supervisor]

supervisor(2) → {"next": "tools", "tool_name": "load_skill_detail", "tool_args": {"skill_name": "shagang-supplier"}} → goto tools
  [meta: tool_planned → load_skill_detail(shagang-supplier)]

tools → 加载沙钢 SKILL.md → 返回 API 列表 + 执行说明 → goto supervisor

supervisor(3) → {"next": "tools", "tool_name": "call_api", "tool_args": {"skill_name": "shagang-supplier", "api_name": "check_inventory", "params": {...}}} → goto tools
  [meta: tool_planned → call_api]

tools → mock 返回库存数据 → goto supervisor

supervisor(4) → {"next": "formatter_card", "card_type": "trade", "card_data": {...}} → goto formatter_card
  [meta: supervisor_end → formatter_card]

formatter_card → [card event] → END
  [done]
```

## 关键设计决策

1. **Command(goto) 动态路由** — 不预设边，每个节点通过 `Command(goto=...)` 决定下一步，与 LangManus 完全一致
2. **Supervisor 结构化输出** — 标准 JSON 格式路由决策，支持嵌套 JSON 提取
3. **渐进式加载** — Supervisor prompt 只有技能摘要，按需 `load_skill_detail` 获取完整内容
4. **ToolNode 统一返回 Supervisor** — 执行-决策循环，Supervisor 评估结果后决定继续还是结束
5. **全量消息传递** — 不做上下文压缩 (messages 最多保留 20 条)，Supervisor 读取完整历史做决策
6. **Mock 模式** — `call_api` 直接解析 SKILL.md 中的 mock 返回示例，不发起真实 HTTP 请求
7. **技能驱动执行** — SKILL.md 中的"执行说明"指导 Supervisor 如何组合调用 API

## 扩展点

- **模型替换**: `LLM_MODEL` 环境变量，支持 Claude/GPT-4 等更强大的模型以改善 JSON 输出稳定性
- **新增供应商技能**: 在 `skills/public/` 或 `skills/custom/` 下创建新的 SKILL.md，调用 `POST /api/v1/skills/reload` 热加载
- **真实 API 对接**: 修改 `app/tools/api_tools.py` 中的 `call_api` 函数，发起真实 HTTP 请求
- **上下文压缩**: 当 messages 超过阈值时增加自动摘要压缩
- **数据库持久化**: AgentState 添加持久化 checkpointer (当前为 MemorySaver)
