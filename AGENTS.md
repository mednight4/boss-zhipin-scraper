# AGENTS.md

给未来 Agent 的仓库级开发指引。开始修改代码前先读本文件；开始执行查询或抓取任务时读取 [`skill/agent_workflow.md`](skill/agent_workflow.md)。

## 这是什么

`boss-zhipin-scraper` 通过 Chrome DevTools Protocol（CDP）连接用户本人已经登录的 Chrome 或 Microsoft Edge，抓取 BOSS直聘公开职位和公司信息，用于个人求职分析，不用于大规模爬取。

## 文档职责

- `AGENTS.md`：开发约束、代码边界、测试、合规和提交流程。
- `SKILL.md`：Agent Skill 的最小启动协议和文档路由。
- `skill/agent_workflow.md`：抓取、恢复和管道状态检查流程。
- `skill/query_workflow.md`：已完成数据库的只读筛选流程。
- `README.md` / `README.en.md`：面向用户的安装、CLI、参数、产物和风险说明。
- `skill/install.md`：Skill 安装和文件分发。
- `skill/reference.md`：参数、输出格式和只读查询参考。
- `skill/pipeline.md`：当前 Pipeline 状态机、三表数据契约和恢复语义。
- `specs/`：功能设计和历史变更依据；若与当前实现冲突，以代码和“当前实现契约”说明为准。
- `docs/`：本地产物，不作为 Skill 分发后的唯一运行入口。

## 目录边界

```text
scripts/boss_cdp_raw.py       核心抓取、CDP、CLI 主入口
scripts/job_summary.py        抓取结果到求职分析摘要
scripts/company_detail/       BOSS 公司详情抓取和纯文本解析
scripts/company_list/db.py    SQLite 数据访问层及只读筛选数据方法
scripts/company_list/query.py 已完成数据的只读 CLI 查询入口
scripts/company_list/pipeline.py 分阶段管道和状态入口
scripts/company_insight/      爱企查洞察抓取
 data/city_codes.json         城市码表
 tests/                       全 mock 或纯解析单元测试
```

核心逻辑优先放在现有模块，不要随手新建脚本。`data/city_codes.json` 是数据文件；公司详情、列表管道和洞察子包是已有的明确模块边界。

## 当前数据契约

```text
company_list.encrypt_brand_id
    = company_detail.brand_id
    = company_insight.brand_id

company_detail.credit_code
    → 爱企查搜索输入

Aiqicha company_id / pageid
    → 爱企查页面导航标识，不是项目表连接键
```

当前列表阶段没有把 `credit_code` 写入 `company_list`。真实执行顺序是：

```text
list → company_list → detail → company_detail.credit_code → insight → company_insight
```

因此不能在文档或代码注释中声称列表导入后 detail 和 insight 已经具备相同输入、可以直接并行。结果表可以通过 `brand_id` 最终回连列表表，但结果连接关系不等于抓取输入已经准备完成。

## 环境和命令

项目要求 Python >= 3.10，使用项目的 `uv` 环境和 `uv.lock`。统一使用模块入口：

```powershell
uv run python -m scripts.boss_cdp_raw --check --cdp-port 9222
uv run python -m scripts.company_list.pipeline --step status --db-path output/jobs.db
```

当前机器优先使用 Edge：

```powershell
uv run python -m scripts.boss_cdp_raw --setup-edge --cdp-port 9222
```

长任务使用 `-u`。不要把 `--check` 失败解释成“没有职位”，先按检查工具输出区分依赖、CDP、登录和风控状态。

## 测试命令

```powershell
uv run python -m unittest tests.chrome_setup.test_chrome_setup
uv run python -m unittest tests.company_detail.test_extractor
uv run python -m unittest tests.company_list.test_db
uv run python -m unittest tests.company_list.test_pipeline
uv run python -m unittest tests.company_insight.test_scraper
```

语法检查：

```powershell
uv run python -m py_compile scripts/boss_cdp_raw.py scripts/company_list/db.py scripts/company_list/pipeline.py scripts/company_detail/extractor.py scripts/company_insight/scraper.py
```

改动列表抓取、登录探测或详情链路时，合并前还必须在真实 Edge 中验证：

```text
--check → --smoke-test → --pages 2 --no-detail
```

一次性验证脚本放系统临时目录，不进入仓库。

## 改代码硬规则

1. 版本号在 `scripts/boss_cdp_raw.py`、`pyproject.toml`、`SKILL.md`、`README.md`、`README.en.md` 和 `uv.lock` 中保持一致。
2. 禁止 bare `except:`，捕获具体异常类型。
3. 用户可见行为变更更新中英文 README；有意义变更更新 `CHANGELOG.md`。
4. 新功能或非平凡修复先在 `specs/` 建立规范，保持一个 PR 只做一件事。
5. 禁止通过代理轮换、指纹伪造、验证码识别等方式绕过风控。
6. 验证码或风控页命中后，程序退出码为 `2`，交用户人工处理，不自动重试绕过。
7. 禁止直接写 SQLite；所有 JSON 入库使用 `JobDatabase.import_*_from_json()` 和现有状态更新方法。

## 数据和抓取边界

- 列表页通过 CDP Network 域被动捕获页面自身搜索响应，不注入额外搜索请求。
- BOSS 公司详情页通过 `encrypt_brand_id` 对应的公司链接抓取。
- 详情页 `business_info` 提供统一社会信用代码，写入 `company_detail.credit_code`。
- 爱企查通过 `credit_code` 搜索，再在页面内部使用其 `company_id/pageid` 导航；项目数据库用 `brand_id` 连接结果。
- `has_detail` 和 `has_insight` 是列表表上的状态字段，必须通过状态入口和数据库访问方法判断，不用文件数或单条日志替代。

## 提交流程

默认分支为 `master`。非平凡改动先开 Issue，再从 `master` 建立 `fix/...` 或 `feat/...` 分支。提交使用 Conventional Commits，如 `fix:`、`feat:`、`docs:`、`refactor:`、`test:`。

审查或拉分支前先 `git fetch origin`，不要未经用户明确允许自主推送远程仓库。
