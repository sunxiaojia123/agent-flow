---
name: nanjing-supplier
display_name: 南京钢铁
description: 南京钢铁股份有限公司，主营H型钢、工字钢、槽钢、角钢等型材。型材品类齐全，覆盖华东华中。
category: supplier
version: "1.0"
---

# 南京钢铁股份有限公司

## 公司信息
- 名称: 南京钢铁股份有限公司
- 地区: 华东
- 城市: 江苏南京
- 规模: 大型
- 评级: 4.7
- 主营产品: H型钢、工字钢、槽钢、角钢、无缝管、焊管
- 月产能: 25000吨
- 亮点: 型材专家、规格齐全、可定制长度、配套加工
- 联系方式: 025-8365XXXX

## API 接口

### check_inventory
- **描述**: 查询型材库存
- **方法**: GET
- **参数**:
  - product_category: string (必填) - 产品品类
  - grade: string (可选) - 钢材牌号
  - spec: string (可选) - 规格描述
- **Mock 返回**:
  ```json
  {
    "available": true,
    "stock": 2000,
    "unit": "吨",
    "product": "H型钢 Q235B",
    "warehouse": "南京江宁仓库",
    "lead_time": "3-5个工作日",
    "remark": "型材规格齐全，支持按需切割"
  }
  ```

### get_quote
- **描述**: 获取型材报价
- **方法**: POST
- **参数**:
  - product_category: string (必填) - 产品品类
  - quantity: number (必填) - 采购数量(吨)
  - grade: string (可选) - 钢材牌号
- **Mock 返回**:
  ```json
  {
    "product": "H型钢 Q235B",
    "quantity": 300,
    "unit": "吨",
    "unit_price": 4500,
    "price_unit": "元/吨",
    "total_price": 1350000,
    "valid_until": "2026-06-05",
    "includes_tax": true,
    "includes_shipping": false,
    "payment_terms": "月结30天"
  }
  ```

### check_logistics
- **描述**: 查询型材物流配送
- **方法**: GET
- **参数**:
  - destination: string (必填) - 配送目的地城市
  - quantity: number (必填) - 配送数量(吨)
- **Mock 返回**:
  ```json
  {
    "available": true,
    "methods": ["公路运输", "铁路运输", "水路运输"],
    "recommended": "水路运输",
    "estimated_days": 5,
    "cost_per_ton": 35,
    "total_logistics_cost": 10500,
    "remark": "型材推荐水路运输，成本低但时间较长"
  }
  ```

## 执行说明
1. 用户采购型材(工字钢/H型钢/槽钢/角钢/管材)时匹配南京钢铁
2. 先查库存，再获取报价，最后查物流
3. 型材可提供切割加工服务
4. 汇总后使用 show_card 展示推荐卡片
