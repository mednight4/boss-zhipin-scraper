# BOSS直聘爬虫 · 职位抓取工具 v2.5（Chrome/Edge CDP / 明文薪资）

> 🌐 English documentation: [README.en.md](./README.en.md)

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)
![Version](https://img.shields.io/badge/version-2.5.0-orange.svg)

一个轻量的 **BOSS直聘爬虫（spider / crawler / scraper）**：通过 Chrome DevTools Protocol 连接本地已登录的 Chrome 或 Microsoft Edge，复用真实登录态调用 zhipin.com 搜索 API，绕过前端字体反爬，输出含**明文薪资**的职位数据（JSON / CSV），并生成薪资分布、技能词频和求职材料优化提示词。同时作为 Hermes Agent Skill 提供。

> 📌 **一句话介绍**：不用 Selenium/Playwright，直接通过 Chrome DevTools Protocol 连接本地已登录的 Chrome，复用真实登录态调搜索 API，输出含明文薪资的 JSON/CSV，并生成薪资分布、技能词频和求职材料优化提示词。

![cover](cover.png)

---

## ⚠️ 免责声明

本项目仅供学习和技术研究参考，旨在探讨 Chrome DevTools Protocol、前端反爬机制与数据采集技术。请勿用于任何违反 [BOSS直聘用户协议](https://www.zhipin.com/about/protocol.html) 或相关法律法规的用途，不得用于商业转售、恶意爬取或对目标网站造成负担的行为。使用本项目所产生的一切后果由使用者自行承担，作者不对任何滥用行为负责。

---

## 🚀 30 秒快速开始

```powershell
# 1. 安装依赖
uv sync

# 2. 启动隔离 Edge 并登录（只需一次，登录态持久保存）
uv run python -m scripts.boss_cdp_raw --setup-edge --cdp-port 9222

# 3. 检查环境
uv run python -m scripts.boss_cdp_raw --check --cdp-port 9222

# 4. 抓取职位
uv run python -u -m scripts.boss_cdp_raw --keyword "AI Agent" --city 上海 --pages 3 --analysis --cdp-port 9222

# 5. 抓取后生成聚合摘要 + 提示词
uv run python -m scripts.job_summary --top 15
```

也可以使用 BOSS 查询 URL。URL 模式默认用 `--db-path` 指定数据库并执行列表、详情、爱企查洞察完整管道；若只抓列表，可同时跳过详情和洞察：

```powershell
uv run python -u -m scripts.boss_cdp_raw --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent" --pages 3 --db-path output/jobs.db --cdp-port 9222
uv run python -u -m scripts.boss_cdp_raw --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent" --pages 3 --no-detail --no-insight --db-path output/jobs.db --cdp-port 9222
```

支持全国城市。查看支持的城市：

```powershell
uv run python -m scripts.boss_cdp_raw --list-cities 上海
```

## ✨ 特性

- 明文薪资（API 模式，绕过字体反爬）
- Boss 活跃状态独立字段（`boss_active_status`）：列表兼容 `bossOnline`→「在线」，详情可得到「刚刚活跃」等更细状态
- 跨轮新增标记（`is_new`）：每条岗位带布尔字段标识「是否为本次新增」（终端同步以 🆕 显示），基准自动取同关键词同城市、日期早于本轮的最近一份结果；同一天多轮抓取折叠为一轮，`--diff-base` 可显式指定
- JSON / CSV 双格式输出
- 详情页 JD 抓取 + 技能分析
- 公司详情提取：通过 CDP 导航 BOSS 公司页面，解析结构化公司信息（基本信息、热招职位、工商信息 15 字段、产品介绍、工作时间及福利等）
- 抓取后聚合摘要 + 可复制提示词
- 增量写入（异常退出不丢数据）
- 一键环境检查 + 持久隔离 Chrome/Chromium CDP profile
- 多维筛选（规模、融资、薪资、经验、学历、行业）
- macOS + Linux + Windows 支持；macOS 会自动探测 Google Chrome 或 Chromium；Windows 已通过单元测试与基础 CLI 验证（GBK 控制台崩溃已修复），并支持 Chrome 或 Microsoft Edge CDP；真实抓取链路仍欢迎反馈

<details>
<summary>🔍 为什么不选 Selenium / Playwright 类爬虫？</summary>

- Selenium/Playwright 会启动完整的受控浏览器，体积大、指纹明显，容易触发 BOSS 的风控和验证码。
- 本工具直接连接你已经登录的真实 Chrome（CDP），复用真实指纹和登录态，调用的也是页面内合法的搜索 API，返回的 `salaryDesc` 本就是明文——不需要解析被字体反爬加密的 DOM 薪资。
- 因此比传统 DOM 抓取类爬虫更稳定，也更难被识别为自动化流量。

</details>

## 安装

### 方式 1：克隆到本地再安装（推荐）

由于 `hermes skills install` 的网络请求在某些环境下可能无法直接访问 GitHub，推荐先克隆仓库再本地安装：

```bash
# 1. 克隆仓库
git clone https://github.com/eatmoreduck/boss-zhipin-scraper.git
cd boss-zhipin-scraper

# 2. 复制到 Hermes skills 目录
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_insight
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/skill
cp SKILL.md ~/.hermes/skills/data-science/boss-zhipin-scraper/
cp skill/*.md ~/.hermes/skills/data-science/boss-zhipin-scraper/skill/
cp scripts/boss_cdp_raw.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/
cp scripts/job_summary.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/
cp scripts/company_detail/__init__.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/
cp scripts/company_detail/extractor.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/
cp scripts/company_list/__init__.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list/
cp scripts/company_list/db.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list/
cp scripts/company_list/pipeline.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list/
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/data
cp data/city_codes.json ~/.hermes/skills/data-science/boss-zhipin-scraper/data/
```

### 方式 2：curl 一键安装

不需要克隆整个仓库，直接下载必要文件：

```bash
SKILL_DIR="$HOME/.hermes/skills/data-science/boss-zhipin-scraper"
mkdir -p "$SKILL_DIR/scripts/company_detail" "$SKILL_DIR/scripts/company_list" "$SKILL_DIR/scripts/company_insight" "$SKILL_DIR/skill" && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/SKILL.md -o "$SKILL_DIR/SKILL.md" && \
for file in agent_workflow.md install.md pipeline.md reference.md; do \
  curl -sL "https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/skill/$file" -o "$SKILL_DIR/skill/$file"; \
done && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/boss_cdp_raw.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/boss_cdp_raw.py && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/job_summary.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/job_summary.py && \
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/company_detail/__init__.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/__init__.py && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/company_detail/extractor.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/extractor.py && \
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/company_list/__init__.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list/__init__.py && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/company_list/db.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list/db.py && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/company_list/pipeline.py \
  -o "$SKILL_DIR/scripts/company_list/pipeline.py" && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/company_insight/__init__.py \
  -o "$SKILL_DIR/scripts/company_insight/__init__.py" && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/company_insight/scraper.py \
  -o "$SKILL_DIR/scripts/company_insight/scraper.py" && \
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/data && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/data/city_codes.json \
  -o "$SKILL_DIR/data/city_codes.json"
```

### 方式 3：hermes skills install（需网络直连 GitHub）

```bash
hermes skills install https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/SKILL.md --category data-science
```

> 注意：此方式依赖 hermes 进程能直接访问 GitHub，如果遇到超时或连接失败，请使用方式 1 或 2。

### 方式 4：skills.sh 一键安装（Claude Code 等 Agent Skills 兼容 agent）

```bash
npx skills add eatmoreduck/boss-zhipin-scraper
```

[skills.sh](https://skills.sh) 已收录本技能。任何支持 Agent Skills 格式的 agent（Claude Code、Codex、Gemini CLI、Cursor 等）都可以用这条命令安装，SKILL.md、脚本和城市码表随技能一起分发，按提示选择要安装到哪个 agent 即可。

### 方式 5：ClawHub 安装（OpenClaw / clawhub CLI）

本技能已上架 [ClawHub](https://clawhub.ai)（OpenClaw 生态的技能注册表），OpenClaw 用户可一条命令安装：

```bash
npx clawhub@latest install @eatmoreduck/boss-zhipin-scraper
```

### 验证安装

```bash
# 检查文件是否存在
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/SKILL.md
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/skill/agent_workflow.md
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/skill/pipeline.md
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/skill/reference.md
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/skill/install.md
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/boss_cdp_raw.py
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/job_summary.py
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/__init__.py
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/extractor.py
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list/__init__.py
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list/db.py
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_list/pipeline.py
ls ~/.hermes/skills/data-science/boss-zhipin-scraper/data/city_codes.json
```

安装后直接在 Hermes 对话中说"帮我搜一下 BOSS直聘 上上海的 AI Agent 岗位"。

## 作为命令行工具使用

不想装成 Skill 也可以直接当 CLI 用：

```bash
# 1. 克隆 + 安装依赖
git clone https://github.com/eatmoreduck/boss-zhipin-scraper.git
cd boss-zhipin-scraper
pip install -r requirements.txt

# 2. 启动 Chrome CDP（也可改用 --setup-edge）
uv run python -m scripts.boss_cdp_raw --setup-chrome
# macOS 会自动选择已安装的 Google Chrome 或 /Applications/Chromium.app
# 首次使用也不会复制主 Chrome 登录态；请在弹出的 BOSS 专用浏览器中登录 zhipin.com
# setup 会等待登录完成，并确认接口能返回明文薪资

# 3. 检查环境
uv run python -m scripts.boss_cdp_raw --check

# 可选：真实浏览器/API smoke test（不写结果文件）
uv run python -m scripts.boss_cdp_raw --smoke-test

# 4. 抓取
uv run python -m scripts.boss_cdp_raw --keyword "AI Agent" --city 上海 --pages 3 --format csv --analysis

# 5. 抓取后摘要和提示词
uv run python -m scripts.job_summary --top 15
```

## 参数

| 参数 | 说明 |
|------|------|
| `--keyword` | 搜索关键词（默认 "AI Agent"） |
| `--city` | 城市（中文或 9 位代码，默认上海）。**支持全国城市**（一二三四五线全覆盖，共 300+ 个），运行时自动从 BOSS 同步最新城市码；码表见 [`data/city_codes.json`](data/city_codes.json)，或用 `--list-cities` 查看。本地及在线码表均无法识别的城市名会报错退出，避免静默得到 0 条结果 |
| `--list-cities [关键词]` | 打印支持的城市列表，可选关键词过滤，如 `--list-cities 江` |
| `--pages` | 页数（上限可通过 `BOSS_MAX_PAGES` 环境变量覆盖，默认 10） |
| `--format` | json / csv；csv 会同时导出列表和详情 CSV |
| `--detail` | 抓取详情页 JD（默认开启） |
| `--no-detail` | 不抓取详情页 |
| `--analysis` | 分析报告 |
| `--merge FILE` | 合并已有数据（按 job_id 去重） |
| `--diff-base FILE` | 指定 `is_new` 对比基准文件（默认自动取同关键词同城市、文件名日期早于本轮的最近一份结果；无基准时全体视为新增） |
| `--allow-dom-fallback` | API 无数据时允许降级 DOM 提取；默认关闭，薪资可能不可信 |
| `--check` | 环境检查（CDP + 依赖 + 登录态） |
| `--smoke-test` | 用真实 Chrome/CDP 跑一次 BOSS 搜索 API smoke test，不写结果文件 |
| `--setup-chrome` | 一键启动 Chrome CDP（持久隔离 profile） |
| `--setup-edge` | 一键启动 Microsoft Edge CDP（持久隔离 profile） |
| `--browser` | 配合 `--setup-chrome` 选择 `chrome` 或 `edge`（默认 `chrome`）；`--setup-edge` 固定 Edge，显式传 `--browser chrome` 会以 `--setup-edge` 为准并提示 |
| `--copy-login-state` | 手动导入主浏览器（`--setup-chrome` 取主 Chrome、`--setup-edge` 取主 Edge）的 Local State + Cookie 相关文件到隔离 profile（默认、首次启动、重复启动都不复制） |
| `--reset-chrome-profile` | 重建 BOSS 专用 Chrome profile，会清除此专用浏览器内的登录态 |
| `--no-wait-login` | `--setup-chrome` 启动后不等待登录完成 |
| `--login-timeout` | `--setup-chrome` 等待登录完成的秒数（默认 300） |
| `--stop-chrome` | 关闭 BOSS 专用 CDP Chrome（按隔离 profile 精准匹配，不碰主 Chrome） |
| `--stop-edge` | 关闭 BOSS 专用浏览器 CDP（与 `--stop-chrome` 共用隔离 profile） |
| `--close-chrome` | 抓取正常结束后自动关闭专用 Chrome（默认不关；异常退出不触发，保留登录态） |
| `--output` | 列表输出路径（默认 `~/.boss-zhipin-scraper/job-result/`） |
| `--detail-output` | 详情输出路径（默认 `~/.boss-zhipin-scraper/job-result/`） |
| `--cdp-port` | CDP 端口（默认 9222） |
| `--scale/--salary/--experience/--degree` | 筛选条件 |

## 抓取后摘要与提示词

`scripts/job_summary.py` 只读取已抓取的 `boss_jobs_*.json` 和 `boss_details_*.json`，做简单聚合分析并生成一段可复制提示词。它不读取本地简历文件，不引入 PDF 依赖，也不给个人与岗位做分数判断。

```bash
# 读取默认结果目录下最新的 boss_jobs_*.json，并自动匹配同时间戳或最新详情文件
uv run python -m scripts.job_summary

# 指定列表和详情文件
uv run python -m scripts.job_summary \
  --input ~/.boss-zhipin-scraper/job-result/boss_jobs_20260625_1200.json \
  --details ~/.boss-zhipin-scraper/job-result/boss_details_20260625_1200.json \
  --top 15

# 只输出提示词
uv run python -m scripts.job_summary --prompt-only
```

打包安装后也可以使用入口命令：

```bash
uv run boss-summary --top 15
```

摘要会覆盖这些维度：薪资区间、经验要求、学历要求、地区分布、高频公司、技能标签、JD 高频词。提示词会要求模型基于这些统计去做简历关键词补齐、项目经历改写方向和面试准备清单，但明确要求不要虚构经历。

## 文件结构

```
boss-zhipin-scraper/
├── SKILL.md              # Agent 最小启动协议
├── AGENTS.md             # 仓库开发规则
├── README.md
├── README.en.md
├── skill/
│   ├── agent_workflow.md  # Agent 检查工具和状态工作流
│   ├── install.md         # 安装和分发
│   ├── reference.md       # 参数和输出参考
│   └── pipeline.md        # Pipeline 和数据库契约
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
├── .env.example          # 环境变量配置模板（BOSS_MAX_PAGES 等）
├── data/
│   └── city_codes.json   # 全量城市码表
├── scripts/
│   ├── boss_cdp_raw.py   # 抓取主脚本（列表 + 详情）
│   ├── job_summary.py    # 抓取后摘要 + 提示词
│   ├── company_detail/   # 公司详情提取模块
│   │   ├── __init__.py
│   │   └── extractor.py  # 公司页面解析（基本信息/热招职位/工商信息等）
│   ├── company_list/     # SQLite 数据访问层 + 分阶段管道编排
│   │   ├── __init__.py
│   │   ├── db.py
│   │   └── pipeline.py
│   └── company_insight/  # 企查查洞察子包
│       ├── __init__.py
│       └── scraper.py    # 爱企查工商信息抓取（CDP 自爬虫）
└── tests/
    ├── chrome_setup/     # 城市码表防回归 + 验证码检测测试
    │   ├── __init__.py
    │   └── test_chrome_setup.py
    ├── company_detail/   # 公司详情测试
    │   ├── __init__.py
    │   └── test_extractor.py
    ├── company_insight/  # 洞察抓取测试
    │   ├── __init__.py
    │   └── test_scraper.py
    └── company_list/     # JobDatabase + 管道状态测试
        ├── test_db.py
        └── test_pipeline.py
```

## 公司详情提取

`scripts/company_detail/extractor.py` 提供独立的公司信息提取能力，通过 CDP 导航到 BOSS 公司页面（`/gongsi/{brand_id}.html`），解析页面文本提取结构化数据：

```bash
# 命令行用法
uv run python -m scripts.company_detail.extractor <company_url>

# 示例
uv run python -m scripts.company_detail.extractor "https://www.zhipin.com/gongsi/abc123.html"
```

独立命令只抓取并保存 JSON，不会写入 `company_detail` 或更新 `company_list.has_detail`。需要闭环入库时使用上文的 `--step detail` 管道入口。

提取字段包括：基本信息（在招职位数、BOSS 数、公司名、融资阶段、规模、行业）、热招职位列表（含薪资/标题/经验/学历/地点/在线状态）、公司简介、官网链接、产品介绍、工商信息（企业名称、法定代表人、成立时间、注册资本、注册地址等 15 字段）、公司地址、工作时间及福利、招聘人员列表、高管介绍。

程序库调用：

```python
from scripts.company_detail.extractor import scrape_company_detail, parse_basic_info, parse_hot_jobs

# 完整抓取（需要真实 Chrome CDP）
company = scrape_company_detail("https://www.zhipin.com/gongsi/abc123.html")

# 纯文本解析（不需要 Chrome）
basic = parse_basic_info(page_text)
jobs = parse_hot_jobs(page_text)
```

## 管道 CLI 与状态查看

分阶段管道按真实数据依赖执行：

```text
列表 → company_list → BOSS 公司详情 → company_detail.credit_code → 爱企查洞察 → company_insight
```

`credit_code` 不是 BOSS `brand_id`，也不是爱企查内部 `company_id/pageid`。三张项目表最终使用以下连接键：

```text
company_list.encrypt_brand_id = company_detail.brand_id
company_list.encrypt_brand_id = company_insight.brand_id
```

完整管道也可以直接从关键字和城市执行，默认包含列表、详情和洞察。`--step all` 参数不足时会在抓取前报错；输入已有列表 JSON 时可用 `--list-json` 继续。

```powershell
uv run python -u -m scripts.company_list.pipeline --step all --keyword "AI Agent" --city 101020100 --pages 3 --db-path output/jobs.db
uv run python -u -m scripts.boss_cdp_raw --db --step all --keyword "AI Agent" --city 101020100 --pages 3 --db-path output/jobs.db
```

URL 与分步入口使用同一数据库：`--url` 模式通过 `--db-path` 指定 SQLite；完整模式默认执行洞察，显式跳过时使用 `--no-insight`。跳过阶段仍保留数据库待办，不会返回虚假的全部完成状态。

查看当前状态：

```powershell
uv run python -m scripts.company_list.pipeline --step status --db-path output/jobs.db
```

批量抓 BOSS 公司详情：

```powershell
uv run python -u -m scripts.company_list.pipeline --step detail --port 9222 --db-path output/jobs.db
```

详情阶段产生 `company_detail.credit_code` 后，批量抓爱企查洞察：

```powershell
uv run python -u -m scripts.company_list.pipeline --step insight --port 9222 --insight-delay 15 --db-path output/jobs.db
```

单条查某家公司的工商信息：

```powershell
uv run python -u -m scripts.company_insight.scraper 91310104MA1FR5RY3N --port 9222 --delay 15
```

筛选已完成数据库中的职位和参保人数时，先列出批次，再核对并选择 `query_hash`：

```powershell
uv run python -m scripts.company_list.query --db-path output/jobs.db --list-batches --format json
uv run python -m scripts.company_list.query --db-path output/jobs.db --query-hash QUERY_HASH --employee-min 50 --employee-max 100 --format json
```

查询入口使用只读连接，不触发抓取或修改管道状态。`company_insight.employee_count` 是爱企查公开的“参保人数”，迁移后以可空整数保存；它与 BOSS 企业规模不是同一指标。查询流程和结果解释见 [`skill/query_workflow.md`](skill/query_workflow.md)。

`--step status` 输出六个区块，回答「哪些公司查过了 / 有数据吗 / 什么时候查的 / 需要重新查吗」：
| 区块 | 内容 |
|------|------|
| `[1] 查询批次` | 有哪几批搜索，关键词/城市/职位数/最早入库时间 |
| `[2] 总体进度` | 职位数、唯一公司数、详情与洞察的已完成/待爬计数 |
| `[3] 待爬详情` | `has_detail=0` 或缺少 `company_detail` 行的 brand_id 清单 |
| `[4] 待爬洞察` | 详情状态已完成但洞察尚未闭环的公司；可执行项需有 `credit_code`，缺失项单独说明 |
| `[5] 洞察 JSON 对账` | 规范命名 / 孤儿 / 旧命名 / 无法解析 / 重复 `credit_code` |
| `[6] 最近入库的洞察` | 最近 5 家入库时间，用于判断数据新鲜度 |

洞察 JSON 统一落在 `output/insight/aqc_{credit_code}.json`。只有在详情产生 `credit_code` 后，洞察管道才有可执行输入。JSON 文件存在不代表完成：详情/洞察必须分别同时具备结果表中的 `brand_id` 行与列表表对应的 `has_detail=1` / `has_insight=1`。独立详情提取器只保存 JSON；单条洞察 CLI 若 JSON 未能入库会以退出码 `1` 返回，并可用 `--db-path` 指定数据库。已有单条洞察 JSON 会先尝试补导入，成功后不重复抓取。

Agent 的详细检查工具、状态路由和停止条件见 [`skill/agent_workflow.md`](skill/agent_workflow.md)。

### 遇到验证码 / 风控页时

BOSS 和爱企查都可能把页面重定向到验证码页。程序会主动检测并**中止整轮抓取**，以退出码 `2` 结束，同时打印需要人工打开的 URL：

```
🛑 BOSS 触发验证码/安全校验，已中止本轮抓取（Java @ 上海）：URL 命中安全校验特征「_security_check」: ...
   请人工在 Chrome 中打开 ... 完成验证后重跑，程序不会自动绕过。
   已中止本轮；人工完成验证后重跑同一命令即可续做。
```

已完成的进度都已入库，人工在浏览器里完成验证后重跑同一命令会自动续做。程序不会尝试指纹伪造、代理轮换或验证码识别（见 `CONTRIBUTING.md` 的合规红线）。

## 工作原理

这是一个基于 Chrome CDP 的 BOSS直聘爬虫，核心流程：

1. 通过 Chrome DevTools Protocol (CDP) 连接到已打开的 Chrome
2. 导航到真实搜索页，通过 CDP `Network` 域**被动捕获页面自身发出的搜索 API 响应**（不发任何注入请求，规避 BOSS 对注入 XHR 的风控识别）
3. 翻页通过滚动触发页面自身的无限滚动加载，继续旁听其请求；API 返回明文 `salaryDesc`，绕过前端字体反爬
4. 列表 API 保留 `securityId` / `lid` 等上下文，进入详情页时带上这些参数
5. 每页抓完立即写入文件，按 `job_id` 去重

默认不会使用 DOM 提取列表，因为 DOM 薪资可能受字体反爬影响。只有明确传 `--allow-dom-fallback` 时，API 无数据才会降级 DOM。

详情页只从包含“职位描述”的详情区提取 JD，整页 `body` 仅用于识别登录墙和导航页，不会直接写入结果。若页面出现“登录查看完整内容”，抓取会明确报错并停止，避免把截断正文、招聘者信息、公司介绍和推荐职位当成完整 JD 保存。

`--input ... --analysis --no-detail` 会优先加载 `--detail-output`，其次加载与输入列表同目录、同时间戳的 `boss_details_*.json`，最后查找 `~/.boss-zhipin-scraper/job-result` 下最新详情文件。

## 浏览器 profile 安全策略

`--setup-chrome` 默认使用持久隔离 profile，不软链接、不复制你的主 Chrome 数据。首次启动和后续重复启动都只是创建或复用这个专用 profile：

- `~/.boss-zhipin-scraper/chrome-profile`

未显式指定 `--output` 或 `--detail-output` 时，抓取结果默认保存到：

- `~/.boss-zhipin-scraper/job-result`

首次使用需要在这个专用浏览器中手动登录 BOSS直聘。`--setup-chrome` 和 `--setup-edge` 都会等待登录完成并确认接口能返回明文 `salaryDesc`；登录态保存在专用 profile 内，重启机器后仍然保留，也不会影响主 Chrome、Edge、Gmail、GitHub 等账号。

登录探测不向页面注入任何请求：`--setup-chrome` 等待登录时会在不同关键词/城市之间轮换导航真实搜索页，被动捕获页面自身发出的搜索响应，等待间隔从 3 秒逐步退避到最多 15 秒；这些页面请求同样计入单次 500 次的全局请求预算。正式抓取不再单独发送固定关键词的探测请求，登录/风控判定直接用第一次真实搜索的响应完成。未登录、探测样本为空、接口限制和响应异常会分别提示。遇到已确认的限制状态（例如 `code: 31`、`code: 37`「您的环境存在异常」）会立即停止探测，不会继续提示重复登录或密集重试；对未知风控码还会按 message 关键字（环境存在异常、访问频繁、安全校验等）兜底识别为限制状态，避免把「已登录但被风控」误判为登录失败。

`--setup-chrome` 的交互式登录页是唯一会主动置前的临时页面；环境检查、列表/详情抓取和 smoke test 创建的临时标签页都会在后台运行，避免自动流程反复抢占当前窗口。这里的“后台”仅表示不激活标签页，专用 Chrome 仍以有界面模式运行，必要时可以手动打开检查。

如确实需要从主 Chrome 手动导入 BOSS 登录态，可以显式运行：

```bash
uv run python -m scripts.boss_cdp_raw --setup-chrome --copy-login-state
```

`--copy-login-state` 每次运行都会覆盖隔离 profile 内对应的 Cookie 相关文件；日常启动不要加这个参数。它只复制 `Local State` 和 `Default/Cookies*`、`Default/Network/Cookies*` 这类 Cookie 数据库相关文件，不复制密码库、历史记录、扩展或完整 profile。

macOS 上的导入源会与自动选中的浏览器保持一致：Google Chrome 使用 `~/Library/Application Support/Google/Chrome`，Chromium 使用 `~/Library/Application Support/Chromium`。

需要清空专用浏览器登录态时使用：

```bash
uv run python -m scripts.boss_cdp_raw --setup-chrome --reset-chrome-profile
```

### 用完如何收尾

抓取/分析结束后，专用 Chrome 不会自动关闭（默认保留登录态，方便你接着跑下一条抓取）。确认不再使用时，可以手动收尾：

```bash
uv run python -m scripts.boss_cdp_raw --stop-chrome
```

`--stop-chrome`/`--stop-edge` 只关闭 scraper 隔离 profile（`--user-data-dir`）对应的 Chrome 或 Edge 进程，**绝不**按端口或进程名去 kill，因此不会误伤你正在用的主 Chrome、Edge、Gmail、GitHub 等账号。

如果你希望某次抓取正常结束后就顺手关掉 Chrome，可以加 `--close-chrome`：

```bash
uv run python -m scripts.boss_cdp_raw --keyword "AI Agent" --city 上海 --pages 3 --close-chrome
```

`--close-chrome` 默认不开启；且只在抓取走完的**成功路径**上触发，登录失败、异常退出等情况不会关闭 Chrome，登录态得以保留。

## 📌 TODO

- [ ] 详情页抓取补强 Referer 与请求指纹，进一步降低风控触发概率

## License

MIT

## 友情链接

- [LINUX DO](https://linux.do/) — 真诚、友善、充满活力的技术社区，本项目认可并推荐。

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=eatmoreduck/boss-zhipin-scraper&type=date&legend=top-left&sealed_token=linAWksW9v7s0YEw83L89xbRzD4QWaJWxKrQHvkJBmx9xwMH8PseUKUQC9QAcRYaBFK1jBA_Mod4Vs8qH9A47spODANKwiVWieL3CxxQ3f9ZLqHYRwzTiA)](https://www.star-history.com/?type=date&repos=eatmoreduck%2Fboss-zhipin-scraper)
