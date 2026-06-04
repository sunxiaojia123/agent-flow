# API 文档

> 最后更新：2026-06-05

## 基础信息

- Base URL: `http://localhost:8001/api/v1`
- 响应格式: JSON (REST) / SSE text/event-stream (流式)

---

## SSE 流式端点

### POST /chat/stream

主对话端点，返回 SSE 事件流。

**请求**:
```json
{
  "message": "我想在上海买500吨螺纹钢",
  "conversation_id": "optional-existing-uuid"
}
```

**响应头**:
- `Content-Type: text/event-stream`
- `Cache-Control: no-cache`
- `X-Accel-Buffering: no`
- `X-Conversation-Id: <conversation_id>`

**完整流程示例**:
```
event: meta       → START: 开始处理
event: meta       → coordinator start
event: meta       → coordinator end
event: meta       → supervisor start
event: meta       → supervisor end
event: thinking   → Supervisor 推理: 先获取用户画像
event: progress   → 工具开始: get_user_context
event: meta       → tools start
event: meta       → tools end
event: progress   → 工具完成: 用户: 张经理, 地区: 上海
event: meta       → supervisor start
event: meta       → supervisor end
event: thinking   → Supervisor 推理: 加载钢联供应商
event: progress   → 工具开始: load_skill_detail
event: meta       → tools start
event: meta       → tools end
event: progress   → 工具完成: 已加载 钢联供应商
  ... (多轮 check_inventory → get_quote → check_logistics) ...
event: thinking   → Supervisor 推理: 信息充分，生成卡片
event: meta       → formatter_card start
event: meta       → formatter_card end
event: text_delta → 引导文字
event: text_done
event: card       → 交易推荐卡片
event: text_done
event: done       → 本轮完成
```

### SSE 事件类型

#### meta — 调度状态

节点生命周期:
```json
{
  "type": "meta",
  "conversation_id": "uuid",
  "node": "supervisor",
  "message": "Supervisor 正在决策...",
  "status": "start",
  "span_id": "abc123"
}
```

Supervisor 工具决策 (phase: "tool_planned"):
```json
{
  "type": "meta",
  "phase": "tool_planned",
  "tool_name": "load_skill_detail",
  "tool_args": {"skill_name": "shagang-supplier"},
  "message": "Supervisor → 调用 load_skill_detail",
  "span_id": "abc123"
}
```

Supervisor 结束决策 (phase: "supervisor_end"):
```json
{
  "type": "meta",
  "phase": "supervisor_end",
  "next": "formatter_card",
  "reasoning": "已获取沙钢库存和报价信息，生成推荐卡片",
  "message": "Supervisor → formatter_card",
  "span_id": "abc123"
}
```

#### thinking — Supervisor 推理

每轮 Supervisor 决策后发出，包含推理过程和下一步行动:
```json
{
  "type": "thinking",
  "reasoning": "用户明确需要螺纹钢Q235 1000吨，先查询沙钢库存",
  "next_action": "tools",
  "tool_name": "call_api",
  "tool_args": {"skill_name": "shagang-supplier", "api_name": "check_inventory", "params": {"product_category": "螺纹钢"}},
  "span_id": "abc123"
}
```

#### progress — 工具执行进度

工具开始 (phase: "tool_start"):
```json
{
  "type": "progress",
  "phase": "tool_start",
  "tool_name": "call_api",
  "tool_args": {"api_name": "check_inventory"},
  "message": "调用API: 查询库存",
  "span_id": "abc123"
}
```

工具完成 (phase: "tool_end"):
```json
{
  "type": "progress",
  "phase": "tool_end",
  "tool_name": "call_api",
  "message": "查询库存: 库存 3000 吨",
  "span_id": "abc123"
}
```

#### text_delta — 流式文字

```json
{ "type": "text_delta", "content": "根据查询结果，为您推荐 沙钢集团有限公司" }
```

text_delta 在以下场景发出:
- formatter_text 输出的文字内容
- formatter_popup 之前的引导文字
- formatter_card 之前的引导文字
- 流式 LLM 调用过程中的文字块

#### text_done — 文字完成

```json
{ "type": "text_done" }
```

text_done 在每次文字输出结束后发出。对于 popup/card 流程，text_done 会在引导文字之后、popup/card 事件之前发出。整个 SSE 流结束前也会发出一次。

#### popup — 弹窗表单 (参数缺失)

```json
{
  "type": "popup",
  "popup_id": "uuid",
  "fields": [
    {
      "name": "product_category",
      "label": "产品品类",
      "type": "select",
      "required": true,
      "options": ["螺纹钢", "线材", "热轧卷板"]
    },
    {
      "name": "quantity",
      "label": "数量（吨）",
      "type": "number",
      "required": true,
      "min": 1
    }
  ],
  "message": "张经理您好！请补充以下采购信息"
}
```

#### card — 结果卡片

**交易推荐卡片** (`card_type: "trade"`):
```json
{
  "type": "card",
  "card_type": "trade",
  "data": {
    "summary": {"product": "螺纹钢 Q235", "quantity": 1000, "unit": "吨"},
    "recommendations": [
      {
        "company_name": "沙钢集团有限公司",
        "city": "江苏张家港",
        "unit_price": 3850,
        "total_price": 3850000,
        "delivery_days": "3-5个工作日",
        "logistics_cost": 22500,
        "stock_status": "库存充足（3000吨）"
      }
    ]
  }
}
```

**选商卡片** (`card_type: "selection"`):
```json
{
  "type": "card",
  "card_type": "selection",
  "data": {
    "options": [
      {"company_name": "沙钢集团有限公司", "city": "张家港", "unit_price": 3850},
      {"company_name": "钢联贸易", "city": "上海", "unit_price": 3920}
    ]
  }
}
```

#### error — 错误

```json
{ "type": "error", "code": "INTERNAL_ERROR", "message": "error description" }
```

#### done — 完成

```json
{ "type": "done", "conversation_id": "uuid" }
```

---

## 技能管理端点

### GET /skills

获取所有可用技能列表。

**响应**:
```json
{
  "skills": [
    {
      "name": "shagang-supplier",
      "display_name": "沙钢供应商",
      "description": "沙钢集团简介...",
      "category": "supplier",
      "api_count": 3,
      "apis": ["check_inventory", "get_quote", "check_logistics"]
    }
  ]
}
```

### POST /skills/reload

热加载技能 (custom/ 目录新增或修改后使用)。

**响应**:
```json
{ "status": "ok", "count": 6 }
```
