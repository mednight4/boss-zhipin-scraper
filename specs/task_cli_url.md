# Task: CLI --url 参数 — 一条 URL 跑完整管道

> **当前实现契约（优先于本历史设计记录）**
>
> 本文件记录 `--url` 入口的历史方案。`company_list` 没有 `credit_code` 列；详情 extractor 取出的统一社会信用代码写入 `company_detail.credit_code`，爱企查以此搜索，`company_id/pageid` 只用于页面 URL 导航。三表使用 `company_list.encrypt_brand_id = company_detail.brand_id = company_insight.brand_id` 连接，空库顺序是 `list → company_list → detail → company_detail.credit_code → insight → company_insight`。
>
> 当前 URL 入口不注入 `scrape_insight_fn`，不能据此声称会自动完成洞察；入口分支优先于 `--db`。`PipelineState.decide()` 可能在 `detail_pending>0` 时返回 `SKIP`（只按新鲜度判断），而 `run()` 处于 `LIST_JSON_SAVED` 时会再次调用 `_step_scrape_list`，不会自动把现有列表 JSON 导入。`--step all` 当前总是报错。
>
> **历史记录标记**：下文的目标、实现片段和验证项保留原方案背景；与当前契约冲突的“完整管道”或恢复语义属于原方案（已过时）。

## 目标

新增 `--url` CLI 参数到 `boss_cdp_raw.py`。用户给一条 BOSS 查询 URL，系统自动解析 keyword/city/filters 并通过 PipelineState 一键跑完整管线。

URL 是语义最精确的查询方式，一条 URL 等价于 keyword + city + 所有筛选条件的组合。

## 背景

当前 PipelineState 已有 Python API（`query()` / `PipelineState`），但 CLI 入口仍需手动传 `--keyword` / `--city` / `--scale` 等零散参数。BOSS 搜索结果页的 URL 天然包含全部查询条件，直接给 URL 是最自然的交互方式。

## URL 解析规则

BOSS 查询 URL 格式：
```
https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent&scale=303&experience=105
```

解析映射：
- `query` → keyword（需 URL decode）
- `city` → city_input（9 位城市码，缺失默认 `101020100` 上海）
- `scale` / `stage` / `salary` / `experience` / `degree` / `industry` → filters dict
- 其他字段忽略

## 修改 1：`scripts/boss_cdp_raw.py`

### argparse

在 `--detail-json-dir` 之后添加：

```python
p.add_argument("--url", default=None,
               help="BOSS 查询 URL，自动解析 keyword/city/filters 并跑完整管道")
```

### main() 入口

在 `require_runtime_dependencies` 之后、`if args.db:` 之前添加：

```python
if args.url:
    _run_url_pipeline(args)
    return
```

### _run_url_pipeline(args) 函数

新增函数（位于 `_run_db_pipeline` 之前）：

```python
def _run_url_pipeline(args):
    from urllib.parse import urlparse, parse_qs, unquote
    from scripts.company_list.pipeline import PipelineState

    parsed = urlparse(args.url)
    params = parse_qs(parsed.query)

    keyword = unquote(params.get("query", [""])[0])
    city = params.get("city", [""])[0]
    if not city:
        city = "101020100"

    filters = {}
    for key in ["scale", "stage", "salary", "experience", "degree", "industry"]:
        val = params.get(key, [None])[0]
        if val:
            filters[key] = val

    pipe = PipelineState(args.url)
    action = pipe.decide()
    if action == "SKIP":
        info = pipe.db.get_query_info(pipe.query_hash)
        pipe.db.close()
        return

    result = pipe.run(
        keyword=keyword, city_input=city, filters=filters,
        max_pages=args.pages, cdp_port=args.cdp_port, fmt=args.format,
    )
    pipe.db.close()
```

## 修改 2：`SKILL.md`

在「管道工作流 (Pipeline)」章节的「使用方式」子节中添加 CLI 示例：

```bash
# 给 URL 跑完整管道（自动决策跳/查/恢复/刷新）
python "$SCRIPT_PATH" --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent"

# 带筛选条件
python "$SCRIPT_PATH" --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent&scale=303&experience=105"
```

## 修改 3：`CHANGELOG.md`

未发布段落新增独立条目。

## 不需要修改的文件

- `scripts/company_list/db.py` — 无变更
- `scripts/company_list/pipeline.py` — 无变更（复用现有 PipelineState）
- `scripts/company_list/__init__.py` — 无变更
- `specs/task_pipeline_state_machine.md` — 不修改，保持独立
- `tests/company_list/test_db.py` — 无变更

## 验证

- `python -m py_compile scripts/boss_cdp_raw.py` — 语法
- `python "$SCRIPT_PATH" --help` — 确认 --url 参数出现在帮助中

## 溯源

- Plan 文件：由 Agent 自动生成
- 本 spec：`specs/task_cli_url.md`
- CHANGELOG：未发布段落新增条目
