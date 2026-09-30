# Task: 企查查洞察爬虫接入 Pipeline 体系

> **当前实现契约（优先于本历史设计记录）**
>
> 本文件记录爱企查洞察接入的历史方案。`company_list` 没有 `credit_code` 列；BOSS 公司详情 extractor 从 `business_info` 取统一社会信用代码并写入 `company_detail.credit_code`，爱企查按该字段搜索。爱企查页面中的 `company_id/pageid` 只用于 URL 导航，不是项目表连接键。
>
> 项目三表的连接键是 `company_list.encrypt_brand_id = company_detail.brand_id = company_insight.brand_id`。空库实际顺序为 `list → company_list → detail → company_detail.credit_code → insight → company_insight`，所以洞察依赖详情，列表入库后不能直接并发 detail 与 insight。所谓独立洞察入口只适用于详情已就绪且 `credit_code` 可用的记录；`get_pending_insight_brands()` 还要求 `cl.has_detail=1`、`cl.has_insight=0` 并能 `INNER JOIN company_detail`。
>
> **历史记录标记**：下文的目标、字段设计和接入步骤保留当时背景；与本契约冲突的内容属于原方案（已过时）。

## 现状问题

`scripts/company_insight/scraper.py` 是独立的企查查抓取脚本，通过 credit_code 搜索爱企查、抓取详情页并输出 JSON，但未接入 pipeline 体系：

- 输出目录不规范（应在 `output/insight/` 下）
- 顶层输出缺少 `phone`/`email`/`website` 联系信息
- 包含难以清理的 `description` 和 `business_scope` 字段
- `business_info_raw` 中的 `description` 被 `"... 展开"` 后的 UI 噪音污染
- `business_info_raw` 中的 `former_name` 被股权结构/持股比例数据污染
- `parse_top_tags` 误收 UI 标签（"风险监控"等）
- pipeline 没有 step5 触达 `company_insight` 表

## 目标

将企查查洞察爬虫完整接入现有 pipeline：`company_list` 抽出 `credit_code` → 搜索爱企查 → 抓取详情页 → 结构化输出 → 入库 `company_insight`。顶层字段精简干净，`business_info_raw` 调试数据也做清理。

## 设计

### 修改 1：`scripts/company_insight/scraper.py` — 核心清洗

#### 输出路径

```python
output_dir = os.path.join(OUTPUT_DIR, "insight")
os.makedirs(output_dir, exist_ok=True)
output_path = os.path.join(output_dir, f"{credit_code}.json")
```

#### 顶层字段精简

删除 `description` 和 `business_scope`（文本过于冗长，清理成本高，不值得入库）。

新增联系字段（从已有 `parse_contact_info` 接入）：
```python
"phone": _clean_field_value("phone", contact_info.get("phone", "")),
"email": _clean_field_value("email", contact_info.get("email", "")),
"website": _clean_field_value("website", contact_info.get("website", "")),
```

#### `_clean_field_value` 新增清洗规则

| 字段 | 规则 | 示例 |
|------|------|------|
| `scale` | 去掉开头非中文字符 + 尾部字母标 | "小型 S" → "小型"，"微型 XS" → "微型" |
| `phone` | 去掉尾部 "更多电话" / "获取更多" | "0571-8855101..." → "0571-8855101" |
| `email` | 去掉尾部 "更多" / "获取更多邮箱..." | |
| `website` | 去掉尾部 "更多" / "获取更多..."，"暂无网址" → 空 | |
| `approval_date` | `****-**-**` → 空 | |
| `establish_date` | 非 `YYYY-` 开头 → 空 | 防止误捡分支机构信息 |
| `former_name` | 数字/%/持股开头 → 空 | 防止误捡持股比例 |

#### `parse_top_tags` 增加 UI 排除列表

排除："风险监控"、"发票抬头"、"企业认证"、"同行"、"店铺"、"对比" 等 UI 元素，只保留纳税人/企业类型/资质标签。

#### `business_info_raw` 清理函数

新增 `_clean_business_info_raw(business)`：
- `description` 在 `"... 展开"` 处截断（只保留经营范围描述正文）
- 删除 `former_name`（该字段经常被股权结构数据污染）

```python
def _clean_business_info_raw(business: dict) -> dict:
    raw = dict(business)
    desc = raw.get("description", "")
    if desc:
        idx = desc.find("... 展开")
        if idx > 0:
            raw["description"] = desc[:idx]
    raw.pop("former_name", None)
    return raw
```

#### 顶层输出字段（最终 22 个）

```
company_name, credit_code, legal_person, registered_capital,
establish_date, business_status, company_type, industry,
registered_address, business_term, registration_authority,
approval_date, registration_number, org_code, taxpayer_id,
employee_count, former_name, phone, email, website,
scale, stage, tags, products, business_info_raw, url, scraped_at
```

### 修改 2：`scripts/company_list/db.py` — 表结构与数据访问

#### `company_insight` 表新增 18 列

联系：`phone`, `email`, `website`, `description`
注册信息：`company_type`, `industry`, `registered_address`, `business_term`,
`registration_authority`, `employee_count`, `scale`, `former_name`
JSON 扩展：`tags_json`, `products_json`, `top_info_json`, `business_info_raw_json`
溯源：`url`, `scraped_at`

#### 方法更新

- `company_list` 不提供 `credit_code`；必须先通过 BOSS 公司详情得到 `company_detail.credit_code`。
- `get_pending_insight_brands()` 返回可执行的公司记录，其中 `brand_id` 来自 `company_list.encrypt_brand_id`，`credit_code` 来自 `company_detail`。
- 洞察结果的连接使用 `company_insight.brand_id = company_list.encrypt_brand_id`；`credit_code` 不是结果表连接键。

### 修改 3：`scripts/company_list/pipeline.py` — 管道扩展

#### 新增 step5_scrape_insights()

从 `company_detail` 取得 `credit_code` → 循环调用 `scrape_aqc_by_credit_code()` → 保存 JSON → 使用对应 `brand_id` 调 `import_insight_from_json()` 入库。

#### 新增 run_insight_pipeline()

独立入口，只跑 step5（列表+详情已在 DB 就绪时适用）。

#### run_full_pipeline 扩展

新增 `scrape_insight_fn` 可选参数，允许外部传入自定义抓取函数。

#### PipelineState 状态机扩展

新增状态：`DETAIL_DONE`（详情已完成、洞察待抓取）

新增决策分支：`SCRAPE_INSIGHT`（当 `detail_pending == 0` 但 `insight_pending > 0` 时触发）

```
IDLE → LIST_JSON_SAVED → LIST_DB_IMPORTED → DETAIL_DONE → INSIGHT_DONE → COMPLETE
```

### 修改 4：删除 dead code

- `business_scope` / `description` 的清洗规则
- `flush()` 中 `business_scope` 特殊处理逻辑

## 真机验证

测试 3 家公司，全部成功：

| credit_code | 公司名 | 验证要点 |
|-------------|--------|---------|
| 91310117324576081E | 上海桐栖信息科技有限公司 | baseline |
| 91310113MA1GNN0NX8 | 谷斗科技（上海）有限公司 | 修复 `former_name` 误捡持股比例 |
| 913301103112401401 | 杭州云象网络技术有限公司 | 修复 `establish_date` 误捡分支机构信息 |

## 不需要修改的文件

- `scripts/boss_cdp_raw.py` — 不碰列表/详情主链路
- `scripts/company_detail/extractor.py` — 不碰 BOSS 详情提取
- `AGENTS.md` — 暂不更新，后续统一处理
- `tests/company_list/test_db.py` — 22 个单测全绿，结构未变

## 验证

- `python -m py_compile scripts/company_insight/scraper.py` — 语法
- `python -m py_compile scripts/company_list/db.py` — 语法
- `python -m py_compile scripts/company_list/pipeline.py` — 语法
- `python -m unittest tests.company_list.test_db` — DAL 回归

## 溯源

- 本 spec：`specs/task_company_insight_integration.md`
- CHANGELOG：未发布段落新增条目
