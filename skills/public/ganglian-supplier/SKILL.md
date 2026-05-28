---
name: ganglian-supplier
display_name: 钢联贸易
description: 上海钢联贸易有限公司，中型钢材贸易商，主营螺纹钢、线材、圆钢。扎根华东，覆盖华北，服务灵活。
category: supplier
version: "1.0"
---

# 钢联贸易有限公司

## 公司信息
- 名称: 钢联贸易有限公司
- 地区: 华东
- 城市: 上海
- 规模: 中型
- 评级: 4.6
- 主营产品: 螺纹钢、线材、圆钢
- 月产能: 15000吨
- 亮点: 同城配送、服务灵活、响应快速、可小批量
- 联系方式: 021-6234XXXX

## API 接口

### check_inventory
- **描述**: 查询当前库存信息
- **方法**: GET
- **参数**:
  - product_category: string (必填) - 产品品类
  - grade: string (可选) - 钢材牌号
  - spec: string (可选) - 规格描述
- **Mock 返回**:
  ```json
  {
    "available": true,
    "stock": 800,
    "unit": "吨",
    "product": "螺纹钢 HRB400",
    "warehouse": "上海宝山仓库",
    "lead_time": "1-2个工作日",
    "remark": "上海本地仓库，同城次日可达"
  }
  ```

### get_quote
- **描述**: 获取产品实时报价
- **方法**: POST
- **参数**:
  - product_category: string (必填) - 产品品类
  - quantity: number (必填) - 采购数量(吨)
  - grade: string (可选) - 钢材牌号
- **Mock 返回**:
  ```json
  {
    "product": "螺纹钢 HRB400",
    "quantity": 500,
    "unit": "吨",
    "unit_price": 3900,
    "price_unit": "元/吨",
    "total_price": 1950000,
    "valid_until": "2026-06-03",
    "includes_tax": true,
    "includes_shipping": true,
    "payment_terms": "月结30天或现结优惠1%"
  }
  ```

### check_logistics
- **描述**: 查询物流配送方案
- **方法**: GET
- **参数**:
  - destination: string (必填) - 配送目的地城市
  - quantity: number (必填) - 配送数量(吨)
- **Mock 返回**:
  ```json
  {
    "available": true,
    "methods": ["公路运输"],
    "recommended": "公路运输",
    "estimated_days": 1,
    "cost_per_ton": 20,
    "total_logistics_cost": 10000,
    "remark": "上海同城/周边配送，次日可达，运费优惠"
  }
  ```

## 执行说明
1. 用户采购品类匹配后，先调用 check_inventory 确认库存
2. 库存充足后调用 get_quote 获取报价（报价已含运费至上海周边）
3. 如需配送到更远地区，调用 check_logistics 获取完整物流方案
4. 汇总信息后使用 show_card 展示推荐卡片
5. 钢联贸易适合上海本地及周边客户，配送速度快
