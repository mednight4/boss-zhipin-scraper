---
name: boss-zhipin-scraper
description: "Scrape BOSS直聘 (job listing site) via Chrome CDP. Searches jobs by keyword/city/filters, fetches JD details, outputs structured JSON/CSV with plaintext salary, and can summarize scraped results into a job-market prompt. Use when user wants to search/analyze jobs on BOSS直聘 or zhipin.com."
version: 2.3.0
author: eatmoreduck
license: MIT
platforms: [macos, linux]
metadata:
  hermes:
    tags: [scraper, jobs, career, cdp, chrome, zhipin, boss直聘]
---

# BOSS直聘职位抓取工具 v2.3

通过 Chrome CDP 协议抓取 BOSS直聘 (zhipin.com) 职位数据，输出结构化 JSON/CSV（含明文薪资），并可对已抓取结果生成聚合摘要和求职材料优化提示词。

## 前置条件

- Chrome 浏览器已安装
- Python 3.10+
- 用户已登录 zhipin.com（或愿意手动登录）

## 脚本位置

- `scripts/boss_cdp_raw.py`：抓取主脚本
- `scripts/job_summary.py`：抓取后摘要和提示词脚本
- `scripts/company_detail/extractor.py`：公司详情提取模块

运行前先确定脚本绝对路径（详见 [skill/install.md](skill/install.md)）。

## 依赖安装

```bash
uv add websocket-client requests beautifulsoup4
```

## 自动化流程

当用户要求搜索/抓取 BOSS直聘 职位时，按以下顺序执行：

### 1. 检查环境

```bash
python3 "$SCRIPT_PATH" --check --cdp-port 9222
```

- 全部通过 → 跳到第 3 步
- CDP 不通 → 继续第 2 步
- 未登录 → 告诉用户登录后重试

### 2. 启动专用浏览器 CDP（仅 CDP 不通时）

```bash
python3 "$SCRIPT_PATH" --setup-chrome --cdp-port 9222
```

### 3. 运行抓取

```bash
# 基础搜索
python3 "$SCRIPT_PATH" --keyword "关键词" --city 上海 --pages 3

# 带详情 + 分析报告
python3 "$SCRIPT_PATH" --keyword "关键词" --city 上海 --pages 3 --detail --max-details 8 --analysis

# 抓取后摘要
python3 "$SUMMARY_PATH" --top 15
```

## Pipeline（管道查询）

当用户提出查询需求时，**不要直接跑管道**，先按渐进式询问流程确认需求：

1. **展示筛选条件** — 先展示常见筛选字段（薪资/经验/规模/学历），询问用户需要哪些过滤
2. **确认搜索意图** — 过滤条件确认后，再确认关键词/城市，不清楚就让用户去 web 选好后贴链接
3. **选择深度** — 让用户选：仅列表 / 列表+详情 / 列表+MCP / 全部，并说明时间代价
4. **检查 MCP 可用性** — 含 MCP 选项时先确认企查查 MCP 是否可用

详细询问流程、深度选项、筛选字段 → [skill/pipeline.md](skill/pipeline.md)

```bash
# 用户确认选项后，给 URL 执行
python "$SCRIPT_PATH" --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent"
```

`--url` 是最简入口：一条 URL 等价于 keyword + city + 所有筛选条件。

详情与 MCP 无耦合，可任意组合。

## 常见问题

1. **--check CDP 不通** → 运行 `--setup-chrome`
2. **--check 未登录** → 在专用 Chrome 中访问 zhipin.com 登录，或重新运行 `--setup-chrome`
3. **薪资空白** → 通常是未登录、登录态失效；先重新登录，不要优先做字体解密

## 子模块索引

| 何时读 | 文件 |
|--------|------|
| Pipeline 状态机、决策流程、SQL 查询、文件路径 | [skill/pipeline.md](skill/pipeline.md) |
| 完整参数速查、筛选条件、输出格式、工作原理 | [skill/reference.md](skill/reference.md) |
| 脚本路径查找、curl/clone 安装 skill | [skill/install.md](skill/install.md) |

## 注意事项

- 仅用于个人求职研究
- 单次最多 10 页（300 条），防封号
- 翻页间隔 12-22 秒随机延迟
- BOSS直聘可能更新 API 路径，失效时需更新脚本中 `API_JOB_LIST_PATH` 常量
