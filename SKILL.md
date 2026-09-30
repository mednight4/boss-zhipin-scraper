---
name: boss-zhipin-scraper
description: "Scrape BOSS直聘 via Chrome CDP. Searches jobs by keyword/city/filters, fetches JD details, outputs structured JSON/CSV with plaintext salary, and can summarize scraped results into a job-market prompt. Use when user wants to search/analyze jobs on BOSS直聘 or zhipin.com."
version: 2.4.0
author: eatmoreduck
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [scraper, jobs, career, cdp, chrome, zhipin, boss直聘]
---

# BOSS直聘职位抓取工具 v2.4

通过 Chrome CDP 协议抓取 BOSS直聘 (zhipin.com) 职位数据，输出结构化 JSON/CSV（含明文薪资），并可通过 SQLite 三表桥接管道持久化与查询。

---

## 0. 先读这一节：禁止行为

**本仓库的 CLI 已覆盖全部正常操作。不要新建脚本。**

在写任何新 `.py` 文件之前，先确认下面四条你都试过了：

| 你想做的事 | 正确的入口（不要写脚本） |
|---|---|
| 查现在到哪一步、哪些公司查过了、有没有重复/孤儿数据 | `python3 -m scripts.company_list.pipeline --step status` |
| 批量抓详情 | `python3 -m scripts.company_list.pipeline --step detail` |
| 批量抓爱企查洞察 | `python3 -m scripts.company_list.pipeline --step insight` |
| 单条查某家公司的工商信息 | `python3 -m scripts.company_insight.scraper <credit_code>`（抓完自动入库） |
| 导入已有 JSON | `--step list --list-json <path>` / `--step detail` / `--step insight`（会自动补导入） |
| 查 DB 里的数据 | 见第 3 节「主线 B」的 sqlite3 查询模板 |

**禁止**：

1. **禁止在仓库根目录或 `scripts/` 下新建 `check_*.py` / `run_*.py` / `verify_*.py` / `inspect_*.py` 等临时脚本。**
   `.gitignore` 已不再忽略这类文件——写了就会出现在 `git status` 里。上一轮接手者写过 6 个这样的脚本
   （`check_db.py`、`check_insight.py` 等），原因是它不知道 `credit_code` 存在哪张表、也没有状态入口；
   这些信息现在都在本文件里。若确实需要一次性验证，写到系统临时目录（`/tmp`、`%TEMP%`），不要进仓库。
2. **禁止绕过 `db.py` 的 `import_*_from_json()` 直接写 SQLite。** 手工 INSERT 会漏字段，
   并让 `has_detail` / `has_insight` 与实际数据不一致。
3. **禁止用 `python3 scripts/boss_cdp_raw.py` 的裸路径调用方式，而应统一用 `python3 -m scripts.boss_cdp_raw`**
   （前者历史上会让包内导入失败、连 `--help` 都跑不起来；现已修复，但 `-m` 是唯一有测试覆盖的入口）。
4. **禁止绕过验证码。** 遇到验证码/风控页时程序会主动中止并提示人工处理，
   不要尝试指纹伪造、代理轮换、验证码识别等手段（见 `CONTRIBUTING.md` 合规红线）。

**长任务必须加 `-u`。** 抓取动辄十几分钟，不加 `-u` 时 Python 会按块缓冲 stdout，
被当子进程调用时你会长时间看不到任何输出，误判成「卡死」：

```bash
python3 -u -m scripts.company_list.pipeline --step insight
```

各 CLI 入口已调用 `enable_line_buffering()` 做行缓冲，但 `-u` 仍是最稳妥的做法。

---

## 1. 决策入口

每次接到查询/抓取需求时，**先做这两步**，决定走哪条主线。

### 1.1 环境检查

```bash
python3 "$SCRIPT_PATH" --check --cdp-port 9222
```

- 全部通过 → 继续 1.2
- CDP 不通 / 依赖缺失 → 详见 [skill/install.md](skill/install.md)

### 1.2 PipelineState.decide() 判断路径

```python
from scripts.company_list.pipeline import PipelineState

pipe = PipelineState(query_url="https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent")
action = pipe.decide()
```

| decide() 返回 | 含义 | 走哪条主线 |
|---------------||------|-----------|
| `SKIP` | DB 有数据且未过期（24h 内） | → **主线 B：数据查询** |
| `SCRAPE_LIST` | 无数据，需从头抓取 | → **主线 A：数据构建** |
| `IMPORT_LIST` | JSON 已爬但未导入 DB | → **主线 A：数据构建** |
| `RESUME_REFRESH` | 数据已过期（>24h） | → **主线 A：数据构建** |
| `SCRAPE_INSIGHT` | 详情和/或洞察待抓取 | → **主线 A：数据构建（step3-4 与 step5-6 可并行）** |

---

## 2. 主线 A：数据构建（爬虫·管道）

当 `decide()` 返回非 `SKIP` 时，按以下流程执行。

### A1. 渐进式询问用户需求

**不要直接跑命令。** 按以下顺序逐一确认，每步等用户回答后再进下一步。

#### 展示筛选维度，询问过滤条件

先告诉用户可筛选的维度：

| 维度 | 可选值 |
|------|--------|
| 薪资 | 3K以下 / 3-5K / 5-10K / 10-20K / 20-50K / 50K+ |
| 经验 | 在校生 / 应届生 / 1-3年 / 3-5年 / 5-10年 / 10年+ |
| 规模 | 0-20人 / 20-99人 / 100-499人 / 500-999人 / 1000-9999人 / 10000+ |
| 学历 | 大专 / 本科 / 硕士 / 博士 |

如果用户描述不清，**建议去 web 端选好后贴 URL**：
> "你可以先打开 https://www.zhipin.com/web/geek/jobs ，设好筛选条件后把地址栏 URL 贴给我。"

#### 确认搜索意图（关键词 + 城市）

即使用户给了 URL，也要用自然语言复述理解的意图，请用户确认：
> "确认一下：你要查 **上海** 的 **AI Agent** 相关职位，筛选条件是 **10-20K + 本科以上**，对吗？"

#### 让用户选择查询深度

| 选项 | 内容 | 估算时间 |
|------|------|----------|
| A. 仅列表 | 职位名/薪资/公司/地点 | 1-2 分钟 |
| B. 列表 + 详情 | 增加融资/规模/主营/官网 | 3-8 分钟 |
| C. 列表 + 洞察 | 增加工商注册号/法人/风险（CDP 爱企查） | 1-3 分钟 |
| D. 全部 | 详情 + 洞察 全量 | 5-12 分钟 |

### A2. 构造命令执行

**无论是否使用 `--url`，都必须先完成 A1 的深度选择，再构造命令。**

`--url` 只替代筛选参数（keyword/city/salary/scale 等），**不替代深度选择**。深度由独立参数控制，每次运行必须显式指定。

**优先用 `--url`**（一条 URL = keyword + city + 所有筛选条件）：

```bash
# 仅列表（用户选 A）
python3 "$SCRIPT_PATH" --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent&salary=405" --pages 3 --no-detail

# 列表 + 详情（用户选 B）
python3 "$SCRIPT_PATH" --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent&salary=405" --pages 3

# 列表 + 详情 + 洞察（用户选 D）
python3 "$SCRIPT_PATH" --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent&salary=405" --pages 3 --db --step all
```

**并行优化**：用户选 D 时，agent 可开两个子线程分别执行，速度更快：
- 子线程 1: `python3 "$SCRIPT_PATH" --db --step detail`（爬详情）
- 子线程 2: `python3 "$SCRIPT_PATH" --db --step insight`（爬洞察）
- 两者无依赖，`company_list` 已含 `encrypt_brand_id`（详情联立键），洞察侧的 `credit_code` 来自 `company_detail`
```

没有 URL 时用筛选参数：

```bash
python3 "$SCRIPT_PATH" \
  --keyword "AI Agent" \
  --city 上海 \
  --salary 405 \
  --degree 203 \
  --scale 303,304 \
  --pages 3 \
  --db \
  --step all
```

**禁止行为**：收到 URL 后直接 `python --url "..." --pages 10` 而不问深度。URL 只给了筛选条件，没给深度。

### A3. 管道推进

PipelineState 按状态机推进，自动跳过已完成步骤。

**并行说明**：step2 完成后 `company_list` 已含 `encrypt_brand_id`（详情联立键）；洞察需要的 `credit_code` 存在 `company_detail.credit_code`（由 step3-4 从 `business_info` 的「统一社会信用代码」拆出），所以洞察路径依赖详情先完成或至少先导入。两条路径各自独立写各自的表，完成后状态归一化为 `COMPLETE`。

```
IDLE → LIST_JSON_SAVED → LIST_DB_IMPORTED → DETAIL_DONE → COMPLETE
                                       ↘ INSIGHT_DONE ↗
```

| 步骤 | 做什么 | 产物 | 参数流转 | 可并行 |
|------|--------|------|----------|--------|
| step1 | 列表抓取 | `output/query/{query_hash}.json` | — | — |
| step2 | JSON 导入 DB | `company_list` 表 | — | — |
| step3 | 扫描 `has_detail=0` → 逐公司爬取 | `output/company/{brand_id}.json` | `encrypt_brand_id` → 详情页 | ↕ 与 step5 并行 |
| step4 | 导入详情 → 更新 `has_detail=1` | `company_detail` 表 | — | ↕ 与 step5 并行 |
| step5 | 扫描 `has_insight=0` → 逐公司抓取爱企查 | `output/insight/aqc_{credit_code}.json` | `company_detail.credit_code` → 洞察脚本 | ↕ 与 step3-4 并行 |
| step6 | 兜底导入残留洞察 JSON | `company_insight` 表 + has_insight=1 | credit_code → brand_id 反查 | 跟随 step5 |

**step5 洞察脚本说明**：

- 入口函数：`scrape_aqc_by_credit_code(credit_code, cdp_port)`
- CLI 用法：`python -m scripts.company_insight.scraper <credit_code> [--port 9222] [--delay 15]`
- 数据来源：`company_detail.credit_code`（由详情页 `business_info` 的「统一社会信用代码」拆出）。
  注意 `company_list` 表**没有** `credit_code` 列，必须 JOIN `company_detail` 才能拿到。
- 落盘路径：`output/insight/aqc_{credit_code}.json`（CLI 与 step5 共用同一命名，
  由 `scraper.insight_json_path()` 统一生成）
- 工作方式：复用 CDP 打开爱企查详情页 → 解析工商字段 → 结构化输出 → 立即入库 `company_insight`
  并置 `has_insight=1`
- **独立查询**：用户可直接对任意 `credit_code` 执行 `python -m scripts.company_insight.scraper <credit_code>`
  做单条爱企查查询，无需先跑完整管道。抓完会尝试入库；若该 `credit_code` 不在当前批次内，
  会提示「JSON 已保存但未入库」而不是静默丢弃。
- **可安全重跑**：step5 发现同名 JSON 已存在但 `has_insight` 仍为 0 时，会**直接补导入而不重新抓取**，
  避免上次导入失败导致重复请求（上一轮就是这样对 8 家公司重复抓了两遍）。

**验证码/风控处理**（重要）：

两侧都会检测验证码页，命中即**中止整轮**、以退出码 `2` 结束，并打印需要人工打开的 URL。
已完成的进度都已入库，人工完成验证后重跑同一命令自动续做。

**爱企查（百度系）**：抛 `InsightBlockedError`。

```
🛑 爱企查触发验证码/风控，已中止本轮抓取（credit_code=...）：URL 命中风控特征「verify」: ...
   请人工在 Chrome 中打开 ... 完成验证后重跑，程序不会自动绕过。
   已中止本轮洞察抓取（已完成 N 家 + 补导入 M 家）。人工完成验证后重跑同一命令即可续做。
```

检测信号：URL 含 `verify` / `captcha` / `safecheck` / `wappass` / `passport.baidu.com`；
页面标题含「验证」「出错了」「安全中心」；首屏正文含「请输入验证码」「滑动验证」「拖动滑块」
「访问过于频繁」等。

**BOSS直聘**：抛 `SecurityCheckError`（`boss_cdp_raw.detect_security_check_page()`）。
覆盖列表抓取、详情抓取、公司详情提取（`company_detail.extractor`）与 `--step detail` 四条链路。

```
🛑 BOSS 触发验证码/安全校验，已中止本轮抓取（Java @ 上海）：URL 命中安全校验特征「_security_check」: ...
   请人工在 Chrome 中打开 ... 完成验证后重跑，程序不会自动绕过。
```

检测信号：URL 含 `_security_check` / `security-check` / `/web/user/safe` / `captcha` / `verify-slider`；
页面标题含「安全验证」「验证」「出错了」；首屏正文含「请完成安全验证」「拖动滑块」「点击进行验证」
「访问过于频繁」「您的环境存在异常」等。

> 详情链路尤其重要：验证页同样是「一段可解析的文本」，若不先拦下来，
> `scrape_company_detail` 会把它解析成一份几乎全空的详情写入 DB 并置 `has_detail=1`
> —— 状态入口显示「已完成」，实际没有数据。`step3_scrape_details` 现在会在中止前
> 保证这家公司不被标记为已完成。

**不要**把验证码当成普通失败去重试或换 IP——请人工处理后再重跑，
已完成的进度都已入库，重跑会自动续做。

中断恢复：`decide()` 自动检测当前状态，`run()` 从断点继续。详见 [skill/pipeline.md](skill/pipeline.md)。

### A4. 查看状态（唯一的「现在到哪一步」入口）

**不要写脚本查状态。** 所有「哪些公司查过了 / 有没有数据 / 什么时候查的 / 需要重新查吗」的问题，
都由这一条命令回答：

```bash
python3 -m scripts.company_list.pipeline --step status
```

输出六个区块：

| 区块 | 回答的问题 |
|------|-----------|
| `[1] 查询批次` | 有哪几批搜索、关键词/城市/职位数/最早入库时间 |
| `[2] 总体进度` | 职位数、唯一公司数、详情与洞察的已完成/待爬计数 |
| `[3] 待爬详情` | `has_detail=0` 的 brand_id 清单 |
| `[4] 待爬洞察` | `has_insight=0` 的公司名 + `credit_code`；缺 `credit_code` 的单独列出并说明原因 |
| `[5] 洞察 JSON 对账` | 规范命名 / 孤儿 / 旧命名 / 无法解析 / 重复 `credit_code`，并列出具体文件名 |
| `[6] 最近入库的洞察` | 最近 5 家入库时间，用于判断数据新鲜度 |

第 `[5]` 区块的「重复抓取明细」直接暴露同一公司被抓多次的情况（例如
`91310113MA1GNN0NX8: 91310113MA1GNN0NX8.json, aqc_91310113MA1GNN0NX8.json`），
这是上一轮重复抓取的直接证据。`旧命名` 与 `孤儿` 文件确认规范版已存在后即可删除。

---

## 3. 主线 B：数据查询（SQL·分析）

当 `decide()` 返回 `SKIP`（数据已就绪），或用户需要对已有数据做分析时执行。

### B1. 表结构

#### company_list（主表 — 每行一个职位）

| 字段 | 类型 | 说明 |
|------|------|------|
| `job_id` | TEXT UNIQUE | 业务主键 |
| `query_url` | TEXT | 完整查询 URL |
| `query_hash` | TEXT | MD5(url)[:16]，批次标识 |
| `keyword` / `city` / `city_code` | TEXT | 搜索关键词 / 城市名 / 9位码 |
| `filters_json` | TEXT | 筛选条件 JSON |
| `title` / `salary` / `location` | TEXT | 职位名 / 薪资 / 地点 |
| `tags` | TEXT | 经验+学历标签 |
| `boss_name` / `boss_title` / `boss_active_status` | TEXT | 招聘者 / 职位 / 活跃状态 |
| `company_scale` / `company_stage` / `company_industry` | TEXT | 规模 / 融资阶段 / 行业 |
| `skills` / `welfare` | TEXT | 技能标签 / 福利 |
| `encrypt_brand_id` | TEXT | 公司唯一键（联立键 → `company_detail.brand_id`） |
| `is_new` | INTEGER | 本轮是否新增 |
| `has_detail` / `has_insight` | INTEGER | 详情/洞察是否已爬 |

> ⚠️ **`company_list` 没有 `credit_code` 列。** 统一社会信用代码只存在于
> `company_detail.credit_code` 和 `company_insight.credit_code`。任何需要 `credit_code` 的查询
> 都必须 JOIN `company_detail`，否则会报 `no such column`——上一轮接手者为此写了两个探测脚本。

#### company_detail（公司详情 — 每家公司一行）

| 字段 | 类型 | 说明 |
|------|------|------|
| `brand_id` | TEXT UNIQUE | 公司唯一键（联立键） |
| `company_name` / `stage` / `scale` / `industry` | TEXT | 公司名 / 阶段 / 规模 / 行业 |
| `job_count` / `boss_count` | INTEGER | 在招职位数 / BOSS 数 |
| `hot_jobs_json` | TEXT | 热招职位列表 |
| `description` / `website` | TEXT | 公司简介 / 官网 |
| `products_json` | TEXT | 产品列表 |
| `business_info_json` | TEXT | 工商信息（含统一社会信用代码） |
| `address` / `work_hours` / `work_type` | TEXT | 地址 / 工时 / 工作类型 |
| `benefits_json` / `recruiters_json` / `executives_json` | TEXT | 福利 / 招聘者 / 高管 |

#### company_insight（企查查洞察 — CDP 自爬虫）

通过 `scripts/company_insight/scraper.py` 抓取爱企查工商信息。参数 `credit_code` 来自 `company_list`（BOSS 返回的统一社会信用代码）。

| 字段 | 类型 | 说明 |
|------|------|------|
| `credit_code` | TEXT | 统一社会信用代码（主键） |
| `company_name` | TEXT | 公司全称 |
| `legal_person` | TEXT | 法定代表人 |
| `registered_capital` | TEXT | 注册资本 |
| `establish_date` | TEXT | 成立日期 |
| `business_status` | TEXT | 登记状态（开业/注销等） |
| `company_type` | TEXT | 企业类型 |
| `industry` | TEXT | 所属行业 |
| `registered_address` | TEXT | 注册地址 |
| `business_term` | TEXT | 营业期限 |
| `registration_authority` | TEXT | 登记机关 |
| `approval_date` | TEXT | 核准日期 |
| `registration_number` | TEXT | 注册号 |
| `org_code` | TEXT | 组织机构代码 |
| `taxpayer_id` | TEXT | 纳税人识别号 |
| `employee_count` | TEXT | 参保人数 |
| `scale` | TEXT | 规模（大型/中型/小型/微型） |
| `former_name` | TEXT | 曾用名 |
| `phone` | TEXT | 联系电话 |
| `email` | TEXT | 邮箱 |
| `website` | TEXT | 网址 |
| `tags_json` | TEXT | 标签（纳税人/资质/类型，JSON 数组） |
| `products_json` | TEXT | 产品列表（JSON 数组） |
| `top_info_json` | TEXT | 融资/阶段等扩展信息（JSON） |
| `business_info_raw_json` | TEXT | 原始工商信息（调试用，JSON） |
| `url` | TEXT | 爱企查页面 URL |
| `scraped_at` | TEXT | 抓取时间 |

**联立键**：`company_detail.credit_code` = `company_insight.credit_code`（`company_list` 无此列，需经 `encrypt_brand_id` = `brand_id` JOIN 到 `company_detail`）

### B2. 数据过期警告

**查询前必须检查数据 freshness。**

数据有效期由 `BOSS_QUERY_FRESHNESS_HOURS` 环境变量控制，默认 **24 小时**。

```python
from datetime import datetime, timedelta

# 检查数据是否过期
info = db.get_query_info(query_hash)
if info:
    age = datetime.now() - datetime.fromisoformat(info["oldest_create_time"])
    if age > timedelta(hours=24):
        print("⚠️ 数据已过期（>24h），需要返回主线 A 重新抓取")
```

**过期的后果**：
- DB 中的数据仍在，但可能已不准确（职位下架、薪资变动）
- `PipelineState.decide()` 返回 `RESUME_REFRESH`，agent 应回主线 A 重新抓取

### B3. 查询方法

通过 Python sqlite3 直接查询 `output/jobs.db`：

```python
import sqlite3

conn = sqlite3.connect("output/jobs.db")
conn.row_factory = sqlite3.Row

# 基础查询模板
rows = conn.execute("""
    SELECT cl.title, cl.salary, cd.company_name, cd.stage
    FROM company_list cl
    LEFT JOIN company_detail cd ON cl.encrypt_brand_id = cd.brand_id
    WHERE cl.query_hash = ?
""", (query_hash,)).fetchall()
```

### B4. 常用查询案例

```python
# 案例 1: 薪资分布统计
rows = conn.execute("""
    SELECT salary, COUNT(*) as cnt FROM company_list
    WHERE salary != ''
    GROUP BY salary ORDER BY cnt DESC
""").fetchall()

# 案例 2: 某行业的公司（去重）
rows = conn.execute("""
    SELECT DISTINCT cl.encrypt_brand_id,
           cd.company_name, cd.stage, cd.scale
    FROM company_list cl
    JOIN company_detail cd ON cl.encrypt_brand_id = cd.brand_id
    WHERE cd.industry LIKE '%AI%' OR cd.industry LIKE '%人工智能%'
""").fetchall()

# 案例 3: 详情爬取进度
stats = conn.execute("""
    SELECT
        COUNT(*) as total_jobs,
        COUNT(DISTINCT encrypt_brand_id) as total_companies,
        SUM(has_detail) as done_detail,
        COUNT(DISTINCT encrypt_brand_id) - SUM(has_detail) as pending_detail
    FROM company_list
""").fetchone()

# 案例 4: 所有查询批次概览
batches = conn.execute("""
    SELECT query_hash, MIN(keyword) as keyword, MIN(city) as city,
           COUNT(*) as cnt, MIN(create_time) as oldest
    FROM company_list
    GROUP BY query_hash ORDER BY oldest DESC
""").fetchall()

# 案例 5: 新增岗位（is_new=1）
new_jobs = conn.execute("""
    SELECT title, salary, boss_name FROM company_list
    WHERE is_new = 1 ORDER BY create_time DESC
""").fetchall()
```

### B5. 关键索引

查询时优先使用已建索引的字段：

| 索引名 | 字段 | 适用场景 |
|--------|------|----------|
| `idx_cl_query_hash` | `query_hash` | 按查询批次筛选 |
| `idx_cl_brand_id` | `encrypt_brand_id` | 按公司联立查询 |
| `idx_cl_has_detail` | `has_detail` | 筛选待爬详情 |
| `idx_cd_brand_id` | `brand_id` | 详情表主键查找 |
| `idx_cl_has_insight` | `has_insight` | 筛选待爬洞察 |
| `idx_ci_credit_code` | `credit_code` | 洞察表主键查找 |

### B6. 联立查询示例（三表）

```python
# 案例 6: 职位 + 详情 + 洞察（三表联立）
# 注意：credit_code 只在 company_detail / company_insight 上，company_list 没有，
# 因此洞察必须通过 cd.credit_code 关联，不能写 cl.credit_code。
rows = conn.execute("""
    SELECT cl.title, cl.salary,
           cd.company_name, cd.stage, cd.scale,
           ci.legal_person, ci.registered_capital, ci.industry
    FROM company_list cl
    LEFT JOIN company_detail cd ON cl.encrypt_brand_id = cd.brand_id
    LEFT JOIN company_insight ci ON cd.credit_code = ci.credit_code
    WHERE cl.query_hash = ?
    ORDER BY cl.salary DESC
""", (query_hash,)).fetchall()

# 案例 7: 洞察爬取进度
stats = conn.execute("""
    SELECT
        COUNT(DISTINCT cd.credit_code) as total_companies,
        COUNT(DISTINCT ci.credit_code) as done_insight,
        COUNT(DISTINCT cd.credit_code) - COUNT(DISTINCT ci.credit_code) as pending_insight
    FROM company_detail cd
    LEFT JOIN company_insight ci ON cd.credit_code = ci.credit_code
    WHERE cd.credit_code != ''
""").fetchone()
```

---

## 4. 命令速查

### 最简入口（URL 模式）

```bash
python3 "$SCRIPT_PATH" --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent"
python3 "$SCRIPT_PATH" --url "..." --pages 5
```

### 分步管道（`--db --step`）

```bash
python3 "$SCRIPT_PATH" --keyword "AI Agent" --city 上海 --pages 3 --db --step list
python3 "$SCRIPT_PATH" --db --step detail
python3 "$SCRIPT_PATH" --db --step all --list-json output/query/abc123.json
```

### Pipeline 独立入口

```bash
# 查看当前状态（唯一的「现在到哪一步」入口，不要写脚本查）
python3 -m scripts.company_list.pipeline --step status

# 仅运行详情管道
python3 -u -m scripts.company_list.pipeline --step detail

# 仅运行洞察管道（长任务，务必加 -u 让进度实时可见）
python3 -u -m scripts.company_list.pipeline --step insight

# 单条查某家公司（抓完自动入库并置 has_insight=1）
python3 -m scripts.company_insight.scraper 91310104MA1FR5RY3N
```

> **警告**：不要编写自定义脚本直接操作数据库。
> 所有数据导入必须通过 `db.py` 的 `import_*_from_json()` 方法，
> 否则会导致字段缺失或数据不一致。
> 运行管道请使用 `python3 -m scripts.company_list.pipeline --step <list|detail|insight|all|status>`。
> 查状态请用 `--step status`，不要新建 `check_*.py`（见第 0 节）。

### 筛选参数

| 参数 | 值 |
|------|-----|
| `--scale` | 301=0-20人 302=20-99 303=100-499 304=500-999 305=1000-9999 306=10000+ |
| `--salary` | 402=3K以下 403=3-5K 404=5-10K 405=10-20K 406=20-50K 407=50K+ |
| `--experience` | 108=在校生 102=应届生 101=经验不限 103=1年内 104=1-3年 105=3-5年 106=5-10年 107=10年+ |
| `--degree` | 209=初中及以下 208=中专/中技 206=高中 202=大专 203=本科 204=硕士 205=博士 |

### 输出格式

```bash
python3 "$SCRIPT_PATH" --url "..." --output result.json            # JSON（默认）
python3 "$SCRIPT_PATH" --url "..." --format csv                     # CSV（UTF-8 BOM）
python3 "$SCRIPT_PATH" --url "..." --output list.json --detail-output details.json  # 分开输出
```

---

## 5. 常见问题

| 问题 | 解法 |
|------|------|
| CDP 不通 | 详见 [skill/install.md](skill/install.md) 启动 Chrome |
| 薪资空白 | 未登录或登录态失效，重新登录 |
| 抓取中途无数据 | 可能触发风控，等一会或换 `--allow-dom-fallback` |
| DB 查询不到数据 | 确认管道 `--step all` 已执行完毕 |
| 数据过期（>24h） | `decide()` 返回 `RESUME_REFRESH`，重新走主线 A |
| 查询结果为空 | 检查 `query_hash` 是否正确，或确认该批次确实无数据 |
| **命令跑了很久没有任何输出** | 十有八九是 stdout 块缓冲，不是卡死。加 `-u` 重跑；或先看 `--step status` 确认 DB 里有没有在涨 |
| **爱企查返回验证码/风控（退出码 2）** | 程序已主动中止整轮。按提示的 URL 人工在 Chrome 完成验证后重跑同一命令，已完成的进度会自动续做。**不要**自动绕过、不要换 IP、不要连续重试 |
| **`no such column: credit_code`** | `company_list` 没有该列。JOIN `company_detail` 取 `cd.credit_code`（见 B1 的警告框） |
| **同一家公司被查了多次** | 用 `--step status` 的 `[5] 洞察 JSON 对账` 看「重复抓取明细」。现在 CLI 与 step5 共用 `aqc_{credit_code}.json` 命名，且抓前会复用已有 JSON，不会再重复 |
| **不知道哪些公司查过了** | `--step status` 的 `[4] 待爬洞察` 给出待办清单，`[6]` 给出最近入库时间 |
| **想清理旧命名/孤儿 JSON** | `--step status` 的 `[5]` 会列出具体文件名，确认规范版存在后直接删除即可 |

---

## 6. 子模块索引

| 何时读 | 文件 |
|--------|------|
| Pipeline 状态机、决策表、中断恢复 | [skill/pipeline.md](skill/pipeline.md) |
| 完整参数速查、输出格式、工作原理 | [skill/reference.md](skill/reference.md) |
| 安装、首次部署 | [skill/install.md](skill/install.md) |

---

## 7. 注意事项

- 仅用于个人求职研究
- 单次最多 10 页（~300 条），防封号
- 翻页间隔 12-22 秒随机延迟
- 详情页抓取间隔 10-20 秒随机延迟

---

## 8. 安装说明

详见 [skill/install.md](skill/install.md)。

首次运行需要：Chrome 已安装 → Python 3.10+ → `uv add websocket-client requests beautifulsoup4` → `--setup-chrome` 启动 CDP。
