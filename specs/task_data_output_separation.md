# Task: data/output 目录语义分离

## 现状问题

当前 `data/` 目录混合了两类文件：
- **静态依赖**：`city_codes.json`（城市码表，git 管理，程序只读）
- **运行时输出**：`query/*.json`（列表抓取结果）、`company/*.json`（详情抓取结果）

语义模糊 — `data/` 容易让 agent 误以为是输出目录，实际上其中的码表是静态数据。

数据库路径同样散落在用户主目录 `~/.boss-zhipin-scraper/jobs.db`，不属于项目生产输出。

## 目标

| 目录 | 语义 | git 管理 | 内容 |
|------|------|----------|------|
| `data/` | 静态依赖库 | 是 | `city_codes.json` 等只读数据文件 |
| `output/` | 运行时输出 | 否 | `query/*.json`、`company/*.json`、`jobs.db` |

## 路径对照

| 用途 | 改前路径 | 改后路径 |
|------|----------|----------|
| 数据库 | `~/.boss-zhipin-scraper/jobs.db` | `output/jobs.db` |
| 列表 JSON | `data/query/{query_hash}.json` | `output/query/{query_hash}.json` |
| 详情 JSON | `data/company/{brand_id}.json` | `output/company/{brand_id}.json` |

## 修改清单

### 1. `.gitignore`

```gitignore
# 改前
data/*.json
!data/city_codes.json

# 改后
output/
```

data/ 直接 git 管理，无需逐条排除。

### 2. `scripts/company_list/db.py` — 路径常量

```python
# 改前
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
QUERY_DIR = os.path.join(DATA_DIR, "query")
COMPANY_DIR = os.path.join(DATA_DIR, "company")
DEFAULT_DB_PATH = os.path.expanduser("~/.boss-zhipin-scraper/jobs.db")

# 改后
PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
OUTPUT_DIR = os.path.join(PACKAGE_DIR, "output")
QUERY_DIR = os.path.join(OUTPUT_DIR, "query")
COMPANY_DIR = os.path.join(OUTPUT_DIR, "company")
DEFAULT_DB_PATH = os.path.join(OUTPUT_DIR, "jobs.db")
```

导出名称 `QUERY_DIR` / `COMPANY_DIR` 不变，下游 import 无需改动。

### 3. `scripts/company_list/pipeline.py` — 删除冗余

删除第 16 行 `DATA_DIR = ...`（该变量在 pipeline.py 中未被直接使用，QUERY_DIR/COMPANY_DIR 从 db.py 导入）。

### 4. `scripts/boss_cdp_raw.py` — CLI 帮助文字

```python
# 改前 (第 2999 行)
help=f"自定义 SQLite 数据库路径 (默认 {os.path.expanduser('~/.boss-zhipin-scraper/jobs.db')})"

# 改后
from scripts.company_list.db import ... DEFAULT_DB_PATH
help=f"自定义 SQLite 数据库路径 (默认 {DEFAULT_DB_PATH})"
```

### 5. SKILL.md — 路径描述（本次不处理，留待后续 skill 拆分时一并更新）

## 不改的部分

- `data/city_codes.json` — 保持原位，git 管理
- Chrome profile 路径 `~/.boss-zhipin-scraper/chrome-profile` — 与本次改动无关
- `scripts/company_insight/__init__.py` — 不涉及路径

## 验证

- `python -m py_compile scripts/company_list/db.py`
- `python -m py_compile scripts/company_list/pipeline.py`
- `python -m py_compile scripts/boss_cdp_raw.py`
- `git check-ignore -v output/` → 应被忽略
- `git check-ignore -v data/city_codes.json` → 应不被忽略

## 版本号

版本号不变（2.3.0），纯路径重构。
