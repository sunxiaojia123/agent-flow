# Agent Flow — 技能调度交易系统（Demo）

> **这是一个 Demo 项目**，用于展示基于 LangGraph 的 Supervisor 独揽决策架构 — 不依赖独立的 Planner，Supervisor 在拥有完整信息（用户画像 + 技能详情 + API schema）后才做判断。

基于 LangGraph 构建的多智能体交易演示，核心展示 **Supervisor 独揽决策循环（Reason → Action → Observe → Reason）** 与 **SKILL.md 渐进式加载** 的设计模式。

## 架构演进

v1 版本包含独立的 Planner 节点（Coordinator → Planner → Supervisor），负责"完整性检查"。但在实际运行中发现 Planner 存在根本性缺陷：

**Planner 在 skill 懒加载之前运行，缺少关键信息**:
- 不知道 API 需要什么参数（如 `check_inventory` 的 `grade` 字段）
- 没有用户画像数据（如默认地区、偏好品类）
- 只有技能的一行摘要，没有完整 API 定义

这导致 Planner 的"完整性判断"本质上是盲猜。它说"信息完整"，Supervisor 加载 skill 后发现 API 还需要额外参数，又得弹窗 — Planner 的判断被推翻，LLM 调用完全浪费。

**v2 移除了 Planner**，Supervisor 独揽决策：

```
v2:  Coordinator → Supervisor ⇄ Tools → Formatter
```

Supervisor 进入循环后第一步调用 `get_user_context` 获取画像，后续按需 `load_skill_detail` 获取 API 定义。它在**拥有完整信息**后才做完整性判断 — 知道用户画像有什么、API 需要什么，判断精准。

详见 [架构设计文档](docs/ARCHITECTURE.md#为什么没有-planner)。

## 快速启动

```bash
cd agent-flow
uvicorn app.main:app --reload
# 浏览器打开 http://localhost:8001
```

## 图结构

```
START → Coordinator → Supervisor ⇄ ToolNode → Formatter → END
                            ↑___________↓
                         Reason-and-Action 循环
```

### 节点说明

| 节点 | 角色 | 说明 |
|------|------|------|
| Coordinator | 入口分流 | 闲聊直接回复，交易需求交给 Supervisor |
| **Supervisor** | **唯一决策中枢** | **完整性检查 + 技能选择 + API 调度 + 动态应变 + 终止判断** |
| ToolNode | 工具执行 | 执行 Supervisor 指定的工具(get_user_context/load_skill_detail/call_api) |
| Formatter | 结果格式化 | 文本/弹窗/卡片三种输出模式 |

## Supervisor 循环：Reason → Action → Observe → Reason

Supervisor 是系统的唯一大脑，独揽从信息收集到最终输出的全部决策。它在每一步都重新推理当前状态、做出决策、观察结果、再次推理，直到任务完成。

### 循环工作流

```
         ┌─────────────────────────┐
         │     Supervisor 推理      │
         │  (画像 + 技能 + API + 历史) │
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

以用户输入 **"在上海买500吨螺纹钢"** 为例，Supervisor 驱动 5 轮 Reason-and-Action 循环：

| 轮次 | Reason（推理） | Action（行动） | Observe（观察） |
|------|---------------|---------------|-----------------|
| 1 | 首次进入，必须先了解用户偏好 | `get_user_context` | 偏好螺纹钢，默认地区上海 |
| 2 | 用户在上海，钢联是本地区供应商且主营螺纹钢 | `load_skill_detail("ganglian-supplier")` | 获取钢联的 API 列表和执行指南 |
| 3 | 技能已加载，立即查询库存 | `call_api("check_inventory", {螺纹钢})` | 库存 800 吨，充足 |
| 4 | 库存够，获取 500 吨报价 | `call_api("get_quote", {螺纹钢, 500吨})` | 单价 3850 元/吨 |
| 5 | 库存/报价数据充分 | `formatter_card` (生成推荐卡片) | 输出结果卡片给用户 |

> 每一轮 Supervisor 都根据**上一轮观察到的结果**重新推理。信息不全时（如用户只说"买点钢材"），Supervisor 获取画像后直接弹窗收集缺失信息 — 这不是"兜底"，而是正常的业务交互。

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
- `formatter_popup` — 信息不全时弹窗收集，是 Supervisor 执行中的正常交互

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
│   │   └── sse.py                   # SSE 事件生成器 (thinking/progress/text/popup/card)
│   ├── graph/
│   │   ├── state.py                 # AgentState 定义
│   │   ├── builder.py               # LangGraph 图构建
│   │   ├── router.py                # Router 类型定义
│   │   └── nodes/
│   │       ├── coordinator.py       # 入口分流 (闲聊/交易)
│   │       ├── supervisor.py        # 唯一决策中枢 (完整性+技能+API+终止)
│   │       ├── tools.py             # 工具分发执行
│   │       └── formatter.py         # 最终输出 (text/popup/card)
│   ├── skills/
│   │   ├── models.py               # Skill/ApiEndpoint Pydantic 模型
│   │   ├── loader.py               # SKILL.md 解析器
│   │   └── registry.py             # 双源注册表 (public + custom)
│   ├── tools/
│   │   ├── skill_tools.py           # load_skill_detail
│   │   ├── api_tools.py             # call_api (mock)
│   │   └── user_tools.py            # get_user_context
│   └── services/
│       └── llm.py                   # LLM 工厂 (支持 response_format)
├── static/
│   ├── index.html                   # 三栏测试界面
│   ├── app.js                       # SSE 接收 + 事件渲染
│   └── style.css                    # 样式
├── docs/
│   ├── ARCHITECTURE.md              # 架构设计文档
│   └── API.md                       # API 文档
└── pyproject.toml
```

> 注意：v2 已移除 `app/graph/nodes/planner.py`。Planner 的职责已并入 Supervisor。

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

Supervisor 的 system prompt 只包含技能摘要 (技能名 + 一句话描述)。需要时才通过 `load_skill_detail` 工具按需加载完整 SKILL.md 内容，节省 Token。

## 文档

- [架构设计](docs/ARCHITECTURE.md) — 图结构、节点说明、State、SSE 事件、技能系统、架构演进
- [API 文档](docs/API.md) — SSE 端点 + 技能管理端点

## 许可证

MIT License — 详见 [LICENSE](LICENSE)
