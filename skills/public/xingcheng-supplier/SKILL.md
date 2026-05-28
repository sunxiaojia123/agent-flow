---
name: xingcheng-supplier
display_name: 兴澄特钢
description: 兴澄特种钢铁有限公司，专注不锈钢板、镀锌板、合金钢等高附加值产品。技术领先，品质卓越。
category: supplier
version: "1.0"
---

# 兴澄特种钢铁有限公司

## 公司信息
- 名称: 兴澄特种钢铁有限公司
- 地区: 华东
- 城市: 江苏无锡
- 规模: 中型
- 评级: 4.8
- 主营产品: 不锈钢板、镀锌板、合金钢板、耐候钢
- 月产能: 8000吨
- 亮点: 特种钢材专家、技术领先、定制加工、品质保证
- 联系方式: 0510-8271XXXX

## API 接口

### check_inventory
- **描述**: 查询特种钢材库存
- **方法**: GET
- **参数**:
  - product_category: string (必填) - 产品品类
  - grade: string (可选) - 钢材牌号，如304、316L
  - spec: string (可选) - 规格描述
- **Mock 返回**:
  ```json
  {
    "available": true,
    "stock": 500,
    "unit": "吨",
    "product": "不锈钢板 304",
    "warehouse": "无锡锡山仓库",
    "lead_time": "7-10个工作日",
    "remark": "特种钢材按需生产，部分规格需预定"
  }
  ```

### get_quote
- **描述**: 获取特种钢材报价
- **方法**: POST
- **参数**:
  - product_category: string (必填) - 产品品类
  - quantity: number (必填) - 采购数量(吨)
  - grade: string (可选) - 钢材牌号
- **Mock 返回**:
  ```json
  {
    "product": "不锈钢板 304",
    "quantity": 100,
    "unit": "吨",
    "unit_price": 18500,
    "price_unit": "元/吨",
    "total_price": 1850000,
    "valid_until": "2026-06-10",
    "includes_tax": true,
    "includes_shipping": false,
    "payment_terms": "预付30%，发货前付清"
  }
  ```

### check_logistics
- **描述**: 查询特种钢材物流
- **方法**: GET
- **参数**:
  - destination: string (必填) - 配送目的地城市
  - quantity: number (必填) - 配送数量(吨)
- **Mock 返回**:
  ```json
  {
    "available": true,
    "methods": ["公路运输", "铁路运输"],
    "recommended": "公路运输",
    "estimated_days": 5,
    "cost_per_ton": 80,
    "total_logistics_cost": 8000,
    "remark": "特种钢材需防潮包装，推荐专车运输"
  }
  ```

## 执行说明
1. 用户需要不锈钢、镀锌板等特种钢材时匹配兴澄特钢
2. 特种钢材交期较长，需提前告知用户
3. 付款方式为预付模式，与普通钢材不同
4. 先查库存，再获取报价，最后查物流
5. 汇总后使用 show_card 展示推荐卡片
