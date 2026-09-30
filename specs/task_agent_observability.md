# Task: Agent 防呆与可观测性 — 7 个问题的系统性解法

## 现状问题

上一轮 agent 接手项目时写了 6 个临时脚本（`check_db.py`、`check_insight.py`、`check_credit_code.py`、`check_companies.py`、`run_insight.py` 等），并多次绕过数据访问层直接操作 SQLite。根本原因是项目缺乏足够的防呆设计和可观测性入口：

1. **不知道 `credit_code` 在哪张表** — `company_list` 没有 `credit_code` 列，agent 只能靠 `PRAGMA table_info` 反复探测
2. **没有统一状态入口** — 想知道"哪些公司查过了"只能自己写脚本 `SELECT *` 全表扫描
3. **绕过数据访问层** — 自己写 INSERT 绕过 `db.import_*_from_json()`，只写入 13/30 列
4. **JSON 命名混乱** — `{credit_code}.json` / `{brand_id}.json` / `aqc_{credit_code}.json` 三种命名并存
5. **验证码无感知** — 验证页文本被解析成空详情写入 DB，状态显示"已完成"实际无数据
6. **stdout 缓冲** — 长任务十几分钟看不到输出，被误判成卡死
7. **has_insight 未更新** — JSON 已落盘但 DB 状态未同步，导致重复抓取

## 目标

系统性解决上述 7 个问题，让未来 agent 不再重蹈覆辙：

| # | 问题 | 解法 | 实现位置 |
|---|------|------|----------|
| 1 | agent 乱写脚本 | SKILL.md 顶部加禁止行为框 + `.gitignore` 不再忽略 | `SKILL.md` 第 0 节 + `.gitignore` |
| 2 | 验证码无感知 | 双侧验证码检测（BOSS + 爱企查），命中即中止整轮 | `scraper.py` + `boss_cdp_raw.py` |
| 3 | stdout 缓冲 | CLI 入口统一调用 `enable_line_buffering()`，SKILL.md 强调 `-u` | 各 CLI 入口 + `SKILL.md` |
| 4 | JSON 命名混乱 | 统一 `aqc_{credit_code}.json`，由 `insight_json_path()` 生成 | `scraper.py` |
| 5 | check 入口缺失 | `--step status` 六区块盘点 | `pipeline.print_status()` |
| 6 | has_insight 未更新 | step5 每导入一家立即 `mark_insight_done()` | `step5_scrape_insights()` |
| 7 | agent 绕过数据访问层 | SKILL.md 禁止 + `db.py` 统一入口 | `SKILL.md` + `db.py` |

## 改动文件清单

### 1. `SKILL.md` — 第 0 节「禁止行为」

**位置**：front matter 之后、第 1 节「决策入口」之前

**内容**：
- 「想做的事 → 正确入口」映射表（6 行）
- 四条禁止规则：
  1. 禁止新建 `check_*.py` / `run_*.py` / `verify_*.py` / `inspect_*.py` 等临时脚本
  2. 禁止绕过 `db.py` 的 `import_*_from_json()` 直接写 SQLite
  3. 禁止用裸路径调用，统一用 `python3 -m scripts.xxx`
  4. 禁止绕过验证码
- 长任务必须加 `-u` 的说明

### 2. `scripts/company_insight/scraper.py` — 验证码检测 + JSON 命名统一

**新增**：
- `InsightBlockedError` 异常类
- `detect_block_page(page_url, page_title, page_text)` — URL/标题/正文三重特征检测
- `_raise_if_blocked(state, credit_code)` — 命中即抛异常
- `BLOCK_URL_MARKERS` / `BLOCK_TITLE_MARKERS` / `BLOCK_TEXT_MARKERS` 常量
- `insight_json_path(credit_code, output_dir)` — 统一返回 `aqc_{credit_code}.json` 路径
- `save_insight_json(data, credit_code)` — 统一落盘
- `import_insight_json(json_path, credit_code, db)` — 统一入库

**接入点**：
- `navigate_and_click_company()` — 搜索页检测
- `scrape_aqc_by_credit_code()` — 详情页检测

### 3. `scripts/boss_cdp_raw.py` — BOSS 侧验证码检测 + 行缓冲

**新增**：
- `SecurityCheckError` 异常类
- `detect_security_check_page()` — URL/标题/正文三重特征
- `enable_line_buffering()` — 行缓冲 helper

**接入点**：
- `scrape_list()` — 列表抓取
- `scrape_details()` — 详情抓取
- `company_detail.extractor.extract_page_text()` — 公司详情提取

### 4. `scripts/company_list/pipeline.py` — 状态入口 + 行缓冲 + 中止恢复

**新增**：
- `print_status()` — 六区块盘点（批次/进度/待爬详情/待爬洞察/JSON 对账/最近入库）
- `classify_insight_files()` — JSON 文件分类（canonical/orphan/legacy/duplicates/unreadable）
- `insight_file_credit_code()` — 从文件名推断 credit_code
- `read_credit_code_from_json()` — 从 JSON 内容回读 credit_code

**修改**：
- `step3_scrape_details()` — 接入 `SecurityCheckError`，中止整轮
- `step5_scrape_insights()` — 接入 `InsightBlockedError`，中止整轮；JSON 已存在时补导入不重抓
- `main()` — 调用 `enable_line_buffering()`

### 5. `scripts/company_list/db.py` — 数据访问层完善

**新增**：
- `resolve_brand_id_by_credit_code(credit_code)` — 通过 credit_code 反查 brand_id
- `get_recent_insight_scrapes(limit=5)` — 最近入库的洞察记录
- `validate_insight_completeness()` — 校验不完整数据

### 6. `.gitignore` — 清理 agent 遗留规则

移除对 `check_*.py` / `run_*.py` 等模式的忽略规则，使这类文件直接出现在 `git status` 里。

### 7. `CHANGELOG.md` — v2.5.0 段落

新增条目涵盖上述所有改动。

## Log Tasks 设计

### 管道执行日志

| 时机 | 日志内容 | 示例 |
|------|----------|------|
| 列表抓取开始 | 关键词、城市、页数 | `=== 列表抓取: AI Agent @ 上海 ===` |
| 列表抓取完成 | 职位数、文件路径 | `列表已保存: output/query/abc123.json` |
| 详情抓取成功 | 公司名、brand_id | `详情抓取成功 [某某公司]: brand_id` |
| 详情抓取失败 | 公司名、错误信息 | `详情爬取失败 [某某公司]: timeout` |
| 洞察抓取成功 | 公司名、credit_code | `洞察抓取成功 [某某公司]: 91310104MA1FR5RY3N` |
| 洞察补导入 | 公司名、文件名 | `洞察补导入 [某某公司]: 复用 aqc_xxx.json` |
| 验证码中止 | 类型、URL、已完成数 | `已中止本轮洞察抓取（已完成 5 家）` |
| 等待间隔 | 等待秒数 | `等待 18s 后抓下一个...` |

### 状态盘点日志（`--step status`）

```
[1] 查询批次
  query_hash      keyword         city        jobs  最早入库
  ----------------------------------------------------------
  abc123def456    AI Agent       上海         45    2026-10-01T10:30:00

[2] 总体进度
  职位            : 45
  唯一公司        : 12
  详情 已完成/待爬: 10 / 2
  洞察 已完成/待爬: 8 / 4

[3] 待爬详情（has_detail=0）
  - brand_id_1
  - brand_id_2

[4] 待爬洞察（has_detail=1 且 has_insight=0）: 4 家
  - 某某公司 | 91310104MA1FR5RY3N
  - 另一公司 | 91310113MA1GNN0NX8
  ... 还有 2 家

[5] 洞察 JSON 对账 (output/insight)
  JSON 文件总数     : 15
  规范命名          : 12  (aqc_{credit_code}.json)
  孤儿（不在批次内）: 1
  旧命名            : 1
  无法解析          : 0
  重复 credit_code  : 1

[6] 最近入库的洞察
  2026-10-01T14:23:00  某某公司  (91310104MA1FR5RY3N)
  2026-10-01T14:20:00  另一公司  (91310113MA1GNN0NX8)
  ...
```

## Agent 行为规范

### 禁止行为

1. **禁止新建临时脚本** — `check_*.py` / `run_*.py` / `verify_*.py` / `inspect_*.py`
2. **禁止绕过数据访问层** — 必须通过 `db.py` 的 `import_*_from_json()` 写 DB
3. **禁止裸路径调用** — 统一用 `python3 -m scripts.xxx`
4. **禁止绕过验证码** — 遇到验证码中止整轮，交人工处理
5. **禁止直接操作 SQLite** — 用 `db.py` 提供的方法

### 必须行为

1. **长任务加 `-u`** — `python3 -u -m scripts.company_list.pipeline --step insight`
2. **先查状态再动手** — `python3 -m scripts.company_list.pipeline --step status`
3. **导入用统一入口** — `db.import_*_from_json()` 而非手写 INSERT
4. **JSON 命名统一** — `aqc_{credit_code}.json`（由 `scraper.insight_json_path()` 生成）

## 验证

- 语法自检：`python3 -m py_compile scripts/company_list/pipeline.py`
- 语法自检：`python3 -m py_compile scripts/company_insight/scraper.py`
- 语法自检：`python3 -m py_compile scripts/boss_cdp_raw.py`
- 单测全量通过：`tests.chrome_setup` + `tests.company_detail` + `tests.company_list`

## 风险

- `company_list` 没有 `credit_code` 列是设计决策（避免数据冗余），但需要 JOIN `company_detail` 才能拿到
- 验证码检测可能误报（页面正文包含"验证"等关键词），但只匹配前 2000 字符降低误报率
- JSON 命名统一后，旧命名文件需要手动清理（`--step status` 的 `[5]` 区块会列出）

## 溯源

- 本 spec：`specs/task_agent_observability.md`
- CHANGELOG：v2.5.0 未发布段落
