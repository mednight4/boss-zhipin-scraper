# 安装说明

## 1. 仓库运行方式

在项目根目录使用 uv：

```powershell
uv sync
uv run python -m scripts.boss_cdp_raw --help
uv run python -m scripts.company_list.pipeline --help
```

当前 Windows 环境优先使用 Edge：

```powershell
uv run python -m scripts.boss_cdp_raw --setup-edge --cdp-port 9222
```

## 2. Skill 文件职责

安装后至少需要保留：

```text
SKILL.md                         Agent 最小启动协议
skill/agent_workflow.md         Agent 检查工具和执行状态协议
skill/install.md                 安装说明
skill/reference.md               参数和输出参考
skill/pipeline.md                Pipeline 和数据库契约
scripts/boss_cdp_raw.py          核心抓取入口
scripts/job_summary.py            摘要入口
scripts/company_detail/           BOSS 公司详情模块
scripts/company_list/             SQLite 数据访问和管道模块
scripts/company_insight/          爱企查洞察模块
data/city_codes.json              城市码表
```

`skill/agent_workflow.md` 是 Agent 执行查询任务所需的关键参考，不能只安装 `SKILL.md` 而遗漏它。

## 3. 本地复制安装

从仓库复制到目标 Skill 目录时，完整复制以下内容：

```text
SKILL.md
skill/
scripts/boss_cdp_raw.py
scripts/job_summary.py
scripts/company_detail/
scripts/company_list/
scripts/company_insight/
data/city_codes.json
```

在 macOS/Linux 上可以使用：

```bash
TARGET="$HOME/.hermes/skills/data-science/boss-zhipin-scraper"
mkdir -p "$TARGET"
cp SKILL.md "$TARGET/"
cp -R skill "$TARGET/"
mkdir -p "$TARGET/scripts" "$TARGET/data"
cp scripts/boss_cdp_raw.py scripts/job_summary.py "$TARGET/scripts/"
cp -R scripts/company_detail scripts/company_list scripts/company_insight "$TARGET/scripts/"
cp data/city_codes.json "$TARGET/data/"
```

Windows 环境请使用 PowerShell 等价复制命令，并确保 `skill/agent_workflow.md`、`scripts/company_list/` 和 `scripts/company_insight/` 一并复制。

## 4. 分发安装

使用仓库安装或支持 Agent Skills 的工具时，必须让整个 Skill 目录一起分发，而不是只下载一个 `SKILL.md`：

```powershell
npx skills add eatmoreduck/boss-zhipin-scraper
```

如果使用 Hermes 或其他手动安装方式，验证以下文件存在：

```text
SKILL.md
skill/agent_workflow.md
skill/reference.md
skill/pipeline.md
scripts/boss_cdp_raw.py
scripts/company_list/db.py
scripts/company_list/pipeline.py
scripts/company_insight/scraper.py
data/city_codes.json
```

## 5. 安装后验证

```powershell
uv run python -m scripts.boss_cdp_raw --version
uv run python -m scripts.boss_cdp_raw --help
uv run python -m scripts.company_list.pipeline --help
uv run python -c "import scripts.company_list.db, scripts.company_list.pipeline, scripts.company_insight.scraper; print('SKILL_FILES_OK')"
```

验证失败时先检查文件是否完整复制，再执行 `uv sync`。不要新建临时检查脚本。

## 6. 浏览器和登录

启动 Edge 后：

```powershell
uv run python -m scripts.boss_cdp_raw --setup-edge --cdp-port 9222 --no-wait-login
uv run python -m scripts.boss_cdp_raw --check --cdp-port 9222
```

用户需要在隔离的 Edge profile 中人工登录 BOSS直聘。程序不会自动绕过验证码或风控。
