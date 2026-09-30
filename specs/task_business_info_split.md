# Task: business_info 字段拆分为 company_detail 独立列

> **当前实现契约（优先于本历史设计记录）**
>
> 本文件记录字段拆分方案。现行实现中，`company_list` 没有 `credit_code` 列，列表阶段不会生成或写入信用代码；`company_detail.credit_code` 由公司详情 `business_info` 的“统一社会信用代码”填充，并作为爱企查搜索输入。
>
> 三表的项目内连接关系是 `company_list.encrypt_brand_id = company_detail.brand_id = company_insight.brand_id`。爱企查页面中的 `company_id/pageid` 只用于页面 URL 导航，不是项目数据库连接键。从空库开始的实际顺序是 `list → company_list → detail → company_detail.credit_code → insight → company_insight`，因此列表入库后不能把 detail 和 insight 描述为可直接并发。
>
> **历史记录标记**：下文的目标、步骤和风险保留当时的设计背景；与上述契约冲突的内容均是原方案（已过时），不能当作现行表结构或执行顺序。

## 现状问题

`company_detail` 表的工商信息全部塞在 `business_info_json` 一列（JSON blob）。查询时必须解析 JSON、按中文 key 提取，无法直接 SQL 过滤/排序。

示例数据（`output/company/03b13ce50be625f903163929FlQ~.json`）：
```json
"business_info": {
    "企业名称": "北京智数信达科技有限公司",
    "法定代表人": "孙秀兰",
    "成立时间": "2023-08-16",
    "企业类型": "有限责任公司（独栋自然人）",
    "经营状态": "存续",
    "注册资本": "120万人民币",
    "注册地址": "北京市石景山区八大处路49号院4号楼4层4754A",
    "营业期限": "2023-08-16至-",
    "所属地区": "北京市",
    "统一社会信用代码": "91110112MACWAEA47T",
    "核准日期": "2026-06-15",
    "曾用名": "北京瑞数信达科技有限公司",
    "登记机关": "北京市石景山区市场监督管理局",
    "所属行业": "-",
    "经营范围": "一般项目：技术服务..."
}
```

## 目标

1. 保留 `business_info_json` 列（向后兼容 / 原始数据留存）
2. 新增 15 个独立列，每个工商信息字段一列
3. `import_detail_from_json` 写入时同时填充新列
4. 旧数据通过删除 `company_detail` 表 + 从 JSON 文件全量重新导入完成迁移（不走回填脚本）

## 字段映射

| JSON key (中文) | DB 列名 (英文) | 类型 |
|-----------------|---------------|------|
| 企业名称 | `business_name` | TEXT |
| 法定代表人 | `legal_representative` | TEXT |
| 成立时间 | `established_date` | TEXT |
| 企业类型 | `company_type` | TEXT |
| 经营状态 | `business_status` | TEXT |
| 注册资本 | `registered_capital` | TEXT |
| 注册地址 | `registered_address` | TEXT |
| 营业期限 | `business_term` | TEXT |
| 所属地区 | `region` | TEXT |
| 统一社会信用代码 | `credit_code` | TEXT |
| 核准日期 | `approval_date` | TEXT |
| 曾用名 | `former_name` | TEXT |
| 登记机关 | `registration_authority` | TEXT |
| 所属行业 | `business_industry` | TEXT |
| 经营范围 | `business_scope` | TEXT |

## 步骤一：extractor 已有（无需改动）

`scripts/company_detail/extractor.py` 的 `parse_business_info(text)` 已能解析工商信息区块返回 dict。提取逻辑已在 extractor 主函数中调用并存储为 `result["business_info"]`。

## 步骤二：DB Schema + Import 改动

### 2.1 `scripts/company_list/db.py` — 加 15 列

在 `CREATE TABLE company_detail` 的 `business_info_json TEXT` 后追加 15 个独立列：

```sql
business_name           TEXT,
legal_representative    TEXT,
established_date        TEXT,
company_type            TEXT,
business_status         TEXT,
registered_capital      TEXT,
registered_address      TEXT,
business_term           TEXT,
region                  TEXT,
credit_code             TEXT,
approval_date           TEXT,
former_name             TEXT,
registration_authority  TEXT,
business_industry       TEXT,
business_scope          TEXT
```

### 2.2 `scripts/company_list/db.py` — 更新 `import_detail_from_json`

从 `business_info` dict 提取 15 个字段，追加到 INSERT OR REPLACE 的列列表和 VALUES 列表。

### 2.3 不改的部分

- `parse_business_info` — 不动
- `business_info_json` 列 — 保留
- 查询方法 — 不改（调用方按需取新列）
- `company_list` 表 — 不改

## 步骤三：旧数据迁移

旧数据（独立列空的 `company_detail` 行）通过以下方式迁移：

1. `DROP TABLE company_detail`
2. 重置 `company_list.has_detail = 0`
3. 从 `output/company/*.json` 全量调用 `import_detail_from_json` 重新导入

不走回填脚本——正常写入路径就会填充独立列。

## 测试策略

### 新增测试 `tests/company_list/test_business_info.py`

1. **test_import_extracts_all_15_fields** — 完整 business_info → 15 个独立列全部填充
2. **test_import_empty_business_info** — 空 business_info → 新列为空字符串（无报错）
3. **test_import_missing_business_info_key** — JSON 无 business_info 键 → 不报错，新列为空
4. **test_business_info_json_retained** — business_info_json 列仍保留完整 blob

### 现有测试

- `tests.company_list.test_db` — schema 变更只追加列，INSERT 列数不变，无需修改
- `tests.chrome_setup.test_chrome_setup` — 不受影响
- `tests.company_detail.test_extractor` — 不受影响

## 风险

- `import_detail_from_json` 是 INSERT OR REPLACE，新列追加到列列表末尾，现有调用方不传新列值不会报错
- Schema 变更只追加列，不删不改现有列，100% 向后兼容
- 旧数据迁移通过删表 + 全量导入，无需额外回填脚本
