---
name: user-profile
display_name: 用户画像
description: 当前用户的基本信息、交易偏好和历史采购记录
category: internal
version: "1.0"
---

# 用户画像

## 用户信息
- 用户ID: user_001
- 姓名: 张经理
- 公司: 上海建工集团有限公司
- 默认地区: 华东
- 默认城市: 上海
- 偏好品类: 螺纹钢、线材、热轧卷板
- 月均采购量: 2000吨
- 付款方式: 月结30天
- 配送偏好: 公路运输
- 联系方式: 138xxxx1234

## API 接口

### get_profile
- **描述**: 获取用户完整画像信息
- **方法**: GET
- **Mock 返回**:
  ```json
  {
    "user_id": "user_001",
    "name": "张经理",
    "company": "上海建工集团有限公司",
    "default_region": "华东",
    "default_city": "上海",
    "preferred_categories": ["螺纹钢", "线材", "热轧卷板"],
    "monthly_volume": 2000,
    "payment_method": "月结30天",
    "shipping_preference": "公路运输",
    "contact_phone": "138xxxx1234"
  }
  ```

### get_history
- **描述**: 获取用户历史采购记录
- **方法**: GET
- **Mock 返回**:
  ```json
  {
    "orders": [
      {"date": "2026-05-15", "product": "螺纹钢 HRB400", "quantity": 500, "unit": "吨", "supplier": "沙钢集团", "status": "已完成", "total_price": 1925000},
      {"date": "2026-05-20", "product": "线材 Q235", "quantity": 300, "unit": "吨", "supplier": "钢联贸易", "status": "配送中", "total_price": 1050000},
      {"date": "2026-04-28", "product": "热轧卷板 Q235B", "quantity": 800, "unit": "吨", "supplier": "华东钢材", "status": "已完成", "total_price": 2960000}
    ]
  }
  ```

## 执行说明
- 用户询问"我买过什么"时，调用 get_history
- 用户发起新采购时，自动通过 get_profile 获取默认偏好填充参数
- 用户画像信息可与供应商 skill 配合使用，无需重复询问用户基本信息
