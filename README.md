# Agent Flow — 技能调度交易系统（Demo）

> **这是一个 Demo 项目**，用于展示在 LangGraph 节点编排基础上实现的 Supervisor 循环 Reason-and-Action 架构模式。

基于 LangGraph 构建的层级化多智能体交易演示，核心展示 **Supervisor 循环调度（Reason → Action → Observe → Reason）** 与 **SKILL.md 渐进式加载** 的设计模式。

## Demo 目的

本项目旨在演示以下技术要点：

1. **LangGraph 节点编排基础** — 使用 LangGraph 的 `StateGraph` + `Command(goto=...)` 实现全动态路由，各节点通过 State 共享上下文
2. **Supervisor 循环 Reason-and-Action 流程** — 在 LangGraph 的图上构建一个"推理→行动→观察→再推理"的自治循环，由 Supervisor 作为中央决策器驱动
3. **SKILL.md 渐进式加载** — 首次只注入技能摘要，按需加载完整 SKILL.md 内容，节省上下文 Token

## 快速启动

```bash
cd agent-flow
uvicorn app.main:app --reload
# 浏览器打开 http://localhost:8001
```

## 图结构

```
START → Coordinator → Planner → Supervisor ⇄ ToolNode → Formatter → END
                                        ↑___________↓
                                     Reason-and-Action 循环
```

### 节点说明

| 节点 | 角色 | 说明 |
|------|------|------|
| Coordinator | 入口分流 | 闲聊直接回复，交易需求交给 Planner |
| Planner | 需求分析 | 分析用户需求，制定结构化执行计划 |
| **Supervisor** | **中央决策器** | **Reason-and-Action 循环核心，反复推理+决策+调度** |
| ToolNode | 工具执行 | 执行 Supervisor 指定的工具，结果返回 Supervisor |
| Formatter | 结果格式化 | 文本/弹窗/卡片三种输出模式 |

## Supervisor 循环：Reason → Action → Observe → Reason

Supervisor 是整个系统的核心，它实现了一个自治的 Reason-and-Action 循环。这个循环并非简单的线性流水线，而是 Supervisor 在每一步都重新推理当前状态、做出决策、观察结果、再次推理，直到任务完成。

### 循环工作流

```
         ┌─────────────────────────┐
         │     Supervisor 推理      │
         │  (分析当前状态 + 历史)    │
         └──────────┬──────────────┘
                    │ 结构化决策 (JSON)
                    ▼
         ┌─────────────────────────┐
         │     执行决策 (Action)    │
         │  tools / formatter      │
         └──────────┬──────────────┘
                    │ 工具返回结果
                    ▼
         ┌─────────────────────────┐
         │     观察结果 (Observe)   │
         │  结果回到 Supervisor     │
         └──────────┬──────────────┘
                    │
                    ▼
              ┌──────────┐    是
              │ 任务完成？ │────────→ Formatter → END
              └──────────┘
                    │ 否
                    └────────→ 回到推理步骤
```

### 循环示例

以用户输入 **"在上海买500吨螺纹钢"** 为例，Supervisor 驱动 6 轮 Reason-and-Action 循环：

| 轮次 | Reason（推理） | Action（行动） | Observe（观察） |
|------|---------------|---------------|-----------------|
| 1 | 需要先了解用户画像和采购偏好 | `get_user_context` | 用户偏好华东地区、螺纹钢 |
| 2 | 用户在上海，钢联是本地区供应商且主营螺纹钢 | `load_skill_detail("ganglian-supplier")` | 获取钢联的 API 列表 |
| 3 | 技能已加载，立即查询库存 | `call_api("check_inventory", {螺纹钢})` | 库存 3000 吨，充足 |
| 4 | 库存够，获取 500 吨报价 | `call_api("get_quote", {螺纹钢, 500吨})` | 单价 3850 元/吨 |
| 5 | 报价拿到，查询配送到上海的物流 | `call_api("check_logistics", {上海, 500吨})` | 陆运 3 天，运费 8000 元 |
| 6 | 库存/报价/物流全部获取完毕 | `formatter_card` (生成推荐卡片) | 输出结果卡片给用户 |

> 每一轮 Supervisor 都根据**上一轮观察到的结果**重新推理，动态决定下一步行动。这不是预定义的流水线，而是自治的循环决策。

### 决策输出格式

Supervisor 每轮输出结构化 JSON 作为决策指令：

```json
{
  "next": "tools",
  "tool_name": "call_api",
  "tool_args": {"skill_name": "ganglian-supplier", "api_name": "check_inventory", "params": {"product_category": "螺纹钢"}},
  "reasoning": "技能已加载，立即调用 check_inventory 查询螺纹钢库存"
}
```

`next` 的四种路由方向：
- `tools` — 继续循环，调用指定工具，结果返回 Supervisor 再推理
- `formatter_text` — 循环结束，输出文字回复
- `formatter_card` — 循环结束，生成推荐卡片
- `formatter_popup` — 循环结束，弹窗收集用户补充信息

## 项目结构

```
agent-flow/
├── skills/                          # 技能目录 (SKILL.md 格式)
│   ├── public/                      #   内部技能 (5供应商 + 1用户画像)
│   │   ├── user-profile/SKILL.md
│   │   ├── shagang-supplier/SKILL.md
│   │   ├── ganglian-supplier/SKILL.md
│   │   ├── huadong-supplier/SKILL.md
│   │   ├── xingcheng-supplier/SKILL.md
│   │   └── nanjing-supplier/SKILL.md
│   └── custom/                      #   外部技能 (可热加载)
├── app/
│   ├── main.py                      # FastAPI 入口
│   ├── config.py                    # 配置管理 (pydantic-settings)
│   ├── api/
│   │   ├── routes.py                # SSE 流式端点 + 技能管理 API
│   │   ├── schemas.py               # Request/Response Pydantic 模型
│   │   └── sse.py                   # SSE 事件生成器 (astream_events)
│   ├── graph/
│   │   ├── state.py                 # AgentState 定义
│   │   ├── builder.py               # LangGraph 图构建
│   │   ├── router.py                # Router 类型定义
│   │   └── nodes/
│   │       ├── coordinator.py       # 入口分流 (闲聊/交易)
│   │       ├── planner.py           # 制定结构化执行计划
│   │       ├── supervisor.py        # 核心循环调度 (structured output)
│   │       ├── tools.py             # 工具分发执行
│   │       └── formatter.py         # 最终输出 (text/popup/card)
│   ├── skills/
│   │   ├── models.py               # Skill/ApiEndpoint Pydantic 模型
│   │   ├── loader.py               # SKILL.md 解析器
│   │   └── registry.py             # 双源注册表 (public + custom)
│   ├── tools/
│   │   ├── skill_tools.py           # load_skill_detail, get_api_schema
│   │   ├── api_tools.py             # call_api (mock)
│   │   └── user_tools.py            # get_user_context
│   └── services/
│       └── llm.py                   # LLM 工厂
├── static/
│   ├── index.html                   # 三栏测试界面
│   ├── app.js                       # SSE 接收 + 事件渲染
│   └── style.css                    # 样式
├── docs/
│   ├── ARCHITECTURE.md              # 架构设计文档
│   └── API.md                       # API 文档
└── pyproject.toml
```

## 技能格式 (SKILL.md)

每个技能是一个目录，包含一个 `SKILL.md` 文件:

```markdown
---
name: shagang-supplier
display_name: 沙钢供应商
description: 沙钢集团，主营螺纹钢、线材、热轧卷板
category: supplier
version: "1.0"
---

# 沙钢集团有限公司

## 公司信息
- 名称: 沙钢集团有限公司
- 地区: 华东
- 主营产品: 螺纹钢、线材、热轧卷板

## API 接口

### check_inventory
- **描述**: 查询当前库存
- **方法**: GET
- **参数**:
  - product_category: string (必填) - 产品品类
- **Mock 返回**:
  ```json
  {"available": true, "stock": 3000, "unit": "吨"}
  ```

## 执行说明
1. 用户采购时先调 check_inventory 确认库存
2. 库存充足则调 get_quote 获取报价
...
```

### 渐进式加载

Supervisor 的 system prompt 只包含技能摘要 (技能名 + 一句话描述)。需要时才通过 `load_skill_detail` 工具加载完整 SKILL.md 内容，节省 Token。

## 文档

- [架构设计](docs/ARCHITECTURE.md) — 图结构、节点说明、State、SSE 事件、技能系统
- [API 文档](docs/API.md) — SSE 端点 + 技能管理端点

## 许可证

MIT License — 详见 [LICENSE](LICENSE)
