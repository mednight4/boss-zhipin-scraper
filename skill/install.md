# 安装说明

## 脚本位置

本 skill 的脚本在 skill 目录下：

- `scripts/boss_cdp_raw.py`：抓取主脚本
- `scripts/job_summary.py`：抓取后摘要和提示词脚本
- `scripts/company_detail/extractor.py`：公司详情提取模块（导航 `/gongsi/{brand_id}.html` 解析结构化公司信息）
- `scripts/company_detail/__init__.py`：公司详情包初始化

**运行任何命令前，必须先确定脚本的绝对路径。**

## 查找脚本路径

用以下方式找到脚本（macOS 自带的 `readlink` 不支持 `-f`，用 Python 解析路径更通用）：

```bash
# 方法 1：已知 skill 安装目录（推荐，macOS/Linux 通用）
SKILL_DIR="$(python3 -c "import os,sys;print(os.path.dirname(os.path.realpath(sys.argv[1])))" "$0")"
SCRIPT_PATH="$SKILL_DIR/scripts/boss_cdp_raw.py"
SUMMARY_PATH="$SKILL_DIR/scripts/job_summary.py"

# 方法 2：搜索 hermes skills 目录
SCRIPT_PATH=$(find ~/.hermes/skills -name "boss_cdp_raw.py" -type f 2>/dev/null | head -1)
SUMMARY_PATH=$(find ~/.hermes/skills -name "job_summary.py" -type f 2>/dev/null | head -1)
```

如果找不到脚本，说明 skill 未正确安装，需要重新安装。

## 安装本 Skill

本 Skill 需手动安装到 Hermes skills 目录（`hermes skills install` 因网络问题可能失败）：

### 方法 1：curl 一键安装

```bash
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/SKILL.md \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/SKILL.md && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/boss_cdp_raw.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/boss_cdp_raw.py && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/job_summary.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/job_summary.py && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/company_detail/__init__.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/__init__.py && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/scripts/company_detail/extractor.py \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/extractor.py && \
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/data && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/data/city_codes.json \
  -o ~/.hermes/skills/data-science/boss-zhipin-scraper/data/city_codes.json
```

### 方法 2：克隆后手动复制

```bash
git clone https://github.com/eatmoreduck/boss-zhipin-scraper.git
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail
cp boss-zhipin-scraper/SKILL.md ~/.hermes/skills/data-science/boss-zhipin-scraper/
cp boss-zhipin-scraper/scripts/boss_cdp_raw.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/
cp boss-zhipin-scraper/scripts/job_summary.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/
cp boss-zhipin-scraper/scripts/company_detail/__init__.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/
cp boss-zhipin-scraper/scripts/company_detail/extractor.py ~/.hermes/skills/data-science/boss-zhipin-scraper/scripts/company_detail/
mkdir -p ~/.hermes/skills/data-science/boss-zhipin-scraper/data
cp boss-zhipin-scraper/data/city_codes.json ~/.hermes/skills/data-science/boss-zhipin-scraper/data/
```
