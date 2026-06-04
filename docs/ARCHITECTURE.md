# 架构设计

> 最后更新：2026-06-05

## 概述

基于 LangGraph 的多智能体交易 Demo。核心设计：

1. **Supervisor 独揽决策** — 没有独立的 Planner，Supervisor 是唯一的决策中枢，拥有做出所有决策所需的全部信息
2. **渐进式技能加载** — Supervisor prompt 只含技能摘要，需要时通过工具加载完整 SKILL.md
3. **多轮工具调用** — 获取用户画像 → 加载供应商技能 → 查库存 → 报价格 → 问物流 → 生成卡片
4. **流式输出** — SSE 推送 meta / thinking / progress / text / popup / card 多种事件
5. **内外技能分离** — public/ 内部技能 (5供应商+1用户画像)，custom/ 外部技能 (可热加载)

## 为什么没有 Planner？

v1 版本包含独立的 Planner 节点（Coordinator → Planner → Supervisor）。经过多轮 Agent 讨论和实际运行验证，发现 Planner 存在根本性的架构缺陷，已于 v2 移除。

**Planner 的根本问题：信息鸿沟**

Planner 在 skill 懒加载**之前**运行。此时系统只知道技能的一行摘要（如 "ganglian-supplier: 钢联贸易，主营螺纹钢"），但不知道：
- 每个 API 的参数定义（如 check_inventory 需要 grade 参数）
- 用户画像中的默认偏好（如 default_city: 上海）
- 供应商的具体执行指南

Planner 在这个信息不全的阶段做"完整性检查"（品类/数量/地区是否齐全），本质上是盲猜。它判定"信息完整"放行后，Supervisor 加载 skill 才发现 API 还需要额外参数，又得弹窗——Planner 的判断被推翻，它的 LLM 调用完全浪费。

**Supervisor 为什么更合适**

Supervisor 在循环中运行，可以先调用 `get_user_context` 获取画像、按需 `load_skill_detail` 获取 API 定义，在**拥有完整信息**后判断是否需要弹窗。这个判断是准确的——它知道用户画像有什么、API 需要什么，不会做盲猜。

```
v1:  Coordinator → Planner → Supervisor ⇄ Tools → Formatter
     Planner 做完整性检查 ← 但缺少用户画像和 API 参数定义，检查不可靠

v2:  Coordinator → Supervisor ⇄ Tools → Formatter
     Supervisor 独揽决策 ← 拥有画像 + 技能详情 + API schema，判断精准
```

**收益**:
- -1 LLM 调用/交易流
- 完整性判断从"盲猜"变为"数据驱动"
- 架构更简洁，职责更清晰

## 技术栈

| 层 | 技术 |
|---|---|
| 编排引擎 | LangGraph + MemorySaver checkpointer |
| HTTP 框架 | FastAPI + SSE streaming |
| LLM | langchain-openai (DeepSeek 等兼容接口) |
| 结构化决策 | Tool Calling (bind_tools) 而非 JSON Mode |
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
    ├── Coordinator    ── 入口分流 (闲聊直接回复 / 交易→Supervisor)
    ├── Supervisor     ── 唯一决策中枢 (完整性检查 + 技能选择 + API 调度 + 结束判断)
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
    ├── call_api         ── 执行 mock API 调用
    └── get_user_context ── 加载用户画像
```

## Graph 结构

v2 架构 — Coordinator 直连 Supervisor，无中间 Planner：

```
START
  │
  ▼
coordinator ──── (chitchat) ──→ formatter_text ──→ END
  │
  │ (trading intent → Command(goto="supervisor"))
  ▼
supervisor ←──────────────────────────┐
  │                                   │
  │ Command(goto="tools")             │ Command(goto="supervisor")
  │                                   │
  ▼                                   │
tools ────────────────────────────────┘
  │
  ├── Command(goto="formatter_text")  → formatter_text → END
  ├── Command(goto="formatter_popup") → formatter_popup → END
  └── Command(goto="formatter_card")  → formatter_card → END
```

**关键**: 所有边通过 `Command(goto=...)` 动态决定，Supervisor 是唯一的决策枢纽。

### 节点说明

| 节点 | 类型 | 职责 | 输出路由 |
|------|------|------|----------|
| `coordinator` | 路由 | LLM 判断意图: 闲聊/交易 | `supervisor` 或 `formatter_text` |
| `supervisor` | **核心循环** | 完整性检查 + 技能选择 + API 调度 + 终止判断 | 动态 4 路 |
| `tools` | 工具执行 | 分发执行工具(get_user_context/load_skill_detail/call_api) | `supervisor` (loop back) |
| `formatter_text` | 终端 | 输出文字回复 | END |
| `formatter_popup` | 终端 | 输出弹窗表单(信息不全或执行中需要补充) | END |
| `formatter_card` | 终端 | 输出结果卡片 | END |

### Supervisor 的完整职责

Supervisor 独揽以下所有决策：

1. **完整性自检** — 进入循环第一步 `get_user_context`，获取画像后综合用户历史消息判断品类/数量/地区是否齐全。不全则立即 `route_to_formatter_popup`
2. **技能选择** — 根据用户需求和画像偏好，从可用技能中选择最匹配的供应商
3. **API 调度** — 按合理顺序调用 check_inventory → get_quote → check_logistics
4. **动态调整** — 供应商库存不足时切换备选，数据充分时比较推荐
5. **终止判断** — 信息足够时路由到 `route_to_formatter_card` 或 `route_to_formatter_text`
6. **弹窗交互** — 信息不足或 API 需要更多参数时，自然地弹窗收集（不是"兜底"，是正常交互）

### Coordinator 的消息隔离

Coordinator 是每次请求的入口。为防止其 LLM 被对话历史中的内部执行消息（ToolMessage、带 tool_calls 的 AIMessage）"带偏"而模仿输出 tool call 格式，Coordinator 在判断意图前会过滤消息历史：

- **过滤**: ToolMessage、带 tool_calls 的 AIMessage、内部 SystemMessage（如 `[状态]` 前缀）
- **保留**: HumanMessage、普通 AIMessage（用户可见的回复内容）

这样 Coordinator 看到的是干净的对话视图，不会产生幻觉 tool call。

## State 设计

```python
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]  # 完整对话 + 工具调用历史
    conversation_id: str
    plan: dict | None                         # [已废弃] Planner 移除后保留兼容
    supervisor_decision: dict | None          # 最近一次 Supervisor 路由决策
    coordinator_reply: str | None             # Coordinator 直接回复内容
    final_action: str                         # "text" | "popup" | "card" | ""
    popup_message: str                        # 弹窗提示文案
    popup_fields: list[dict]                  # 弹窗字段定义
    card_type: str                            # "trade" | "selection"
    card_data: dict                           # 卡片数据
    iteration_count: int                      # Supervisor 循环计数 (安全阀, MAX=15)
    guidance_message: str                     # 弹窗/卡片前的文字引导
```

**消息历史管理**: messages 包含完整历史。Supervisor 发送给 LLM 前会做两层处理：
1. **过滤** — 删除 `name='supervisor'` 的旧格式 AIMessage（向后兼容）
2. **清洗** — 对带 tool_calls 的 AIMessage，清空 content（防止 DeepSeek 内联的 raw tool-call 格式泄漏）并截断到 1 个 tool_call（防止 LLM 返回多个 tool_calls 时与单一 ToolMessage 不匹配）

上下文窗口取最近 30 条消息。Supervisor 自己的 AIMessage（无 tool_calls 的路由推理）保留在历史中，供 LLM 了解之前的决策上下文。

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

Supervisor 通过 Tool Calling (bind_tools) 可调度的 3 种执行工具:

| 工具 | 参数 | 功能 |
|------|------|------|
| `get_user_context` | 无 | 加载用户画像+采购历史 (Supervisor 第一轮必调) |
| `load_skill_detail` | `skill_name: str` | 渐进式加载完整 SKILL.md |
| `call_api` | `skill_name, api_name, params` | 执行 mock API 调用 |

另有 3 种路由工具（`route_to_formatter_text/popup/card`）被 Supervisor 拦截，不经过 ToolNode，直接路由到对应 Formatter。

## SSE 事件模型

| event | 来源 | 携带数据 |
|-------|------|----------|
| `meta` | 各节点 start/end | `{node, message, status}` — 调度进度 |
| `thinking` | supervisor 结束后 | `{reasoning, next_action, tool_name, tool_args}` — 推理步骤 |
| `progress` | tools start/end | `{phase, message, tool_name}` — 工具执行进度 |
| `text_delta` | formatter_text / guidance | `{content}` — 流式文字 |
| `text_done` | 文字流结束 | `{}` |
| `popup` | formatter_popup | `{popup_id, fields, message}` — 弹窗表单 |
| `card` | formatter_card | `{card_type, data}` — 结果卡片 |
| `error` | 异常 | `{code, message}` |
| `done` | 完成 | `{conversation_id}` |

## 完整执行流程示例

```
用户: "我想在上海买500吨螺纹钢"

coordinator → LLM 判断 "handoff_to_supervisor" → goto supervisor
  [meta: coordinator start → end]
  [meta: supervisor start]

supervisor(1) → tool_call: get_user_context → goto tools
  [thinking: 首次进入，先获取用户画像]

tools → 执行 get_user_context → 返回用户画像 (偏好螺纹钢, 默认上海) → goto supervisor
  [progress: 用户: 张经理, 地区: 上海, 偏好: 螺纹钢, 线材, 热轧卷板]

supervisor(2) → tool_call: load_skill_detail("ganglian-supplier") → goto tools
  [thinking: 用户在上海需要螺纹钢，钢联是上海本地供应商]
  [progress: 加载技能详情: ganglian-supplier]

tools → 加载钢联 SKILL.md → 返回 API 列表 + 执行说明 → goto supervisor

supervisor(3) → tool_call: call_api(check_inventory) → goto tools
  [progress: 调用API: 查询库存]

tools → mock 返回库存数据 (800吨) → goto supervisor
  [progress: 查询库存: 库存 800 吨]

supervisor(4) → tool_call: call_api(get_quote, 500吨) → goto tools
  [progress: 调用API: 获取报价]

tools → mock 返回报价 (3850元/吨) → goto supervisor
  [progress: 获取报价: 3850 元/吨, 总价 1925000 元]

supervisor(5) → tool_call: route_to_formatter_card({...}) → goto formatter_card
  [thinking: 库存和报价均已获取，信息充分，生成推荐卡片]

formatter_card → [card event] → END
  [done]
```

## 关键设计决策

1. **Supervisor 独揽决策** — v2 移除了 Planner。Supervisor 在拥有用户画像+技能详情+API schema 全部信息后才做判断，不盲猜
2. **Command(goto) 动态路由** — 不预设边，每个节点通过 `Command(goto=...)` 决定下一步
3. **Tool Calling (bind_tools) 结构化决策** — 使用 LLM 原生 tool_call 而非 JSON Mode。路由工具被 Supervisor 拦截直连 Formatter，执行工具转发 ToolNode 后返回 Supervisor 继续循环。比 JSON Mode 更稳定，避免了 JSON 解析失败的问题
4. **渐进式加载** — Supervisor prompt 只有技能摘要，按需 `load_skill_detail` 获取完整内容
5. **ToolNode 统一回 Supervisor** — 执行-决策循环，Supervisor 评估结果后决定继续还是结束
6. **Coordinator 消息隔离** — Coordinator 判断意图前过滤内部执行消息（ToolMessage、带 tool_calls 的 AIMessage），防止 LLM 被 tool call 历史"带偏"而模仿输出
7. **消息历史清洗** — Supervisor 发送给 LLM 的消息历史经过过滤（移除旧格式）+ 清洗（清空 tool_calls 消息的 content，截断到 1 个 tool_call），防止 DeepSeek 内联 raw tool-call 格式污染后续调用，同时保证 ToolMessage 配对正确
8. **循环安全阀** — MAX_ITERATIONS=15，防止无限循环。重试机制：LLM 未返回 tool_call 时重试一次
9. **Mock 模式** — `call_api` 直接解析 SKILL.md 中的 mock 返回示例
10. **弹窗是正常交互** — 不是"兜底"或"异常"，而是 Supervisor 执行中自然的信息收集手段

## 扩展点

- **模型替换**: `LLM_MODEL` 环境变量，支持 Claude/GPT-4 等更强大的模型
- **新增供应商技能**: 在 `skills/public/` 或 `skills/custom/` 下创建新的 SKILL.md，调用 `POST /api/v1/skills/reload` 热加载
- **真实 API 对接**: 修改 `app/tools/api_tools.py` 中的 `call_api` 函数
- **数据库持久化**: AgentState 添加持久化 checkpointer (当前为 MemorySaver)
