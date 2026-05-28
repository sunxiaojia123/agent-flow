# API 文档

> 最后更新：2026-05-29

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
- `X-Conversation-Id: <conversation_id>`

**完整流程示例**:
```
event: meta       → 开始处理
event: meta       → coordinator 执行
event: meta       → planner 执行
event: meta       → supervisor 决策 (tool_planned: get_user_context)
event: meta       → tools 执行
event: meta       → supervisor 决策 (tool_planned: load_skill_detail)
event: meta       → tools 执行
event: meta       → supervisor 决策 (supervisor_end: formatter_card)
event: card       → 结果卡片
event: done       → 本轮完成
```

### SSE 事件类型

#### meta — 调度状态

节点执行:
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

Supervisor 工具决策:
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

Supervisor 结束决策:
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

#### text_delta — 流式文字

```json
{ "type": "text_delta", "content": "好的，为您查询到" }
```

#### text_done — 文字完成

```json
{ "type": "text_done" }
```

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
      "options": [
        {"value": "螺纹钢", "label": "螺纹钢"},
        {"value": "线材", "label": "线材"}
      ]
    },
    {
      "name": "quantity",
      "label": "数量（吨）",
      "type": "number",
      "required": true,
      "min": 1
    }
  ],
  "message": "请补充以下采购信息"
}
```

#### card — 结果卡片

**推荐列表卡片** (`card_type: "trade"`):
```json
{
  "type": "card",
  "card_type": "trade",
  "data": {
    "summary": {"product": "螺纹钢", "quantity": 500, "unit": "吨", "region": "华东"},
    "recommendations": [
      {
        "rank": 1,
        "company_name": "沙钢集团有限公司",
        "match_score_label": "92%",
        "main_products": ["螺纹钢", "线材"],
        "highlights": ["钢厂直供", "价格优势"],
        "city": "张家港",
        "scale": "大型",
        "rating": 4.9
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
    "company": {"company_name": "沙钢集团有限公司", "city": "张家港", "rating": 4.9, "contact": {"phone": "0512-5868XXXX"}},
    "order": {"product": "螺纹钢 HRB400", "quantity": 500, "unit": "吨", "region": "华东"},
    "message": "已选定该供应商，请确认交易信息"
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
