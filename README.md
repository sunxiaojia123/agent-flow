# Agent Flow — 技能调度交易系统（Demo）

基于 LangGraph 的多智能体交易演示，展示 **Supervisor 独揽决策** 架构模式。支持多供应商钢材采购：查库存 → 获取报价 → 生成选商卡片，信息不足时自动弹窗收集。Supervisor 在拥有完整信息（用户画像 + 技能详情 + API schema）后才做判断。

**技术栈**: Python 3.11+ / FastAPI + SSE / LangGraph / Pydantic v2 / 原生 JS 前端

## 快速启动

```bash
pip install -e .
uvicorn app.main:app --reload
# 浏览器打开 http://localhost:8001，进入三栏对话测试界面
```

## Graph 结构

Coordinator 直连 Supervisor，所有边通过 `Command(goto=...)` 动态决定：

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

Supervisor 是唯一的决策枢纽。Tools 执行完始终返回 Supervisor 继续循环，直到 Supervisor 决定路由到某个 Formatter 结束。

### 节点说明

| 节点 | 职责 |
|------|------|
| Coordinator | 入口分流：闲聊直接回复，交易意图交给 Supervisor |
| **Supervisor** | **唯一决策中枢**：完整性检查 + 技能选择 + API 调度 + 终止判断 + 弹窗交互 |
| Tools | 执行 Supervisor 调度的工具，结果返回 Supervisor 继续循环 |
| Formatter | 最终输出：text / popup / card 三种模式 |

### 工具分类

Supervisor 通过 Tool Calling（bind_tools）调度两类工具：

- **执行工具** → 转发 ToolNode，结果返回 Supervisor 继续循环：`get_user_context` / `load_skill_detail` / `call_api`
- **路由工具** → 被 Supervisor 拦截，直接跳转 Formatter 结束：`route_to_formatter_text` / `route_to_formatter_popup` / `route_to_formatter_card`

### Supervisor 循环示例

以"在上海买500吨螺纹钢"为例，Supervisor 驱动 5 轮 Reason-Action-Observe：

| 轮次 | Reason | Action | Observe |
|------|--------|--------|---------|
| 1 | 首次进入，先了解用户偏好 | `get_user_context` | 偏好螺纹钢，默认地区上海 |
| 2 | 上海用户，钢联是本地区供应商 | `load_skill_detail("ganglian-supplier")` | 获取 API 列表和执行指南 |
| 3 | 技能已加载，查库存 | `call_api("check_inventory")` | 库存 800 吨 |
| 4 | 库存充足，获取报价 | `call_api("get_quote", 500吨)` | 单价 3850 元/吨 |
| 5 | 数据充分，生成推荐 | `route_to_formatter_card` | 输出结果卡片 |

## 项目结构

```
agent-flow/
├── skills/                         # 技能目录（SKILL.md 格式）
│   ├── public/                     #   内部技能（5供应商 + 1用户画像）
│   └── custom/                     #   外部技能（可热加载）
├── app/
│   ├── main.py                     # FastAPI 入口
│   ├── api/                        # SSE 流式端点 + 技能管理 API
│   ├── graph/                      # LangGraph 图（state / builder / nodes）
│   ├── skills/                     # 技能解析与注册
│   ├── tools/                      # 工具实现（skill / api / user）
│   └── services/                   # LLM 工厂
├── static/                         # 三栏测试界面
├── docs/                           # 架构设计 / API 文档 / 升级记录
└── pyproject.toml
```

## 技能格式（SKILL.md）

每个技能目录包含一个 `SKILL.md`（YAML frontmatter + Markdown body），Supervisor 按需通过 `load_skill_detail` 渐进式加载，节省 Token。

```markdown
---
name: shagang-supplier
display_name: 沙钢供应商
description: 沙钢集团，主营螺纹钢、线材、热轧卷板
category: supplier
version: "1.0"
---

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
- **Mock 返回**: {"available": true, "stock": 3000, "unit": "吨"}
```

## 文档

- [架构设计](docs/ARCHITECTURE.md) — 图结构、State 设计、SSE 事件、技能系统、设计决策
- [API 文档](docs/API.md) — SSE 端点 + 技能管理端点
- [v2 升级记录](docs/UPGRADE-v2.md) — 架构演进过程与技术决策

## 许可证

MIT License — 详见 [LICENSE](LICENSE)
