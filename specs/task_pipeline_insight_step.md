# Task: Pipeline 洞察环节完善 — step5/step6 真正接入第三张表

## 现状问题

`e54af2c` 提交了 `step5_scrape_insights()` 函数和 `company_insight` 表设计，但存在以下缺口：

1. **`boss_cdp_raw.py` 的 insight step 是占位**：`if step == "insight"` 只打印"功能预留"，没有真正调用 `scrape_aqc_by_credit_code`
2. **状态机缺 `INSIGHT_DONE`**：`PipelineState` 执行 step5 后直接跳到 `COMPLETE`，没有中间状态
3. **无兜底导入**：step5 抓取过程中断后，已生成的 `aqc_*.json` 无法通过 step6 补导
4. **`skill/pipeline.md` 完全没体现 step5/step6**：状态机图、步骤表、ER 图均缺 insight 环节
5. **`_load_state` 判断逻辑有 bug**：`info.get("insight_pending", 0)` 在 `get_query_info` 中总是返回 int，不会为 None

## 目标

Pipeline 完整覆盖三表：列表 → 详情 → 洞察，每步可中断恢复，JSON 先行落地后导入 DB。

## 改动文件清单

### 1. `scripts/company_list/pipeline.py`

**状态机**：
```
IDLE → LIST_JSON_SAVED → LIST_DB_IMPORTED → DETAIL_DONE → INSIGHT_DONE → COMPLETE
```

**`_load_state` 修正**：
```python
# 修改前: 用 info.get("insight_pending", 0) 判断（总是 int，逻辑正确但可读性差）
# 修改后: 显式读取 detail_pending 和 insight_pending，分三种情况
if detail_pending > 0:
    self.step = "LIST_DB_IMPORTED"
elif insight_pending > 0:
    self.step = "DETAIL_DONE"
else:
    self.step = "COMPLETE"
```

**新增 `step6_import_insights()`**：
- 扫描 `output/insight/aqc_*.json`
- 从文件名解析 `credit_code`
- 通过 `db.resolve_brand_id_by_credit_code()` 反查 `brand_id`
- 导入 `company_insight` 表 + 更新 `has_insight=1`

**`run()` 方法**：
- step5-6 执行后状态设为 `INSIGHT_DONE`
- 最终归一化为 `COMPLETE`
- `_step_scrape_insights` 内部调用 step5 + step6

**`run_full_pipeline()`**：
- step5 后追加 step6 兜底导入

### 2. `scripts/company_list/db.py`

**新增 `resolve_brand_id_by_credit_code(credit_code)`**：
- 通过 `company_detail.credit_code` 反查 `company_list.encrypt_brand_id`
- 用于 step6 兜底导入时关联 brand_id

### 3. `scripts/boss_cdp_raw.py`

**`_run_db_pipeline` 的 insight step**：
```python
# 修改前: 只打印"功能预留"
# 修改后: 真正调用 step5_scrape_insights + step6_import_insights
if step == "insight":
    from scripts.company_list.pipeline import step5_scrape_insights, step6_import_insights, INSIGHT_DIR
    from scripts.company_insight.scraper import scrape_aqc_by_credit_code

    def _scrape_insight(credit_code):
        return scrape_aqc_by_credit_code(credit_code, cdp_port=args.cdp_port)

    insight_imported = step5_scrape_insights(db, _scrape_insight, INSIGHT_DIR)
    insight_fallback = step6_import_insights(db, insight_json_dir=INSIGHT_DIR)
```

**统计输出**：追加洞察统计 `done_insight/pending_insight`

### 4. `skill/pipeline.md`

- 状态机图加 `DETAIL_DONE → INSIGHT_DONE → COMPLETE`
- 步骤表加 step5/step6
- ER 图加 `company_insight` 表
- 中断恢复场景加"详情完成，洞察待爬 → SCRAPE_INSIGHT"
- 文件路径表加洞察 JSON 归档路径

### 5. `SKILL.md`

- 步骤表加 step6 行

## 不改的部分

- `scripts/company_insight/scraper.py` — 爬虫逻辑不变
- `tests/` — 不改测试（现有测试覆盖 db.py 和 pipeline.py 基础逻辑）
- `AGENTS.md` — 上次同步已修正，本次无新问题

## 验证

- 语法自检：`python3 -m py_compile scripts/company_list/pipeline.py`
- 语法自检：`python3 -m py_compile scripts/company_list/db.py`
- 语法自检：`python3 -m py_compile scripts/boss_cdp_raw.py`
- 单测全量通过：`tests.chrome_setup` + `tests.company_detail` + `tests.company_list`

## 风险

- `resolve_brand_id_by_credit_code` 依赖 `company_detail.credit_code` 已填充，需 step3-4 先完成
- step5 的 `scrape_aqc_by_credit_code` 需要 Chrome CDP 在线，否则会抛异常（step5 内部已 try/except 处理）
- 纯逻辑变更，无用户可见行为变化（insight step 之前是占位，现在真正执行）
