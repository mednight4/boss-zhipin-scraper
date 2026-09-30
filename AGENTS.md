# AGENTS.md

指引给未来的 ZCode agent。先读这份，再动代码。

## 这是什么

`boss-zhipin-scraper` —— 通过 Chrome CDP（远程调试端口）连接**用户本人已登录的 Chrome**，抓取 BOSS直聘的公开职位数据（列表 + 详情），并可生成求职分析摘要。仅用于个人求职分析，非大规模爬虫（见 `CONTRIBUTING.md` 的合规一节）。

## 目录结构

```
scripts/boss_cdp_raw.py   # 核心：抓取 + CLI 主入口（长单文件，行数以实际为准）
scripts/job_summary.py    # 抓取结果 → Markdown 求职分析摘要
scripts/company_detail/   # 公司详情提取模块（详见下方架构关键点）
scripts/company_list/     # 列表抓取子包：SQLite 数据访问层 + 分阶段管道编排
scripts/company_insight/  # 企查查洞察子包（CDP 自爬虫，复用 boss_cdp_raw.py 的 CDPSession 导航爱企查详情页）
data/city_codes.json      # 全量城市码表（300+ 城市，外置；见下）
tests/chrome_setup/test_chrome_setup.py    # unittest，全 mock，不依赖真实 Chrome/网络
tests/company_detail/test_extractor.py     # 公司详情提取测试
tests/company_list/test_db.py             # JobDatabase 单元测试
pyproject.toml            # hatchling 打包；入口 boss-scraper / boss-summary
requirements.txt          # requests + websocket-client + beautifulsoup4
SKILL.md / README(.en).md / CHANGELOG.md / CONTRIBUTING.md
specs/                    # 任务规范文档 (task_*.md)，每个新特性/修复对应一份 spec
docs/                     # 本地产物 (.gitignore)，bug 报告、spike 脚本等
```

**重要边界：核心逻辑都放 `scripts/boss_cdp_raw.py`，不要随手新建文件**（见 `CONTRIBUTING.md`「单文件原则」）。`docs/` 被 `.gitignore` 忽略，是本地产物，不要提交。**例外**：`data/city_codes.json` 是城市码表数据（非逻辑代码），外置便于用户查看支持哪些城市；改它要同步跑 `tests.chrome_setup.test_chrome_setup` 的城市码表防回归测试。**第二例外**：`scripts/company_detail/extractor.py` 是公司详情提取的独立模块（导航公司页面 + 纯文本行解析，复用 `boss_cdp_raw.py` 的 `CDPSession` + `create_page_session`），与列表/详情抓取路径分离；如需扩展公司字段只改此文件。**第三例外**：`scripts/company_list/db.py` + `pipeline.py` 是 SQLite 数据访问层和分阶段管道编排（列表→DB→详情/洞察并行→DB），与抓取主链路解耦；如需改查询存储或管道状态机只改这两个文件。detail 和洞察在 step2 之后可并行执行（`company_list` 已含 `encrypt_brand_id` 和 `credit_code`），agent 开两个子线程分别跑 `--step detail` 和 `--step insight`。**第四例外**：`scripts/company_insight/` 是企查查洞察子包，通过 CDP 复用 `boss_cdp_raw.py` 的 `CDPSession` + `create_page_session` 导航爱企查详情页，抓取工商结构化信息，与列表/详情抓取路径分离；如需改洞察字段只改此文件。

## 环境与命令

- Python **>=3.10**，依赖为 `requests` + `websocket-client` + `beautifulsoup4`。用项目里的 `.venv`（`source .venv/bin/activate`），别用 pyenv 全局解释器（会缺依赖报错）。
- 包管理用 `uv`（仓库有 `uv.lock`），也可 `pip install -r requirements.txt`。
- 跑测试：`python3 -m unittest tests.chrome_setup.test_chrome_setup`（无需 Chrome / 联网，全 mock）。改了 `job_summary` 再加跑 `tests.test_job_summary`。改了 `company_detail` 需跑 `tests.company_detail.test_extractor`。改了 `company_list` 需跑 `tests.company_list.test_db`。
- 语法自检：`python3 -m py_compile scripts/boss_cdp_raw.py`。
- 实跑抓取需要先启动带调试端口的 Chrome：`python3 scripts/boss_cdp_raw.py --setup-chrome`（开 `127.0.0.1:9222`，默认端口见 `DEFAULT_CDP_PORT`），登录后在**另一个终端**跑抓取命令。Chrome 关了端口就没了。

## 改代码时的硬规则

1. **版本号四处一致**：`scripts/boss_cdp_raw.py` 的 `__version__`（第 22 行附近）、`pyproject.toml`、`SKILL.md`、`README.md` 必须同步，否则 `VersionConsistencyTests` 会挂。改版本号时四处一起改，并跑 `uv lock` 同步 `uv.lock`——CI 用 `uv sync --locked` 安装，lockfile 版本落后会直接失败；本地 `.venv` 不走 lockfile，单测发现不了（#89 踩过）。
2. **异常处理**：禁止 bare `except:`，必须捕获具体类型（`requests.ConnectionError`、`json.JSONDecodeError` 等），和现有代码保持一致。
3. **改了用户可见行为 → 更新 `README.md`；有意义变更 → `CHANGELOG.md` 顶部加一条。**
4. **README 双语同步**：`README.md`（中文）和 `README.en.md`（英文）必须保持一致，改了其中一个就要同步另一个。
5. **commit message 用 Conventional Commits**（`feat:` / `fix:` / `docs:` / `optimize:` / `refactor:` 等，见 `CONTRIBUTING.md`）。
6. **动抓取链路必须真机验证**：凡改列表抓取、登录探测、详情链路的 PR，合并前要在真机过一遍 `--check` → `--smoke` → `--pages 2 --no-detail`（Chrome 需已启动且已登录）。全 mock 单测覆盖不到浏览器的焦点、定时器节流、SPA 行为和风控——焦点仿真 bug 曾 96 个单测全绿而真机翻页静默失败。一次性验证脚本（spike）放 `/tmp`，不进仓库。
7. **合规红线**：只做被动捕获（Network 域旁听页面自身请求）和请求节奏控制。**禁止**主动伪装类手段：指纹伪造、验证码绕过、代理池轮换。遇到验证页时程序已主动检测并中止整轮（BOSS 侧 `SecurityCheckError`，爱企查侧 `InsightBlockedError`，均以退出码 2 结束并打印需人工打开的 URL），交用户人工处理，不自动绕过。

## 架构关键点（容易踩坑）

- `scripts/boss_cdp_raw.py` 是一个**长单文件**，包含：`CDPSession` 类（WebSocket 连 CDP，含事件缓冲 `events` / `drain_events`）、`NetworkJoblistCapture`（列表被动捕获）、`scrape_list`（列表抓取）、`scrape_details`（详情抓取）、`main`（argparse）。城市码表外置到 `data/city_codes.json`，`resolve_city` 查询链为「本地静态码表 → 运行时拉 BOSS 接口 → 原样兜底」。
- **列表页 vs 详情页路径完全不同**：列表页导航真实搜索页，通过 CDP `Network` 域**被动捕获页面自身发出的 joblist 响应**（不注入任何请求，背景见 `NetworkJoblistCapture` 头部注释）；翻页靠滚动触发页面自身的无限滚动加载。详情页通过新开 tab → `Page.navigate` → 注入 JS 提取。改其中一条路径时，另一条不受影响。
- **is_new 跨轮对比**（#88）：`scrape_list` 输出的每条岗位带 `is_new` 布尔（终端列表同步 🆕 标记），纯本地后处理、零额外请求，不碰抓取链路。基准自动选取（`find_diff_base`）：同 keyword+city、文件名时间戳早于本轮的最近一份 JSON 结果——时间从 `boss_jobs_YYYYMMDD_HHMM.json` 文件名解析（`parse_result_file_time`），不用 mtime（文件复制会改 mtime）；同一天多轮抓取折叠为一轮，不和几分钟前的自己 diff 出翻页抖动噪音（#50 的「搜索结果重复」由此缓解）。无历史基准时全体 `is_new=true` 并终端明示；`--diff-base` 显式指定优先。`load_base_ids` 读基准文件已见 job_id 集合做比对。
- **BOSS 页面行为事实**（2026-08 实测，写代码前先知道）：搜索页无翻页控件、纯无限滚动，URL 带 `&page=N` 直跳无效（SPA 始终请求第 1 页）；页面自身请求是 POST + form body（URL 只有时间戳）；每页 15 条，`zpData.hasMore` 判断是否最后一页；反复自动化导航可能触发 `_security_check` 验证页——已由 `detect_security_check_page()` + `SecurityCheckError` 主动检测并中止整轮（列表/详情/公司详情/`--step detail` 四条链路都接入），不要绕过、不要重试、不要换 IP。
- **CDP target 焦点/可见性不变量**：统一通过 `create_page_session` 创建页面；自动化 target 默认后台打开并注册 visibility override + **焦点仿真**（`Emulation.setFocusEmulationEnabled`），两者都不可省——后台页真实的 `hidden/hasFocus=false` 状态会让无限滚动加载静默失效（实测 JS override 单独不生效，焦点仿真才解决），同时避免抢用户前台焦点（issue #18/#29）。只有需要用户操作的 `wait_for_login` 显式传 `background=False`。不要绕过 helper 直接新增 `Target.createTarget`。
- 同一个 Chrome 实例的默认 browser context 下，新开 target **本就共享 cookies**，不要被「新 tab 丢 cookie」的直觉误导。
- `require_runtime_dependencies("requests", "websocket")` 在多个入口前置检查依赖，缺了会提示安装。
- `scripts/company_detail/extractor.py` 是公司详情提取的独立模块：复用 `boss_cdp_raw.py` 的 `CDPSession` + `create_page_session` 导航 `/gongsi/{brand_id}.html`，拿到 `document.body.innerText` 后通过纯文本行解析（`parse_basic_info` / `parse_hot_jobs` / `parse_description` / `parse_products` / `parse_business_info` / `parse_work_benefits` / `parse_recruiters` / `parse_executives`）提取结构化字段。有 `scrape_company_detail(url, cdp_port, delay)` 高级 API（delay 参数控制公司间随机间隔，默认 15s±5s）、`main()` CLI 入口，以及多个可独立使用的 `parse_*` 纯文本解析函数（无需 Chrome）。
- `scripts/company_list/db.py` 是 SQLite 三表桥接数据访问层（company_list / company_detail / company_insight），提供 `JobDatabase` 类、`build_query_url`、`compute_query_hash` 等。`pipeline.py` 是分阶段管道编排（step1_scrape_list → step2_import_list → step3_scrape_details → step4_import_details → step5_scrape_insights），含 `PipelineState` 状态机和 `run_full_pipeline()` 一键入口。状态流转：
  ```
  IDLE → LIST_JSON_SAVED → LIST_DB_IMPORTED → DETAIL_DONE → COMPLETE
                                         ↘ INSIGHT_DONE ↗
  ```
  **detail 和洞察可并行**：step2 完成后 `company_list` 已含 `encrypt_brand_id`（详情联立键）和 `credit_code`（洞察联立键），两条路径无依赖。agent 可开两个子线程分别执行 `--step detail` 和 `--step insight`，各自独立写各自的表。`DETAIL_DONE` 和 `INSIGHT_DONE` 都到达后状态归一化为 `COMPLETE`。`scripts/company_insight/scraper.py` 通过 CDP 自爬虫抓取爱企查工商信息，入口为 `scrape_aqc_by_credit_code(credit_code, cdp_port)`，参数 `credit_code` 来自 `company_list` 中 BOSS 返回的统一社会信用代码，CLI 入口为 `python -m scripts.company_insight.scraper <credit_code> [--port 9222]`。step5 从 DB 扫描 `has_insight=0` 的公司 → 读取 `credit_code` → 逐家调用洞察脚本 → 导入 `company_insight` 表。**独立查询**：用户可直接用 `python -m scripts.company_insight.scraper <credit_code>` 对任意统一社会信用代码做单条爱企查查询，无需先跑完整管道。

  > **警告**：不要编写自定义脚本直接操作数据库。所有数据导入必须通过 `db.py` 的 `import_*_from_json()` 方法，否则会导致字段缺失或数据不一致。运行管道请使用 `python3 -m scripts.company_list.pipeline --step <list|detail|insight|all>`。

## 提交流程

默认分支 `master`，fork/分支工作流：从 `master` 拉新分支（`fix/...`、`feat/...`）→ 改代码补测试 → push → PR。一个 PR 只做一件事。**审 PR / 拉分支前先 `git fetch origin`**——本地 master 落后时 diff 范围会失真（曾把已合并的 #43 误判为 PR 夹带改动）。

**合并惯例**：squash merge，标题带 `(#PR号)` 后缀（如 `fix: ...(#55)`）；PR 描述含 `Fixes #N` / `Closes #N` 时合并会自动关闭对应 issue，只提 `#N`（普通引用）则不会。

**先开 issue 再动手**：非平凡的改动（bug 修复、新功能、文档补充）按仓库 `CONTRIBUTING.md` 的规范，先在 Issues 开一条说明「改什么 / 为什么 / 怎么改」，讨论清楚后再起新分支提交。issue 正文要结构化（问题 / 现状 / 根因 / 建议 / 影响），并标注改动范围（哪些逻辑受影响、哪些不动）。

**issue 分诊打标**：处理/关闭 issue 时按 `CONTRIBUTING.md` 的「Issue 标签约定」打标签；`wontfix` / `invalid` 关闭前必须留说明理由的回复。
