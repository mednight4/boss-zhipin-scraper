# Task: extractor 反爬机制补全

## 现状问题

`scripts/company_detail/extractor.py` 的抓取防护弱于 `scripts/boss_cdp_raw.py` 的详情链路：

| 机制 | boss_cdp_raw.py 详情 | extractor.py |
|------|---------------------|--------------|
| 滚动回看仿真（15% 概率上滚） | 有 | 无 |
| 鼠标抖动（40% 概率） | 有 | 无 |
| 阅读停顿（30% 概率 2-4s） | 有 | 无 |
| 公司间随机延迟（10-25s） | 有 | 无 |

当 `pipeline.py` 的 `step3_scrape_details` 循环调用 `scrape_company_detail` 时，公司之间零间隔，连续快速导航易触发 BOSS `_security_check` 风控。

## 目标

extractor.py 的防护等级对齐 boss_cdp_raw.py 详情链路，三层仿真全部补齐：
1. 滚动行为仿真（回看 + 快慢交替 + 阅读停顿）
2. 鼠标抖动仿真
3. 公司间随机延迟

## 设计

### 新增 helper 函数（CDP 交互层）

在 `extract_page_text` 上方新增两个模块级私有函数：

```python
def _human_scroll(ws, sid):
    """模拟人类滚动：随机次数、随机距离、偶尔回看、快慢交替。"""
    for _ in range(random.randint(3, 6)):
        if random.random() < 0.15:
            delta = -random.randint(80, 200)
        else:
            delta = random.randint(200, 600)
        ws.eval_js(f"window.scrollBy(0, {delta})", sid)
        if random.random() < 0.3:
            time.sleep(random.uniform(2.0, 4.0))
        else:
            time.sleep(random.uniform(0.5, 1.5))


def _human_mouse_jitter(ws, sid):
    """偶尔移动鼠标位置，仿真人在页面上活动。"""
    if random.random() < 0.4:
        ws.send("Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": random.randint(200, 800),
            "y": random.randint(200, 600)
        }, sid)
        time.sleep(random.uniform(0.5, 1.5))
```

逻辑数值与 boss_cdp_raw.py 保持一致。

### 重写 extract_page_text

删除内联滚动循环，调用 `_human_scroll` + `_human_mouse_jitter`：

```python
def extract_page_text(ws, sid, url, scroll_rounds=8):
    ws.send("Page.navigate", {"url": url}, sid)
    time.sleep(random.uniform(5, 8))

    _human_scroll(ws, sid)
    _human_mouse_jitter(ws, sid)
    ws.eval_js("window.scrollTo(0, 0)", sid)
    time.sleep(0.5)
    ...
```

`scroll_rounds` 参数保留（向后兼容），但不再使用（`_human_scroll` 内部自行决定次数）。

### scrape_company_detail 新增 delay 参数

```python
def scrape_company_detail(url, cdp_port=CDP_PORT, delay=15):
```

`delay` 含义：公司间间隔基准秒数。`finally` 块中执行：

```python
gap = random.uniform(max(delay - 5, 5), delay + 5)
print(f"  等待 {gap:.0f}s 后抓下一个...\n")
time.sleep(gap)
```

默认 15 → 实际间隔 10-20s，对齐 boss_cdp_raw.py 的 10-25s。

### 不改的部分

- `pipeline.py` —— 延迟下沉到 `scrape_company_detail` 内部，所有调用方自动获得
- `boss_cdp_raw.py` —— 已有完整防护
- `parse_*` 系列纯函数 —— 无浏览器交互
- `main()` CLI —— 单条调用，默认 delay 自动生效

## 测试策略

现有测试全为纯文本解析，不调用 CDP → 无需修改，预期全绿。

## 风险

- `_human_scroll` / `_human_mouse_jitter` 为私有函数（下划线前缀），不进 `__init__.py` 导出
- delay 参数默认值确保向后兼容，现有调用方无需修改
