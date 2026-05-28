# Agent Flow — 技能调度交易系统

> 基于 LangManus (deer-flow 前身) 层级化多智能体架构的交易 Demo，核心展示 **Supervisor 循环调度 + SKILL.md 渐进式加载** 的设计模式。

## 快速启动

```bash
cd agent-flow
uvicorn app.main:app --reload
# 浏览器打开 http://localhost:8001
```

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

## 核心概念

### Supervisor 循环调度

参考 LangManus 的层级化多智能体架构。Supervisor 是整个系统的中央决策控制器，通过结构化输出 (JSON) 决定每一步的调度策略：

```
START → Coordinator → Planner → Supervisor ⇄ ToolNode → Formatter → END
```

- **Coordinator** — 入口分流。闲聊直接回复，交易需求交给 Planner
- **Planner** — 分析需求，制定结构化 JSON 执行计划 (需要哪些技能/API)
- **Supervisor** — 核心循环。根据 Plan + 工具返回结果，动态决定下一步: 继续调用工具 / 弹窗收集参数 / 生成结果卡片 / 直接回答
- **ToolNode** — 执行 Supervisor 指定的工具，结果返回 Supervisor
- **Formatter** — 格式化最终输出 (text/popup/card)

所有节点之间的路由通过 `Command(goto=...)` 动态决定，无预定义流水线。

### 技能格式 (SKILL.md)

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
