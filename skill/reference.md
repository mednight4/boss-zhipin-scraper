# 参数与输出参考

> Agent 的执行顺序和检查工具见 [`agent_workflow.md`](agent_workflow.md)。本文件只描述参数、输出和只读数据关系。

## CLI 入口

项目统一使用：

```text
uv run python -m scripts.boss_cdp_raw ...
uv run python -m scripts.company_list.pipeline ...
uv run python -m scripts.company_insight.scraper ...
```

长任务加 `-u`。

## 核心参数

| 参数 | 说明 |
|---|---|
| `--keyword` | BOSS 搜索关键词 |
| `--city` | 中文城市名或 9 位 city_code |
| `--pages` | 列表抓取页数，受 `BOSS_MAX_PAGES` 限制 |
| `--format` | `json` 或 `csv` |
| `--detail` | 抓取职位详情，默认开启 |
| `--no-detail` | 不抓取职位详情 |
| `--max-details` | 职位详情数量上限 |
| `--analysis` | 输出职位分析 |
| `--cdp-port` | CDP 端口，默认 `9222` |
| `--url` | 使用 BOSS 查询 URL 自动解析 keyword、city 和筛选条件 |
| `--db` | 启用 SQLite 管道 |
| `--db-path` | 数据库路径，默认 `output/jobs.db` |
| `--step` | `list`、`detail`、`insight`、`all` 或 `status` |
| `--list-json` | 从现有列表 JSON 导入 |
| `--detail-json-dir` | 从现有详情 JSON 目录导入 |
| `--insight-delay` | 洞察抓取间隔基准秒数 |
| `--check` | 检查依赖、CDP 和 BOSS 登录态 |
| `--smoke-test` | 验证真实 BOSS 搜索响应，不写结果文件 |
| `--setup-edge` | 启动 Edge CDP 隔离 profile |
| `--setup-chrome` | 启动 Chrome CDP 隔离 profile |
| `--no-wait-login` | 启动浏览器后不等待登录 |
| `--stop-edge` | 关闭 Edge 隔离 profile |
| `--stop-chrome` | 关闭 Chrome 隔离 profile |

## 筛选代码

| 参数 | 代码示例 |
|---|---|
| `--scale` | `301` 0-20人，`302` 20-99人，`303` 100-499人，`304` 500-999人，`305` 1000-9999人，`306` 10000人以上 |
| `--salary` | `402` 3K以下，`403` 3-5K，`404` 5-10K，`405` 10-20K，`406` 20-50K，`407` 50K以上 |
| `--experience` | `101` 经验不限，`102` 应届生，`103` 1年以内，`104` 1-3年，`105` 3-5年，`106` 5-10年，`107` 10年以上，`108` 在校生 |
| `--degree` | `202` 大专，`203` 本科，`204` 硕士，`205` 博士，`206` 高中，`208` 中专/中技，`209` 初中及以下 |
| `--stage` | `801` 未融资，`802` 天使轮，`803` A轮，`804` B轮，`805` C轮，`806` D轮及以上，`807` 已上市，`808` 不需要融资 |
| `--industry` | 使用项目当前的行业代码映射 |

## 状态和字段关系

```text
company_list.encrypt_brand_id
    = company_detail.brand_id
    = company_insight.brand_id

company_detail.credit_code
    → 爱企查搜索输入

Aiqicha company_id / pageid
    → 爱企查页面导航标识
```

当前 `company_list` 没有 `credit_code` 列。不要写：

```sql
SELECT credit_code FROM company_list;
```

需要统一社会信用代码时：

```sql
SELECT cl.encrypt_brand_id,
       cd.brand_id,
       cd.credit_code,
       ci.credit_code AS insight_credit_code
FROM company_list AS cl
LEFT JOIN company_detail AS cd
  ON cl.encrypt_brand_id = cd.brand_id
LEFT JOIN company_insight AS ci
  ON cl.encrypt_brand_id = ci.brand_id
WHERE cl.query_hash = ?;
```

## 输出路径

| 产物 | 路径 |
|---|---|
| SQLite | `output/jobs.db` |
| 查询列表 JSON | `output/query/{query_hash}.json` |
| BOSS 公司详情 JSON | `output/company/{brand_id}.json` |
| 爱企查洞察 JSON | `output/insight/aqc_{credit_code}.json` |
| 普通 CLI 列表结果 | `~/.boss-zhipin-scraper/job-result/boss_jobs_*.json` |
| 普通 CLI 详情结果 | `~/.boss-zhipin-scraper/job-result/boss_details_*.json` |

## 管道命令

首次或新的列表批次：

```powershell
uv run python -u -m scripts.boss_cdp_raw --db --step list --keyword "AI Agent" --city 101020100 --pages 3 --cdp-port 9222
```

导入已有列表 JSON：

```powershell
uv run python -m scripts.company_list.pipeline --step list --list-json output/query/QUERY_HASH.json --db-path output/jobs.db
```

抓 BOSS 公司详情：

```powershell
uv run python -u -m scripts.company_list.pipeline --step detail --port 9222 --db-path output/jobs.db
```

抓爱企查洞察：

```powershell
uv run python -u -m scripts.company_list.pipeline --step insight --port 9222 --insight-delay 15 --db-path output/jobs.db
```

查看状态：

```powershell
uv run python -m scripts.company_list.pipeline --step status --db-path output/jobs.db
```

当前洞察必须在详情产生 `company_detail.credit_code` 后执行。

## 爱企查单条查询

```powershell
uv run python -u -m scripts.company_insight.scraper CREDIT_CODE --port 9222 --delay 15
```

此处的 `CREDIT_CODE` 是统一社会信用代码，不是 BOSS `encrypt_brand_id`，也不是爱企查内部 `company_id/pageid`。

## 结果字段来源

- 职位标题、薪资、城市、标签、`encrypt_brand_id`：BOSS 列表响应。
- 公司名称、公司简介、工商信息、`credit_code`：BOSS 公司详情页。
- 法定代表人、注册资本、登记状态、企业类型等洞察字段：爱企查详情页。
- `has_detail`、`has_insight`：`company_list` 上的管道状态字段。

## 风控退出

BOSS 或爱企查命中验证页时，程序退出码为 `2`，保留已完成进度并提示人工处理。完成验证后重跑原命令，不自动绕过。
