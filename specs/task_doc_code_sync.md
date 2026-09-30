# Task: 文档与代码一致性修正

> **当前实现契约（优先于本历史设计记录）**
>
> 本文件是文档同步的历史记录，不是现行代码变更计划。现行命令统一使用 `uv run python -m ...`，测试模块路径以仓库当前目录为准；历史段落中的旧命令、旧路径和版本数字只表示当时发现的问题。
>
> **历史记录标记**：下文的问题清单、目标和改动文件保留原方案背景；不应把其中的“修改前/修改后”内容当作当前实现声明。

## 现状问题

版本号同步 commit `bef6752` 后，文档与代码仍存在多处不一致：

### 🔴 严重不一致

| 问题 | 文档描述 | 实际代码 |
|------|----------|----------|
| README.en.md 版本号 | badge 显示 `2.3.0` | `pyproject.toml` / `SKILL.md` / `boss_cdp_raw.py` 均为 `2.4.0` |
| README 文件结构 | `company_list/` 仅列 `__init__.py`，注释"向后兼容" | 有完整的 `db.py` + `pipeline.py`（SQLite DAL + 管道编排） |
| README 文件结构 | `tests/company_list/test_chrome_setup.py` | 实际文件在 `tests/chrome_setup/test_chrome_setup.py` |
| README 文件结构 | 缺失 `scripts/company_insight/` | 目录存在，`__init__.py` 已建 |
| README 文件结构 | 缺失 `tests/company_list/test_db.py` | 文件存在，22 个单测 |
| README 安装方式 1/2 | 复制/下载命令缺少 `db.py` 和 `pipeline.py` | 不安装这两个文件则管道功能不可用 |
| CHANGELOG 测试路径 | `tests/company_list/test_chrome_setup.py` | 实际已迁移到 `tests/chrome_setup/` |

### 根因

`bef6752` 只修正了 AGENTS.md 和 README 文件结构的主干部分，未全面检查 `README.en.md` 版本号、安装命令列表、`CHANGELOG.md` 路径引用。属于首次同步的半成品遗漏。

## 目标

消除全部文档与代码的不一致，确保用户阅读任何一份文档都能得到准确的文件路径、版本号和安装步骤。

## 改动文件清单

### 1. `README.md`（中文）

**文件结构**：
```
修改前:
│   └── company_list/     # 列表抓取子包（向后兼容）
│       └── __init__.py
└── tests/
    ├── company_detail/   # 公司详情测试
    └── company_list/     # 列表抓取测试（原 test_chrome_setup.py）
        └── test_chrome_setup.py

修改后:
│   ├── company_list/     # SQLite 数据访问层 + 分阶段管道编排
│   │   ├── __init__.py
│   │   ├── db.py
│   │   └── pipeline.py
│   └── company_insight/  # 企查查洞察子包（预留）
└── tests/
    ├── chrome_setup/     # 城市码表防回归测试
    │   └── test_chrome_setup.py
    ├── company_detail/   # 公司详情测试
    └── company_list/     # JobDatabase 单元测试
        └── test_db.py
```

**安装方式 1（克隆）**：补 `company_list` 目录创建 + `__init__.py` / `db.py` / `pipeline.py` 复制

**安装方式 2（curl）**：补 `__init__.py` / `db.py` / `pipeline.py` 下载

**验证安装**：补 `__init__.py` / `db.py` / `pipeline.py` 检查行

### 2. `README.en.md`（英文）

**版本号**：
```
修改前: ![Version](https://img.shields.io/badge/version-2.3.0-orange.svg)
修改后: ![Version](https://img.shields.io/badge/version-2.4.0-orange.svg)
```

**文件结构**：同中文 README 修正（英文注释）

**安装方式 1/2**：同中文 README 补 db.py/pipeline.py（英文验证命令）

### 3. `CHANGELOG.md`

```
修改前: - 测试目录重组：... `tests/company_list/test_chrome_setup.py`
修改后: - 测试目录重组：... `tests/chrome_setup/test_chrome_setup.py`
```

### 不改的部分

- `AGENTS.md` — 上次同步已修正，本次无新问题
- `SKILL.md` — 子模块索引正确
- `scripts/` 代码 — 不改代码逻辑
- `tests/` — 不改测试

## 验证

- 文档审查：逐条对照上述清单，确认每个路径/命令/版本号与实际文件系统一致
- 测试全量通过：`tests.chrome_setup` + `tests.company_detail` + `tests.company_list`

## 风险

- 仅文档变更，零代码逻辑风险
- 安装命令列表纯文本追加，不影响已有命令
