# Task: SQLite 三表桥接与分阶段管道

> **当前实现契约（优先于本历史设计记录）**
>
> 本文件记录 SQLite 桥接与分阶段管道的历史方案。现行实现中，`company_list` 没有 `credit_code` 列；列表只产生 `company_list.encrypt_brand_id`。详情 extractor 从 `business_info` 取统一社会信用代码并写入 `company_detail.credit_code`，爱企查以该字段搜索；爱企查 `company_id/pageid` 只用于页面 URL 导航。
>
> 三表通过 `company_list.encrypt_brand_id = company_detail.brand_id = company_insight.brand_id` 连接。从空库启动必须按 `list → company_list → detail → company_detail.credit_code → insight → company_insight` 推进，不能把 detail 与 insight 描述为列表入库后的直接并发。当前洞察待处理查询是 `company_list INNER JOIN company_detail`，并要求 `cl.has_detail=1`、`cl.has_insight=0`。
>
> 当前输出目录是 `output/query/`、`output/company/`、`output/insight/`，数据库默认是 `output/jobs.db`；本文件中出现的 `data/` 和用户目录路径属于历史方案。当前 `--step all` 总是报错，不能作为可执行恢复命令。
>
> **历史记录标记**：下文的表结构、步骤和命令保留原始设计背景；与上述契约冲突的内容属于原方案（已过时），不能作为现行接口说明。

## 目标

引入 SQLite 数据库作为列表抓取与公司详情抓取之间的桥接层，实现三表设计（company_list / company_detail / company_insight），支持增量爬取和 AI Agent 查询。

## 总体架构

```
Step 1: List 爬取
  scrape_list() → data/query/{query_hash}.json (原始归档)
       ↓
  从 JSON 读取 → 结构化导入 company_list 表

Step 2: Detail 爬取 (扫描 DB has_detail=0)
  scrape_company_detail() → data/company/{brand_id}.json (单公司归档)
       ↓
  从 JSON 读取 → 结构化导入 company_detail 表 → 更新 has_detail=1

Step 3: Insight 爬取 (扫描 DB has_insight=0)
   CDP 自爬虫抓取爱企查 → 结构化导入 company_insight 表 → 更新 has_insight=1
```

每步独立可中断恢复：JSON 先行落地，DB 导入可重试，不会重复爬取。

## 文件存储规范

```
data/query/{query_hash}.json       ← 列表原始结果（query_hash = MD5(query_url)）
data/company/{brand_id}.json       ← 单公司详情（brand_id 即公司主体键）
```

- `data/query/`：每次搜索一份 JSON，文件名是查询 URL 的 MD5 前 16 位，用户可识别查询条件
- `data/company/`：每家公司独立一份 JSON，文件名是 `brand_id`（URL 安全、唯一），用户可直接打开阅读公司信息

## 新增文件

### `scripts/company_list/db.py` — SQLite 数据访问层

数据库路径：`~/.boss-zhipin-scraper/jobs.db`（可通过 `BOSS_DB_PATH` 环境变量覆盖）

#### 表结构设计

**company_list**（主表 — 每行一个职位）

```sql
CREATE TABLE company_list (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL UNIQUE,               -- 业务主键 (MD5 of job_link+title)
    query_url       TEXT NOT NULL,                      -- 完整查询URL
    query_hash      TEXT NOT NULL,                      -- MD5(query_url) 前16位
    keyword         TEXT,
    city            TEXT,
    city_code       TEXT,
    filters_json    TEXT,
    title           TEXT,
    salary          TEXT,
    salary_source   TEXT,
    location        TEXT,
    tags            TEXT,
    boss_name       TEXT,
    boss_title      TEXT,
    boss_active_status TEXT,
    company_scale   TEXT,
    company_stage   TEXT,
    company_industry TEXT,
    job_labels      TEXT,
    skills          TEXT,
    welfare         TEXT,
    encrypt_job_id  TEXT,
    encrypt_boss_id TEXT,
    encrypt_brand_id TEXT,
    job_link        TEXT,
    company_link    TEXT,
    is_new          INTEGER DEFAULT 1,
    has_detail      INTEGER DEFAULT 0,
    has_insight     INTEGER DEFAULT 0,
    create_time     TEXT NOT NULL,
    scraped_at      TEXT
);
CREATE INDEX idx_cl_query_hash ON company_list(query_hash);
CREATE INDEX idx_cl_brand_id ON company_list(encrypt_brand_id);
CREATE INDEX idx_cl_has_detail ON company_list(has_detail);
CREATE INDEX idx_cl_has_insight ON company_list(has_insight);
```

**company_detail**（公司详情表 — 按 brand_id 去重）

```sql
CREATE TABLE company_detail (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id        TEXT NOT NULL UNIQUE,               -- 业务主键
    company_list_id INTEGER,                            -- 触发来源
    company_name    TEXT,                               -- 法定名称 (business_info.企业名称)
    job_count       INTEGER,
    boss_count      INTEGER,
    stage           TEXT,
    scale           TEXT,
    industry        TEXT,
    hot_jobs_json   TEXT,
    description     TEXT,
    website         TEXT,
    products_json   TEXT,
    business_info_json TEXT,                            -- 含统一社会信用代码
    address         TEXT,
    work_hours      TEXT,
    work_type       TEXT,
    benefits_json   TEXT,
    recruiters_json TEXT,
    executives_json TEXT,
    office_addresses_json TEXT,
    url             TEXT,
    json_path       TEXT,                               -- 归档JSON路径
    create_time     TEXT NOT NULL,
    scraped_at      TEXT
);
CREATE INDEX idx_cd_brand_id ON company_detail(brand_id);
```

**company_insight**（企查查洞察表 — 预留）

```sql
CREATE TABLE company_insight (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id        TEXT NOT NULL UNIQUE,
    company_list_id INTEGER,
    company_name    TEXT,
    credit_code     TEXT,
    legal_person    TEXT,
    registered_capital TEXT,
    establish_date  TEXT,
    business_scope  TEXT,
    business_status TEXT,
    cap_json        TEXT,
    risk_json       TEXT,
    create_time     TEXT NOT NULL,
    scraped_at      TEXT
);
CREATE INDEX idx_ci_brand_id ON company_insight(brand_id);
CREATE INDEX idx_ci_credit_code ON company_insight(credit_code);
```

#### 核心 API

```python
class JobDatabase:
    def __init__(self, db_path: str = None)
    def init_schema(self)                              -- 幂等建表

    # --- List 导入 ---
    def import_list_from_json(self, json_path: str) -> tuple[int, int]
        -- 读取 data/query/*.json → 写入 company_list
        -- 返回 (插入数, 跳过数)

    # --- Detail 查询/导入 ---
    def get_pending_detail_brands(self) -> list[dict]
        -- has_detail=0 的唯一 brand 列表
        -- 返回 [{id, encrypt_brand_id, company_link, boss_name}, ...]
    def import_detail_from_json(self, json_path: str, brand_id: str) -> None
        -- 读取 data/company/{brand_id}.json → 写入 company_detail
    def mark_detail_done(self, brand_id: str) -> None
        -- 更新关联 company_list 行 has_detail=1

    # --- Insight 查询/导入 (预留) ---
    def get_pending_insight_brands(self) -> list[dict]
    def import_insight_from_json(self, json_path: str, brand_id: str) -> None
    def mark_insight_done(self, brand_id: str) -> None

    # --- 统计 ---
    def get_stats(self) -> dict
        -- {total_jobs, unique_companies, pending_detail, pending_insight, done_detail, done_insight}

    def close(self)
```

### `scripts/company_list/pipeline.py` — 管道编排

封装分阶段执行逻辑，便于 CLI 和 AI Agent 调用。

```python
def step1_scrape_list(keyword, city, filters, cdp_port=None) -> str:
    """爬取列表 → 保存 JSON → 返回 json_path"""

def step2_import_list(db: JobDatabase, json_path: str) -> tuple[int, int]:
    """从 JSON 导入列表到 DB"""

def step3_scrape_details(db: JobDatabase, cdp_port=None) -> list[str]:
    """扫描 DB → 逐公司爬取详情 → 保存 JSON → 返回 json_paths"""

def step4_import_details(db: JobDatabase) -> tuple[int, int]:
    """扫描 data/company/*.json → 导入 DB → 更新 has_detail"""

def run_full_pipeline(keyword, city, filters, cdp_port=None):
    """完整管道: step1 → step2 → step3 → step4"""
```

## 修改文件

### `scripts/boss_cdp_raw.py`

新增 CLI 参数：

| 参数 | 说明 |
|------|------|
| `--db` | 启用 SQLite 模式 |
| `--db-path PATH` | 自定义 DB 路径 |
| `--step {list,detail,insight,all}` | 执行哪一步（默认 `all`） |
| `--list-json PATH` | 指定列表 JSON 路径（跳过列表抓取） |
| `--detail-json-dir PATH` | 指定详情 JSON 目录（跳过详情抓取） |

修改 `main()` 流程：

```
--step list:
    scrape_list() → save to data/query/{query_hash}.json
    if --db: import_list_from_json()

--step detail (requires --db):
    if --detail-json-dir:
        import_details_from_dir()
    else:
        brands = db.get_pending_detail_brands()
        for brand in brands:
            detail = scrape_company_detail(brand['company_link'])
            save to data/company/{brand_id}.json
        import_details_from_dir()

--step all:
    step1 → step2 → step3 → step4
```

### `scripts/company_list/__init__.py`

导出 `JobDatabase`、`build_query_url`、`compute_query_hash`、pipeline 函数。

## 执行流程示例

```bash
# 完整管道（列表 + 详情）
python scripts/boss_cdp_raw.py --keyword agent --city 上海 --db --step all

# 仅列表
python scripts/boss_cdp_raw.py --keyword agent --city 上海 --db --step list

# 仅补爬详情（从中断恢复）
python scripts/boss_cdp_raw.py --db --step detail

# 指定已有 JSON 导入
python scripts/boss_cdp_raw.py --db --step detail --detail-json-dir data/company/
```

## 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| JSON 先行 | 每步先写 JSON 再导 DB | 可中断恢复，不重复爬取 |
| 详情文件名 | `{brand_id}.json` | URL 安全、唯一、可直接打开阅读 |
| 列表文件名 | `{query_hash}.json` | 标识查询批次，避免重复抓取 |
| 导入幂等 | job_id/brand_id UNIQUE + INSERT OR REPLACE | 重复导入不报错 |
| 详情去重 | 按 encrypt_brand_id GROUP BY | 同一公司多职位只抓一次 |
| 向后兼容 | `--db` 默认关闭 | 不影响现有 JSON-only 用户 |
| company_name | 优先 business_info.企业名称，回退 boss_name | 列表只有品牌名 |

## 测试

新增 `tests/company_list/test_db.py`：
- `test_init_schema_idempotent`
- `test_import_list_from_json`：验证 JSON → DB 字段映射
- `test_import_list_dedup`：重复导入不重复插入
- `test_get_pending_detail_brands`：去重 + 仅返回 has_detail=0
- `test_import_detail_from_json`：验证详情 JSON → DB
- `test_mark_detail_done`：级联更新 has_detail
- `test_get_stats`：统计正确
- `test_build_query_url`：URL 构造
- `test_compute_query_hash`：哈希稳定

全 mock，不依赖 Chrome/网络。

## 版本号

版本号不变（仍为 2.3.0），此改动为新增功能。

## 溯源

- Plan 文件：`specs/task_sqlite_bridge_pipeline.md`
- CHANGELOG 条目：未发布 → 变更
