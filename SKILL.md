---
name: boss-zhipin-scraper
description: "Scrape BOSS直聘 through a logged-in Chrome or Microsoft Edge CDP session, collect job listings and company data, and generate job-market summaries. Use when the user asks to search, collect, inspect, or analyze BOSS直聘 job data."
version: 2.5.0
author: eatmoreduck
license: MIT
platforms: [macos, linux, windows]
metadata:
  hermes:
    tags: [scraper, jobs, cdp, zhipin, boss直聘]
---

# BOSS直聘 Skill

本 Skill 通过用户本人已经登录的 Chrome 或 Microsoft Edge 的 Chrome DevTools Protocol（CDP）连接 BOSS直聘，抓取个人求职分析所需的公开职位和公司数据。

## 0. Agent 启动协议

本文件是 Skill 的最小启动入口。先按任务类型选择对应的短工作流文档，不要在只读分析任务中加载抓取协议：

- 已有数据库的筛选、统计或链接查询：读取 [`skill/query_workflow.md`](skill/query_workflow.md)。
- 新抓取、继续/恢复抓取、进度检查：读取 [`skill/agent_workflow.md`](skill/agent_workflow.md)。
- 参数字段说明：按需读取 [`skill/reference.md`](skill/reference.md)。
- Pipeline 状态机和恢复契约：按需读取 [`skill/pipeline.md`](skill/pipeline.md)。

只读分析不得因为数据较旧而隐式抓取或刷新。
## 1. 绝对规则

### 1.1 现有入口优先

| 需求 | 唯一优先入口 |
|---|---|
| 检查环境、CDP、登录 | `uv run python -m scripts.boss_cdp_raw --check --cdp-port 9222` |
| 检查真实搜索链路 | `uv run python -m scripts.boss_cdp_raw --smoke-test --cdp-port 9222` |
| 查看批次、待办和 JSON 对账 | `uv run python -m scripts.company_list.pipeline --step status --db-path output/jobs.db` |
| 查询已有数据库结果 | `uv run python -m scripts.company_list.query --db-path output/jobs.db --query-hash QUERY_HASH --employee-min 50 --employee-max 100` |
| 批量抓 BOSS 公司详情 | `uv run python -u -m scripts.company_list.pipeline --step detail --port 9222 --db-path output/jobs.db`（先补导入当前待办品牌的详情 JSON，再抓剩余项）|
| 批量抓爱企查洞察 | `uv run python -u -m scripts.company_list.pipeline --step insight --port 9222 --db-path output/jobs.db`（抓取后补导入残留 JSON）|
| 执行列表、详情和洞察完整管道 | `uv run python -u -m scripts.company_list.pipeline --step all --keyword "AI Agent" --city 101020100 --db-path output/jobs.db` |
| 导入已有列表 JSON | `uv run python -m scripts.company_list.pipeline --step list --list-json <path> --db-path output/jobs.db` |
| 单条爱企查查询 | `uv run python -u -m scripts.company_insight.scraper <credit_code> --port 9222 --db-path output/jobs.db` |

### 1.2 禁止事项

- 禁止新建 `check_*.py`、`run_*.py`、`verify_*.py`、`inspect_*.py` 等临时脚本。
- 禁止绕过 `scripts/company_list/db.py` 的 `import_*_from_json()` 直接写 SQLite。
- 禁止把 `credit_code` 当作 `brand_id`。
- 禁止把爱企查 `company_id/pageid` 当作项目三表连接键。
- 禁止根据 JSON 文件数量推断 `has_detail` 或 `has_insight`；详情或洞察完成均要求结果表有对应 `brand_id` 记录且列表状态字段为 `1`。
- 禁止把列表导入后的两个 pending 数字直接解释成 detail 和 insight 可以并行。
- 禁止绕过登录验证、验证码和风控，不使用代理轮换、指纹伪造或验证码识别。
- 长任务必须使用 `-u`，让 Agent 能实时读取进度。

## 2. 当前数据契约

```text
company_list.encrypt_brand_id
    = company_detail.brand_id
    = company_insight.brand_id

company_detail.credit_code
    → 爱企查搜索输入

Aiqicha company_id / pageid
    → 爱企查详情页面导航标识
```

当前代码的真实执行链：

```text
列表抓取
  → company_list
  → BOSS 公司详情抓取
  → company_detail.credit_code
  → 爱企查洞察抓取
  → company_insight
```

当前列表映射保存 BOSS 的 `encrypt_brand_id`，没有把统一社会信用代码写入 `company_list`。因此列表导入完成后通常只能启动详情步骤；详情成功并产生 `company_detail.credit_code` 后，才能启动洞察步骤。

最终查询以 `company_list` 为主表：

```sql
FROM company_list AS cl
LEFT JOIN company_detail AS cd
  ON cl.encrypt_brand_id = cd.brand_id
LEFT JOIN company_insight AS ci
  ON cl.encrypt_brand_id = ci.brand_id
```

## 3. 任务路由

### 查询已完成数据

用户只要求筛选已有数据库中的岗位/公司时，读取 [`skill/query_workflow.md`](skill/query_workflow.md)，直接使用只读查询 CLI。不要执行 `CHK-CDP`、不要生成新 `query_hash`、不要运行 `--step status`，除非用户也要求了解管道进度。

### 查询或抓取新任务

先确认：

```text
keyword
city 或 BOSS 查询 URL
filters（可选）
depth：列表、详情、洞察或全部
```

没有 URL 时调用项目方法解析城市并生成查询 URL：

```powershell
uv run python -c "from scripts.boss_cdp_raw import resolve_city; print(resolve_city('上海'))"
uv run python -c "from scripts.company_list.db import build_query_url; print(build_query_url('AI Agent','101020100',{'salary':'405'}))"
uv run python -c "from scripts.company_list.db import compute_query_hash; print(compute_query_hash('QUERY_URL'))"
```

用户只给关键词或城市而没有足够信息时，先补问，不启动抓取。

### 用户提供 BOSS URL

URL 管道将 URL 规范化为批次身份，复用 `--db-path` 指定的数据库，并默认执行列表、详情和洞察完整流程：

```powershell
uv run python -u -m scripts.boss_cdp_raw --url "QUERY_URL" --pages 3 --db-path output/jobs.db --cdp-port 9222
```

显式跳过洞察时使用 `--no-insight`。仅抓列表时同时传入 `--no-detail --no-insight`；跳过的阶段不会被标记为数据库已完成，结果中仍会返回真实待办。

URL 只提供查询条件，不替代 Agent 对抓取深度的判断。

### 继续或恢复任务

先执行：

```powershell
uv run python -m scripts.company_list.pipeline --step status --db-path output/jobs.db
```

根据 `pending_detail`、`pending_insight`、JSON 对账和 `credit_code` 输入完整性选择下一步，不要根据上一次日志猜测。

### 查询已有结果

只读筛选使用 [`query_workflow.md`](query_workflow.md) 的批次列表和查询 CLI；查询可读取旧批次，不因新鲜度自动刷新。只有用户明确要求抓取或更新数据时才进入抓取流程。

## 4. 状态机摘要

```mermaid
stateDiagram-v2
    [*] --> IDLE
    IDLE --> LIST_JSON_SAVED : 列表抓取
    LIST_JSON_SAVED --> LIST_DB_IMPORTED : 导入company_list
    LIST_DB_IMPORTED --> DETAIL_PENDING : has_detail未完成或详情记录缺失
    DETAIL_PENDING --> DETAIL_DONE : 详情行已入库且has_detail=1
    DETAIL_DONE --> INSIGHT_PENDING : credit_code可用
    DETAIL_DONE --> INSIGHT_INPUT_MISSING : 洞察待办缺少credit_code
    INSIGHT_PENDING --> COMPLETE : 洞察行已入库且has_insight=1
    COMPLETE --> [*]
    DETAIL_PENDING --> SECURITY_BLOCKED : BOSS验证
    INSIGHT_PENDING --> INSIGHT_BLOCKED : 爱企查风控
```

状态含义：

- `IDLE`：没有目标列表 JSON 和 DB 批次。
- `LIST_JSON_SAVED`：列表 JSON 已落盘但尚未导入 `company_list`。
- `LIST_DB_IMPORTED`：列表已入库，通常有 `has_detail=0`。
- `DETAIL_PENDING`：需要访问 BOSS 公司详情页并解析 `credit_code`。
- `DETAIL_DONE`：详情待办为零；只有在详情表记录存在且 `has_detail=1` 时详情才算完成。
- `INSIGHT_PENDING`：使用 `company_detail.credit_code` 查询爱企查。
- `INSIGHT_INPUT_MISSING`：洞察待办缺少 `credit_code`，不能标记为全部完成。
- `COMPLETE`：详情、洞察结果表记录及列表状态标记一致，数据库待办为零。
- `SECURITY_BLOCKED` / `INSIGHT_BLOCKED`：退出码 `2`，必须人工处理后恢复。

完整检查工具和状态分支见 [`skill/agent_workflow.md`](skill/agent_workflow.md)。

## 5. 安装与运行参考

安装参考：完整复制仓库时，至少包括 `skill/agent_workflow.md`、数据库管道模块和摘要入口，例如：

```bash
cp boss-zhipin-scraper/scripts/job_summary.py <skill-dir>/scripts/
```


参数和输出格式见 [`skill/reference.md`](skill/reference.md)。`scripts/job_summary.py` 负责读取职位 JSON 生成聚合分析和求职提示词；SQLite 已完成数据的条件筛选使用 `scripts.company_list.query` 和 [`skill/query_workflow.md`](skill/query_workflow.md)。

Pipeline 技术状态和数据库参考见 [`skill/pipeline.md`](skill/pipeline.md)。

面向用户的完整说明见 [`README.md`](README.md) 和 [`README.en.md`](README.en.md)。

## 6. 版本与开发约束

当前版本为 `2.5.0`。修改版本号时必须同步：

- `scripts/boss_cdp_raw.py`
- `pyproject.toml`
- `SKILL.md`
- `README.md`
- `README.en.md`
- `uv.lock`

本次修复覆盖列表、详情、洞察和 CLI 管道实现；单元测试与语法检查按 `skill/agent_workflow.md` 执行。真实 Edge 抓取验证仍须在合并前按 `AGENTS.md` 完成，本轮不执行真实抓取。
