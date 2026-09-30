# Task: 爱企查 scraper 反爬机制补全

## 现状问题

`scripts/company_insight/scraper.py` 的抓取防护薄弱，连续快速导航易触发爱企查风控：

| 机制 | extractor.py (已防护) | aqc scraper (本次前) |
|------|---------------------|---------------------|
| 滚动回看仿真（15% 概率上滚） | 有 `_human_scroll` | 无 |
| 鼠标抖动（40% 概率） | 有 `_human_mouse_jitter` | 无 |
| 阅读停顿（30% 概率 2-4s） | 有 | 无 |
| 公司间随机延迟（10-25s） | 有 `delay` 参数 | 无 |

当 `pipeline.py` 的 `step5_scrape_insights` 循环调用 `scrape_aqc_by_credit_code` 时，公司之间零间隔 + 固定节奏滚动 = 典型的机器行为特征。

## 目标

爱企查 scraper 的防护等级对齐 `scripts/company_detail/extractor.py`，三层仿真全部补齐。

## 改动文件

### `scripts/company_insight/scraper.py`

**新增两个私有 helper 函数**（CDP 交互层，对齐 extractor.py）：

```python
def _human_scroll(ws, sid):
    """模拟人类滚动：随机次数(3-6)、随机距离、15%概率回看、30%概率阅读停顿。"""
    for _ in range(random.randint(3, 6)):
        if random.random() < 0.15:
            delta = -random.randint(80, 200)      # 回看
        else:
            delta = random.randint(200, 600)       # 正常下滚
        ws.eval_js(f"window.scrollBy(0, {delta})", sid)
        if random.random() < 0.3:
            time.sleep(random.uniform(2.0, 4.0))   # 阅读停顿
        else:
            time.sleep(random.uniform(0.5, 1.5))

def _human_mouse_jitter(ws, sid):
    """40% 概率移动鼠标位置。"""
    if random.random() < 0.4:
        ws.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": random.randint(200, 800),
            "y": random.randint(200, 600)
        }, sid)
        time.sleep(random.uniform(0.5, 1.5))
```

**重写 `extract_page_text`**：删除内联固定节奏滚动循环，调用 `_human_scroll` + `_human_mouse_jitter`。

**`scrape_aqc_by_credit_code` 新增 `delay` 参数**：
- 默认 `delay=15`，实际间隔 `uniform(max(delay-5, 5), delay+5)` = 10-20s
- `finally` 块中执行延迟（无论成功失败都等待）
- 对齐 extractor.py 的 `delay=15` 防护等级

**CLI `main()` 新增 `--delay` 参数**：
- `python -m scripts.company_insight.scraper <credit_code> [--port 9222] [--delay 15]`

## 不改的部分

- `pipeline.py` — 延迟下沉到 `scrape_aqc_by_credit_code` 内部，所有调用方自动获得
- `boss_cdp_raw.py` — 已有完整防护
- `parse_*` 系列纯函数 — 无浏览器交互
- `extractor.py` — 已有完整防护，不改

## 测试策略

现有测试全为纯文本解析和 DB 操作，不调用 CDP → 无需修改，预期全绿。

## 风险

- `_human_scroll` / `_human_mouse_jitter` 为私有函数（下划线前缀），不进 `__init__.py` 导出
- `delay` 参数默认值确保向后兼容，现有调用方无需修改
- `scroll_rounds` 参数保留（向后兼容），但不再使用（`_human_scroll` 内部自行决定次数）
