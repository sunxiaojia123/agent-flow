# v2 架构升级记录

> 记录 Agent Flow 从 v1 到 v2 的架构演进。

## 升级概览

| 阶段 | 内容 |
|------|------|
| 移除 Planner | Supervisor 独揽决策，完整性判断从"盲猜"变为"数据驱动" |
| JSON Mode → Tool Calling | 用 `bind_tools` 替代 JSON 解析，路由工具与执行工具分离 |
| 防御体系 | Coordinator 消息隔离、tool_call 消息清洗、SSE 输出防御 |

## 架构变化

```
v1: Coordinator → Planner → Supervisor ⇄ Tools → Formatter
     Planner 在 skill 加载前做完整性检查 ← 信息不全，判断不可靠

v2: Coordinator → Supervisor ⇄ Tools → Formatter
     Supervisor 先获取画像+技能详情，再判断 ← 数据驱动，判断精准
```

**移除 Planner 的原因**: Planner 在 skill 懒加载之前运行，缺少 API 参数定义和用户画像，完整性判断本质上是盲猜。Supervisor 在循环中按需加载信息后再判断，准确可靠。

**Tool Calling 替代 JSON Mode**: v1 用 `response_format={"type": "json_object"}` 输出决策 JSON，存在解析不稳定、Schema 约束弱的问题。v2 改用 `bind_tools`，将路由决策和执行指令定义为 LLM 原生 tool_call，由 API schema 保证格式正确。

**防御体系**: v2 迭代中修复了三类问题 — Coordinator 被 tool_call 历史"带偏"输出 raw XML、消息过滤破坏 ToolMessage 配对导致 API 400、多 tool_calls 与单 ToolMessage 不匹配。通过消息隔离、存储前清洗、SSE 防御层三层防护解决。

## 文件变更

| 操作 | 文件 |
|------|------|
| 移除 | `app/graph/nodes/planner.py` |
| 重写 | `app/graph/nodes/supervisor.py` (Tool Calling 模式) |
| 重写 | `app/graph/nodes/coordinator.py` (新增消息隔离) |
| 更新 | `app/api/sse.py` (新增 thinking 事件 + 防御层) |
