---
name: shagang-supplier
display_name: 沙钢供应商
description: 江苏沙钢集团，大型钢铁企业，主营螺纹钢、线材、热轧卷板、冷轧卷板。产能充足，价格有竞争力，钢厂直供。
category: supplier
version: "1.0"
---

# 沙钢集团有限公司

## 公司信息
- 名称: 沙钢集团有限公司
- 地区: 华东
- 城市: 江苏张家港
- 规模: 大型
- 评级: 4.9
- 主营产品: 螺纹钢、线材、热轧卷板、冷轧卷板
- 月产能: 50000吨
- 亮点: 钢厂直供、价格优势、产能充足、质量稳定
- 联系方式: 0512-5868XXXX

## API 接口

### check_inventory
- **描述**: 查询当前库存信息
- **方法**: GET
- **参数**:
  - product_category: string (必填) - 产品品类，如螺纹钢、线材
  - grade: string (可选) - 钢材牌号，如HRB400
  - spec: string (可选) - 规格描述
- **Mock 返回**:
  ```json
  {
    "available": true,
    "stock": 3000,
    "unit": "吨",
    "product": "螺纹钢 HRB400",
    "warehouse": "张家港主仓库",
    "lead_time": "3-5个工作日",
    "remark": "库存充足，可随时发货"
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
    "unit_price": 3850,
    "price_unit": "元/吨",
    "total_price": 1925000,
    "valid_until": "2026-06-05",
    "includes_tax": true,
    "includes_shipping": false,
    "payment_terms": "月结30天"
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
    "methods": ["公路运输", "铁路运输", "水路运输"],
    "recommended": "公路运输",
    "estimated_days": 3,
    "cost_per_ton": 45,
    "total_logistics_cost": 22500,
    "remark": "推荐公路运输，3天可达上海"
  }
  ```

## 执行说明
1. 当用户需要采购沙钢主营品类时，先调用 check_inventory 确认库存
2. 库存充足后调用 get_quote 获取实时报价
3. 如用户需要配送信息，调用 check_logistics 获取物流方案
4. 汇总库存、报价、物流信息后，使用 show_card 生成推荐卡片展示给用户
5. 如果缺少必要参数（品类、数量等），使用 ask_user 弹窗收集
