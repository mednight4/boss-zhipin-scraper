# Task: 详情爬取增量同步 — 逐公司写入 DB

## 现状问题

详情爬取（step3）采用「全部爬完再统一导入 DB」的模式：
1. 循环爬取每个公司详情 → 写 JSON 文件 → 路径收集到内存列表 `json_paths`
2. 循环结束后进入 step4 → 统一读取 JSON → `import_detail_from_json` → `mark_detail_done`

**Bug**：若进程在 step3 和 step4 之间中断（用户 Ctrl-C、崩溃、网络断开），所有已爬详情仅存在于 JSON 文件中，DB 完全未同步。重跑时 `get_pending_detail_brands` 仍返回这些公司（因为 `has_detail=0`），造成重复抓取。

### 影响

| 中断时机 | 后果 |
|----------|------|
| step3 进行中（已爬 50/200 家） | company_detail 表为空，company_list.has_detail 全为 0 |
| step3 完成后、step4 开始前 | 同上（最脆弱的时间窗口） |
| step4 中途中断 | 部分导入，但无标记，重跑可能部分重复 |

### 根因

DB 写入与文件写入解耦为两个独立步骤，中间存在"数据孤儿"窗口。设计初衷是批量导入性能更好，但牺牲了中断安全性。

## 目标

改为「爬一个公司 → 立即同步到 DB」的增量模式：
- 每个公司详情 JSON 写入完成后，立即调用 `import_detail_from_json` + `mark_detail_done`
- step4 降级为兜底导入（处理旧数据或中断恢复场景）
- 不影响 `scrape_details` 在 `boss_cdp_raw.py` CLI 中的行为（无 DB 模式下仍只写 JSON）

## 改动文件清单

### 1. `scripts/company_list/pipeline.py` — `step3_scrape_details`（模块级函数）

```python
# 修改前
json_paths = []
for brand in brands:
    ...
    json.dump(detail, f, ...)
    json_paths.append((json_path, brand_id))
return json_paths

# 修改后
imported = 0
for brand in brands:
    ...
    json.dump(detail, f, ...)
    db.import_detail_from_json(json_path, brand_id)
    db.mark_detail_done(brand_id)
    imported += 1
return imported
```

`run_full_pipeline` 中的对应调用和打印同步修改：
```python
# 修改前
json_paths = step3_scrape_details(db, scrape_detail_fn)
detail_imported = step4_import_details(db, json_paths)

# 修改后
imported = step3_scrape_details(db, scrape_detail_fn)
fallback_imported = step4_import_details(db)  # 兜底
```

### 2. `scripts/company_list/pipeline.py` — `PipelineState._step_scrape_details`

同上模式，状态机方法内逐公司同步 DB：

```python
imported = 0
for brand in brands:
    ...
    json.dump(detail, f, ...)
    self.db.import_detail_from_json(json_path, brand_id)
    self.db.mark_detail_done(brand_id)
    imported += 1
print(f"detail sync: {imported}/{len(brands)} company")
```

### 3. `scripts/boss_cdp_raw.py` — `_run_db_pipeline` 的详情循环

CLI 中 `--db --step detail` 路径的同步修复：

```python
# 修改前: 只写 json_paths.append → step4 统一导入
# 修改后: 写入 JSON 后立即 db.import_detail_from_json + mark_detail_done
detail_imported = 0
for brand in brands:
    ...
    json.dump(detail, f, ...)
    json_paths.append((json_path, brand_id))   # 保留列表供 step4 兜底
    db.import_detail_from_json(json_path, brand_id)
    db.mark_detail_done(brand_id)
    detail_imported += 1

# step4 降为兜底
fallback_imported = 0
for json_path, brand_id in json_paths:
    if not os.path.exists(json_path):
        continue
    db.import_detail_from_json(json_path, brand_id)
    db.mark_detail_done(brand_id)
    fallback_imported += 1
print(f"导入详情: {detail_imported} (兜底+{fallback_imported}) 个公司")
```

### 不改的部分

- `db.import_detail_from_json` / `db.mark_detail_done` — 方法本身不变
- `step4_import_details` — 保留为兜底入口（无参数调用）
- `scrape_list` — 列表抓取链路不受影响
- `scrape_company_detail` — extractor 函数不受影响

## 测试策略

现有 `tests.company_list.test_db` 已覆盖 `import_detail_from_json` + `mark_detail_done` 的独立行为。增量同步逻辑为已有方法的组合调用，单测行为不变。

- `tests.chrome_setup.test_chrome_setup` — 版本一致性 + 城市码表（不受影响）
- `tests.company_list.test_db` — 22 个 JobDatabase 单测（不受影响）
- `tests.company_detail.test_extractor` — 25 个解析单测（不受影响）

## 风险

- `db.import_detail_from_json` 内部有 `INSERT OR REPLACE`（upsert 语义），幂等调用安全
- step4 兜底逻辑兼容旧 JSON 文件和部分导入场景
- JSON 文件仍写入磁盘（调试用），不影响现有文件行为
