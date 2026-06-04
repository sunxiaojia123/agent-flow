# v2 架构升级记录

> 记录 Agent Flow 从 v1 到 v2 的架构演进过程、技术决策和踩过的坑。

## 时间线

| 日期 | 事件 |
|------|------|
| 2026-05-29 | v1 初始版本：Coordinator → Planner → Supervisor → Tools → Formatter |
| 2026-06-04 | v2 重构：移除 Planner，Supervisor 成为唯一决策中枢 |
| 2026-06-04 | 决策机制升级：JSON Mode → Tool Calling (bind_tools) |
| 2026-06-05 | Bug 修复：消息历史清洗、Coordinator 隔离、tool_call 配对 |

## 升级 1：移除 Planner（2026-06-04）

### 动机

v1 的图结构为 `Coordinator → Planner → Supervisor ⇄ Tools → Formatter`。Planner 负责在 Supervisor 执行之前做"完整性检查"——判断用户是否提供了足够的信息（品类、数量、地区等）。

实际运行中发现 Planner 存在根本性缺陷：

- **信息鸿沟**: Planner 在 skill 懒加载之前运行。此时只知道技能的一行摘要，不知道 API 参数定义和用户画像
- **盲猜判断**: Planner 判定"信息完整"后，Supervisor 加载 skill 发现 API 还需要额外参数（如 `check_inventory` 的 `grade` 字段），只得再弹窗——Planner 的判断被推翻
- **浪费 LLM 调用**: Planner 的推理结果大部分情况下被后续发现的信息推翻

### 方案

移除 Planner 节点，让 Supervisor 在循环中自行处理完整性判断：

```
v1: Coordinator → Planner → Supervisor ⇄ Tools → Formatter

v2: Coordinator → Supervisor ⇄ Tools → Formatter
```

Supervisor 进入循环后第一步调用 `get_user_context`，后续按需 `load_skill_detail`。在拥有完整信息（用户画像 + API 定义）后才做完整性判断。

### 效果

- 减少 1 次 LLM 调用/交易流
- 完整性判断从"盲猜"变为"数据驱动"
- 架构更简洁，`supervisor_decision` 不再需要与 `plan` 字段交互

## 升级 2：JSON Mode → Tool Calling（2026-06-04）

### 动机

v1 的 Supervisor 使用 OpenAI 的 JSON Mode（`response_format={"type": "json_object"}`）输出结构化决策。这种方式存在几个问题：

1. **解析不稳定**: JSON 可能格式错误、缺少字段、包含额外文本
2. **不支持流式输出**: JSON Mode 下无法获取推理过程
3. **Schema 约束弱**: 只能通过 prompt 描述期望的 JSON 结构，无法强制类型

### 方案

使用 LangChain 的 `bind_tools` 机制，将决策类型定义为 LLM 原生 tool_call：

```python
# 路由工具 — 被 Supervisor 拦截，直接路由到 Formatter
ROUTE_TOOLS = [
    route_to_formatter_text,   # 文字回复
    route_to_formatter_popup,  # 弹窗收集
    route_to_formatter_card,   # 卡片展示
]

# 执行工具 — 转发到 ToolNode，结果返回 Supervisor
EXECUTION_TOOLS = [
    get_user_context,          # 用户画像
    load_skill_detail,         # 技能加载
    call_api,                  # API 调用
]

bound_llm = llm.bind_tools(ALL_TOOLS, tool_choice="required")
```

**两类工具的区别**:
- **路由工具**: Supervisor 拦截，不经过 ToolNode。`_build_route_decision()` 解析 tool_call 参数，直接设置 `Command(goto=formatter_*)`
- **执行工具**: 通过 `_build_execution_decision()` 转发到 ToolNode。ToolNode 返回 ToolMessage 后 Supervisor 继续循环

### 效果

- Tool calling 是 LLM 原生能力，输出格式由 API schema 保证，不会出现 JSON 解析失败
- `reasoning` 字段自然嵌入 tool_call 参数中，前端可直接展示推理过程（thinking 事件）
- 路由工具和执行工具的分离使代码逻辑更清晰

## 升级 3：Bug 修复与防御体系（2026-06-05）

### Bug 1：raw tool-call 内容泄漏到用户输出

**现象**: 用户收到 `<|tool_calls|> <|invoke name="load_skill_detail">...` 这样的原始 XML 文本。

**根因**: Coordinator 的 LLM 看到了对话历史中的 tool_call 消息模式，被"带偏"模仿输出 tool call XML。由于输出不包含 `handoff_to_supervisor`，走到了 `formatter_text` 直接输出。

**修复**: Coordinator 新增 `_visible_messages()` 过滤器，在判断意图前过滤掉 ToolMessage、带 tool_calls 的 AIMessage、内部 SystemMessage。LLM 只看到干净的对话视图。

**涉及文件**: `app/graph/nodes/coordinator.py`

### Bug 2：ToolMessage 配对断裂

**现象**: DeepSeek API 返回 400 错误 `"Messages with role 'tool' must be a response to a preceding message with 'tool_calls'"`。

**根因**: 消息过滤器删除了带 tool_calls 的 AIMessage，但其对应的 ToolMessage 还在历史中。API 要求每条 ToolMessage 之前必须有带匹配 tool_call_id 的 AIMessage。

**修复**: 改为**保留** AIMessage 但**清洗**其 content：
1. 清空 content（DeepSeek 可能在 content 中内联 raw tool-call 格式文本）
2. 截断到 1 个 tool_call（LLM 可能返回多个 tool_calls，但 ToolNode 只执行第 1 个，多个 tool_calls 与单个 ToolMessage 不匹配会导致 400 `insufficient tool messages` 错误）

**涉及文件**: `app/graph/nodes/supervisor.py`（消息过滤 + 消息存储两处）

### Bug 3：SSE 防御层

**现象**: 部分异常路径下，带 tool_calls 的 AIMessage 可能出现在 formatter_text 输出中。

**修复**: SSE formatter_text 处理器跳过带 tool_calls 的消息，作为最后一道防线。

**涉及文件**: `app/api/sse.py`

### 架构层面的经验教训

1. **Coordinator 需要消息隔离**: 入口分类器不应看到内部执行细节。tool_call 历史对意图分类器是噪音，会诱导 LLM 模仿。
2. **ToolMessage 配对是硬约束**: OpenAI-compatible API 严格要求 AIMessage(tool_calls) → ToolMessage(tool_call_id) 的配对。任何破坏配对的过滤操作都会导致 400 错误。
3. **存储前清洗优于读取时过滤**: 在消息写入 state 之前清洗（如清空 content、截断 tool_calls）比在读取时过滤更安全——写入时的上下文更完整，更能准确判断什么是"多余"的。
4. **多 LLM provider 的兼容性**: DeepSeek 的 tool calling 实现在 `auto` 和 `required` 模式下都正确返回 structured tool_calls，但可能在 content 中附带额外的格式化文本。消息清洗是跨 provider 的必要防御。

## v2 架构全貌

```
                     ┌─────────────────────────┐
                     │       Coordinator        │
                     │  (消息隔离 + 意图分类)    │
                     └───────────┬─────────────┘
                                 │
                     ┌───────────▼─────────────┐
                     │       Supervisor         │
                     │  (Tool Calling 决策循环)  │
                     │                          │
                     │  路由工具 → Formatter     │
                     │  执行工具 → ToolNode      │
                     └───────────┬─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                  │
    ┌─────────▼──┐    ┌─────────▼──┐    ┌─────────▼──┐
    │formatter   │    │  ToolNode  │    │formatter   │
    │_text       │    │            │    │_popup      │
    └────────────┘    └─────┬──────┘    └────────────┘
                            │         ┌──────────────┐
                            └─────────┤  formatter   │
                                      │  _card       │
                                      └──────────────┘
```

**核心原则**:
- **Coordinator** 看干净对话 → 分类意图
- **Supervisor** 看完整历史（含清洗后的 tool 消息） → 独揽决策
- **ToolNode** 执行单一工具 → 返回给 Supervisor 继续推理
- **Formatter** 读 supervisor_decision → 生成用户可见输出

## 当前文件清单

v2 中移除的文件:
- `app/graph/nodes/planner.py` — Planner 节点（职责并入 Supervisor）
- `app/graph/router.py` 中的 `Plan` 和 `Router` 类型（不再使用 JSON Mode）

v2 中新增/重写的文件:
- `app/graph/nodes/supervisor.py` — 重写为 Tool Calling 模式，~460 行
- `app/graph/nodes/coordinator.py` — 新增消息隔离过滤
- `app/api/sse.py` — 新增 thinking 事件 + tool_calls 防御
