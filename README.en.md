# BOSS Zhipin Scraper · Job Crawler v2.4 (Chrome/Edge CDP / Plaintext Salary)

> 🌐 中文文档：[README.md](./README.md)

![Python](https://img.shields.io/badge/python-3.10+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux%20%7C%20Windows-lightgrey.svg)
![Version](https://img.shields.io/badge/version-2.5.0-orange.svg)

A lightweight **BOSS Zhipin scraper / crawler** (a.k.a. spider) for job listings on [zhipin.com](https://www.zhipin.com). Instead of driving a heavy Selenium/Playwright browser, it connects to your **already-logged-in Chrome or Microsoft Edge** via the Chrome DevTools Protocol (CDP), reuses the real session, and calls the in-page search API directly — bypassing the front-end font-based anti-scraping so you get the **plaintext salary** in every record. Output goes to JSON / CSV, plus an aggregated salary/skill analysis and a copy-paste prompt for polishing your job-application materials. Also ships as a Hermes Agent Skill.

> 📌 **In one sentence**: no Selenium/Playwright — connect to your logged-in Chrome over CDP, hit the search API with the real session, get JSON/CSV with plaintext salaries, plus salary-distribution, skill-frequency stats and a résumé-optimization prompt.

---

## ⚠️ Disclaimer

This project is for **learning and technical research purposes only**. It is intended to explore Chrome DevTools Protocol, front-end anti-scraping mechanisms, and data-collection techniques. Do **not** use it for any purpose that violates the [BOSS Zhipin Terms of Service](https://www.zhipin.com/about/protocol.html) or applicable laws and regulations, including commercial resale, malicious scraping, or any activity that imposes undue load on the target site. Users are solely responsible for the consequences of using this project; the author is not liable for any misuse.

---

## 🚀 30-Second Quick Start

```powershell
# 1. Install dependencies
uv sync

# 2. Launch an isolated Microsoft Edge and log in
uv run python -m scripts.boss_cdp_raw --setup-edge --cdp-port 9222

# 3. Check dependencies, CDP, and BOSS login state
uv run python -m scripts.boss_cdp_raw --check --cdp-port 9222

# 4. Scrape and analyze
uv run python -u -m scripts.boss_cdp_raw --keyword "AI Agent" --city 上海 --pages 3 --analysis --cdp-port 9222

# 5. Generate an aggregated summary and prompt
uv run python -m scripts.job_summary --top 15
```

You can also pass a BOSS search URL. URL mode uses the database selected by `--db-path` and runs the full list, detail, and Aiqicha insight pipeline by default. To scrape only the list, skip both detail and insight explicitly:

```powershell
uv run python -u -m scripts.boss_cdp_raw --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent" --pages 3 --db-path output/jobs.db --cdp-port 9222
uv run python -u -m scripts.boss_cdp_raw --url "https://www.zhipin.com/web/geek/jobs?city=101020100&query=AI%20Agent" --pages 3 --no-detail --no-insight --db-path output/jobs.db --cdp-port 9222
```

List supported cities with:

```powershell
uv run python -m scripts.boss_cdp_raw --list-cities 上海
```

## ✨ Features

- Plaintext salary (API mode, bypasses font-based obfuscation)
- Boss activity status as a separate field (`boss_active_status`): list maps `bossOnline`→"在线"; detail can provide finer labels like "刚刚活跃"
- Cross-run new-job flag (`is_new`): every job carries a boolean marking whether it is new to this run (also shown as 🆕 in the terminal); the baseline defaults to the most recent prior result with the same keyword and city whose filename date is before today; multiple runs on the same day fold into one round; use `--diff-base` to override
- Dual JSON / CSV output
- Detail-page JD scraping + skill analysis
- Company detail extraction: navigates BOSS company pages via CDP, parses structured company info (basic info, hot jobs, 15 business-registration fields, products, work hours & benefits, etc.)
- Aggregated summary + copy-paste prompt after scraping
- Incremental writes (no data loss on crash)
- One-shot environment check + persistent isolated Chrome/Chromium CDP profile
- Multi-dimension filters (scale, funding, salary, experience, degree, industry)
- macOS + Linux + Windows support; macOS automatically detects Google Chrome or Chromium; Windows is verified by unit tests and basic CLI checks (GBK console crash fixed) and supports Chrome or Microsoft Edge CDP; real scraping flows still welcome feedback

<details>
<summary>🔍 Why not a Selenium / Playwright crawler?</summary>

- Selenium/Playwright spins up a full instrumented browser — it's heavy, has an obvious fingerprint, and is easily flagged by BOSS Zhipin's risk-control / CAPTCHA.
- This tool connects to your own already-logged-in Chrome (via CDP), reusing a real fingerprint and session, and calls the same legitimate search API the page uses. The `salaryDesc` it returns is already plaintext — no need to parse font-obfuscated DOM salaries.
- The result is more stable than traditional DOM-scraping crawlers and harder to flag as automated traffic.

</details>

## Installation

### Option 1: Clone then install locally (recommended)

Because `hermes skills install` may not reach GitHub directly in some environments, clone the repo first and install locally:

```bash
# 1. Clone the repo
git clone https://github.com/eatmoreduck/boss-zhipin-scraper.git
cd boss-zhipin-scraper

# 2. Copy into the Hermes skills directory
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

### Option 2: One-line curl install

No need to clone the whole repo — download just the files you need:

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
mkdir -p "$SKILL_DIR/data" && \
curl -sL https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/data/city_codes.json \
  -o "$SKILL_DIR/data/city_codes.json"
```

### Option 3: `hermes skills install` (requires direct GitHub access)

```bash
hermes skills install https://raw.githubusercontent.com/eatmoreduck/boss-zhipin-scraper/master/SKILL.md --category data-science
```

> Note: this depends on the hermes process being able to reach GitHub directly. If you hit a timeout or connection failure, use Option 1 or 2.

### Option 4: One-line install via skills.sh (Claude Code and other Agent Skills-compatible agents)

```bash
npx skills add eatmoreduck/boss-zhipin-scraper
```

The skill is listed on [skills.sh](https://skills.sh). Any agent that supports the Agent Skills format (Claude Code, Codex, Gemini CLI, Cursor, etc.) can install it with this one command — SKILL.md, the scripts, and the city code table ship with the skill. Pick the target agent when the CLI asks.

### Option 5: ClawHub install (OpenClaw / clawhub CLI)

The skill is published on [ClawHub](https://clawhub.ai), the skill registry of the OpenClaw ecosystem. OpenClaw users can install it with one command:

```bash
npx clawhub@latest install @eatmoreduck/boss-zhipin-scraper
```

### Verify the installation

```bash
# Check that the files exist
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

After installing, just say in a Hermes conversation: "Search BOSS Zhipin for AI Agent jobs in Shanghai."

## Use as a CLI tool

You don't have to install it as a Skill — use it as a plain CLI:

```bash
# 1. Clone + install deps
git clone https://github.com/eatmoreduck/boss-zhipin-scraper.git
cd boss-zhipin-scraper
pip install -r requirements.txt

# 2. Start Chrome CDP (or use --setup-edge)
uv run python -m scripts.boss_cdp_raw --setup-chrome
# macOS automatically selects an installed Google Chrome or /Applications/Chromium.app
# First run won't copy your main Chrome session; log in to zhipin.com in the dedicated BOSS browser that pops up
# setup waits for login to finish and confirms the API returns plaintext salaries

# 3. Check the environment
uv run python -m scripts.boss_cdp_raw --check

# Optional: real browser/API smoke test (writes no result files)
uv run python -m scripts.boss_cdp_raw --smoke-test

# 4. Scrape
uv run python -m scripts.boss_cdp_raw --keyword "AI Agent" --city 上海 --pages 3 --format csv --analysis

# 5. Summary + prompt after scraping
uv run python -m scripts.job_summary --top 15
```

## Parameters

| Parameter | Description |
|-----------|-------------|
| `--keyword` | Search keyword (default "AI Agent") |
| `--city` | City (Chinese name or 9-digit code, default Shanghai). **Supports cities nationwide** (300+, incl. tier-3/4/5); city codes auto-sync from BOSS at runtime. See [`data/city_codes.json`](data/city_codes.json), or run `--list-cities`. An unrecognized city name now exits with an error instead of silently producing zero results |
| `--list-cities [keyword]` | Print the supported city list, optional keyword filter, e.g. `--list-cities 江` |
| `--pages` | Number of pages (max 10, overridable via `BOSS_MAX_PAGES` env var) |
| `--format` | json / csv; csv also exports list and detail CSVs |
| `--detail` | Scrape detail-page JD (on by default) |
| `--no-detail` | Do not scrape detail pages |
| `--analysis` | Analysis report |
| `--merge FILE` | Merge existing data (deduped by job_id) |
| `--diff-base FILE` | Explicit baseline file for `is_new` (defaults to the most recent prior result with the same keyword and city whose filename date is before today; with no baseline, all jobs are treated as new) |
| `--allow-dom-fallback` | Allow DOM extraction fallback when the API has no data; off by default, salaries may be unreliable |
| `--check` | Environment check (CDP + deps + login state) |
| `--smoke-test` | Run one real Chrome/CDP BOSS search API smoke test, writes no result files |
| `--setup-chrome` | One-shot launch of Chrome CDP (persistent isolated profile) |
| `--setup-edge` | One-shot launch of Microsoft Edge CDP (persistent isolated profile) |
| `--browser` | Select `chrome` or `edge` for `--setup-chrome` (defaults to `chrome`); `--setup-edge` always launches Edge — an explicit `--browser chrome` yields to `--setup-edge` with a notice |
| `--copy-login-state` | Manually import the main browser's Local State + cookie-related files into the isolated profile (main Chrome for `--setup-chrome`, main Edge for `--setup-edge`; never copied by default, on first run, or on repeated runs) |
| `--reset-chrome-profile` | Rebuild the dedicated BOSS Chrome profile; clears the login state inside this dedicated browser |
| `--no-wait-login` | With `--setup-chrome`, do not wait for login to finish |
| `--login-timeout` | Seconds to wait for login under `--setup-chrome` (default 300) |
| `--stop-chrome` | Close the dedicated BOSS CDP Chrome (matched precisely by the isolated profile; never touches your main Chrome) |
| `--stop-edge` | Close the dedicated browser CDP process (shares the isolated profile with `--stop-chrome`) |
| `--close-chrome` | Auto-close the dedicated Chrome after a scrape finishes normally (off by default; not triggered on errors, so the login state is kept) |
| `--output` | List output path (default `~/.boss-zhipin-scraper/job-result/`) |
| `--detail-output` | Detail output path (default `~/.boss-zhipin-scraper/job-result/`) |
| `--cdp-port` | CDP port (default 9222) |
| `--scale/--salary/--experience/--degree` | Filters |

## Post-Scrape Summary & Prompt

`scripts/job_summary.py` only reads the already-scraped `boss_jobs_*.json` and `boss_details_*.json`, does simple aggregation, and produces a copy-paste prompt. It never reads your local résumé file, pulls in no PDF dependency, and never scores a person against a job.

```bash
# Read the newest boss_jobs_*.json under the default result dir and auto-match the same-timestamp or newest detail file
uv run python -m scripts.job_summary

# Specify list and detail files
uv run python -m scripts.job_summary \
  --input ~/.boss-zhipin-scraper/job-result/boss_jobs_20260625_1200.json \
  --details ~/.boss-zhipin-scraper/job-result/boss_details_20260625_1200.json \
  --top 15

# Only emit the prompt
uv run python -m scripts.job_summary --prompt-only
```

After installing the package you can also use the entry command:

```bash
uv run boss-summary --top 15
```

The summary covers: salary ranges, experience requirements, degree requirements, regional distribution, top companies, skill tags, frequent JD terms. The prompt asks the model to use these stats to fill in résumé keywords, suggest project-story rewrite directions, and produce an interview-prep checklist — while explicitly instructing it not to fabricate experience.

## File Structure

```
boss-zhipin-scraper/
├── SKILL.md              # Agent bootstrap protocol
├── AGENTS.md             # Repository development rules
├── README.md             # Chinese user documentation
├── README.en.md          # English user documentation
├── skill/
│   ├── agent_workflow.md  # Agent checks and execution states
│   ├── install.md         # Installation and distribution
│   ├── reference.md       # Parameters and output reference
│   └── pipeline.md        # Pipeline and database contract
├── CHANGELOG.md
├── LICENSE
├── pyproject.toml
├── .env.example
├── data/
│   └── city_codes.json
├── scripts/
│   ├── boss_cdp_raw.py
│   ├── job_summary.py
│   ├── company_detail/
│   ├── company_list/
│   └── company_insight/
└── tests/

## Company Detail Extraction

`scripts/company_detail/extractor.py` provides standalone company information extraction. It navigates to a BOSS company page (`/gongsi/{brand_id}.html`) via CDP, then parses the page text into structured data:

```bash
# CLI usage
uv run python -m scripts.company_detail.extractor <company_url>

# Example
uv run python -m scripts.company_detail.extractor "https://www.zhipin.com/gongsi/abc123.html"
```

This standalone command only scrapes and saves JSON; it does not write `company_detail` or update `company_list.has_detail`. Use the pipeline `--step detail` entry point when the result must be imported and marked complete.

Extracted fields include: basic info (job count, BOSS count, company name, funding stage, scale, industry), hot job list (salary/title/experience/degree/location/status), company description, website, products, business registration info (15 fields including legal representative, registered capital, address, etc.), work hours & benefits, recruiters, executives.

Programmatic usage:

```python
from scripts.company_detail.extractor import scrape_company_detail, parse_basic_info, parse_hot_jobs

# Full scrape (requires live Chrome CDP)
company = scrape_company_detail("https://www.zhipin.com/gongsi/abc123.html")

# Pure text parsing (no Chrome needed)
basic = parse_basic_info(page_text)
jobs = parse_hot_jobs(page_text)
```

## Pipeline CLI and Status Inspection

The pipeline follows the actual data dependency:

```text
list → company_list → BOSS company detail → company_detail.credit_code → Aiqicha insight → company_insight
```

`credit_code` is the unified social credit code used as the Aiqicha search input. It is not the BOSS `brand_id` and not the Aiqicha internal `company_id/pageid`.

The project tables use this connection key:

```text
company_list.encrypt_brand_id = company_detail.brand_id
company_list.encrypt_brand_id = company_insight.brand_id
```

The full pipeline runs list → detail → insight. `--step all` accepts `--keyword` and `--city`, or an existing list JSON via `--list-json`; it validates input before scraping. URL and database modes share the same pipeline and database path:

```powershell
uv run python -u -m scripts.company_list.pipeline --step all --keyword "AI Agent" --city 101020100 --pages 3 --db-path output/jobs.db
uv run python -u -m scripts.boss_cdp_raw --db --step all --keyword "AI Agent" --city 101020100 --pages 3 --db-path output/jobs.db
```

Insight runs by default in a full pipeline. Use `--no-insight` to skip it; skipped stages remain pending in the database and are not reported as complete.

View the current status:

```powershell
uv run python -m scripts.company_list.pipeline --step status --db-path output/jobs.db
```

Scrape BOSS company details:

```powershell
uv run python -u -m scripts.company_list.pipeline --step detail --port 9222 --db-path output/jobs.db
```

After the detail stage produces `company_detail.credit_code`, scrape Aiqicha insights:

```powershell
uv run python -u -m scripts.company_list.pipeline --step insight --port 9222 --insight-delay 15 --db-path output/jobs.db
```

Look up one company:

```powershell
uv run python -u -m scripts.company_insight.scraper 91310104MA1FR5RY3N --port 9222 --delay 15
```

`--step status` prints six sections answering which companies were scraped, whether data exists, when it was imported, and what remains:

Filter completed database results by listing the available batches first, then confirm and select a `query_hash`:

```powershell
uv run python -m scripts.company_list.query --db-path output/jobs.db --list-batches --format json
uv run python -m scripts.company_list.query --db-path output/jobs.db --query-hash QUERY_HASH --employee-min 50 --employee-max 100 --format json
```

The query entry opens the database read-only and does not scrape or change pipeline state. `company_insight.employee_count` is Aiqicha's publicly listed insured-person count, stored as a nullable integer after migration. It is distinct from BOSS company scale. See [`skill/query_workflow.md`](skill/query_workflow.md) for query semantics and interpretation.


| Section | Contents |
|---------|----------|
| `[1] Query batches` | Search batches, keyword/city/job count/earliest insert time |
| `[2] Overall progress` | Job count, unique companies, done/pending detail and insight counts |
| `[3] Pending details` | Companies with `has_detail=0` or no matching `company_detail` row |
| `[4] Pending insights` | Companies whose details are complete but insights are not; runnable entries need a `credit_code`, and missing inputs are reported separately |
| `[5] Insight JSON reconciliation` | Canonical / orphan / legacy-named / unparsable / duplicate `credit_code` files |
| `[6] Recently imported insights` | The latest five insight imports |

Insight JSON is written to `output/insight/aqc_{credit_code}.json`. The insight stage needs the `credit_code` produced by company details. A JSON file alone does not mean a stage is complete: each detail/insight result must exist by `brand_id` and its corresponding `company_list.has_detail=1` / `has_insight=1` flag must be set. The standalone detail extractor only saves JSON. The single-company insight CLI tries to import an existing JSON before scraping and exits with code `1` if a saved JSON cannot be imported; pass `--db-path` to select the database.

The detailed Agent routing and checks are documented in [`skill/agent_workflow.md`](skill/agent_workflow.md).

### When a CAPTCHA / risk-control page appears

Both BOSS and Aiqicha may redirect the page to a CAPTCHA. The program detects this and **aborts the whole run**, exiting with code `2` and printing the URL a human needs to open:

```
🛑 BOSS 触发验证码/安全校验，已中止本轮抓取（Java @ 上海）：URL 命中安全校验特征「_security_check」: ...
   请人工在 Chrome 中打开 ... 完成验证后重跑，程序不会自动绕过。
   已中止本轮；人工完成验证后重跑同一命令即可续做。
```

Everything completed so far is already in the database, so after you clear the challenge in the browser, re-running the same command resumes automatically. The program never attempts fingerprint spoofing, proxy rotation, or CAPTCHA solving (see the compliance rules in `CONTRIBUTING.md`).

## How It Works

This is a Chrome-CDP-based BOSS Zhipin crawler. Core flow:

1. Connect to an already-open Chrome via the Chrome DevTools Protocol (CDP)
2. Navigate to the real search page and **passively capture the page's own search-API responses** via the CDP `Network` domain (no injected requests, avoiding BOSS risk-control flags on injected XHRs)
3. Pagination scrolls the page to trigger its own infinite-scroll loading and keeps listening; the API returns plaintext `salaryDesc`, bypassing the front-end font obfuscation
4. The list API preserves `securityId` / `lid` context, carried into the detail page
5. Each page is written to disk immediately, deduped by `job_id`

DOM extraction is not used for the list by default, since DOM salaries may be hit by font-based obfuscation. Only when `--allow-dom-fallback` is explicitly passed will it fall back to DOM when the API returns no data.

For detail pages, the scraper only extracts a section containing the job-description heading. Full-page `body` text is diagnostic input for detecting login walls and navigation shells and is never written directly as a JD. If the page contains the login-to-view-full-content marker, the crawl fails explicitly and stops before truncated text, recruiter metadata, company sections, or recommended jobs can be saved as a complete JD.

`--input ... --analysis --no-detail` first loads `--detail-output`, then the `boss_details_*.json` with the same timestamp in the same dir as the input list, and finally the newest detail file under `~/.boss-zhipin-scraper/job-result`.

## Browser Profile Security Policy

`--setup-chrome` uses a persistent isolated profile by default — it neither symlinks nor copies your main Chrome data. First launch and subsequent launches only create or reuse this dedicated profile:

- `~/.boss-zhipin-scraper/chrome-profile`

Without an explicit `--output` or `--detail-output`, scraping results are saved under:

- `~/.boss-zhipin-scraper/job-result`

On first use you must log in to BOSS Zhipin manually inside this dedicated browser. `--setup-chrome` and `--setup-edge` wait for login to finish and confirm that the API returns plaintext `salaryDesc`. The session is stored inside the dedicated profile and survives reboots; re-running either setup command does not wipe it and does not affect your main Chrome, Edge, Gmail, GitHub, or other accounts.

Login probing injects no requests into the page: while `--setup-chrome` waits for login, it rotates across keyword/city targets by navigating real search pages and passively captures the page's own search responses, backing off from 3 seconds to at most 15 seconds. Those page-issued requests count toward the same 500-request global budget. A regular scrape no longer sends a separate fixed-keyword probe — login/risk-control checks are done with the first real search response. Logged-out sessions, empty probe samples, API restrictions, and malformed responses are reported separately. A confirmed restriction such as `code: 31` or `code: 37` ("您的环境存在异常" / abnormal environment) stops probing immediately instead of prompting for another login or continuing frequent retries. Unknown risk-control codes are also recognized as restrictions via message keywords (abnormal environment, too-frequent access, security check, etc.), so an authenticated session that is merely rate-limited is no longer misreported as a login failure.

The interactive login page opened by `--setup-chrome` is the only temporary page intentionally brought to the foreground. Temporary tabs used by environment checks, list/detail scraping, and the smoke test run in the background so automation does not repeatedly steal focus. “Background” here only means the tab is not activated; the dedicated Chrome still runs with a visible UI and can be opened manually for inspection.

If you really need to import the BOSS session from your main Chrome, run explicitly:

```bash
uv run python -m scripts.boss_cdp_raw --setup-chrome --copy-login-state
```

`--copy-login-state` overwrites the corresponding cookie-related files inside the isolated profile on every run; do not pass this for daily launches. It only copies `Local State` and `Default/Cookies*`, `Default/Network/Cookies*`-style cookie database files — not password stores, history, extensions, or a full profile.

On macOS, the import source matches the browser selected automatically: Google Chrome uses `~/Library/Application Support/Google/Chrome`, while Chromium uses `~/Library/Application Support/Chromium`.

To wipe the dedicated browser's login state:

```bash
uv run python -m scripts.boss_cdp_raw --setup-chrome --reset-chrome-profile
```

### Tearing down when you're done

After a scrape/analysis finishes, the dedicated Chrome is **not** closed automatically (the login state is kept by default so you can run the next scrape right away). When you're sure you no longer need it, tear it down manually:

```bash
uv run python -m scripts.boss_cdp_raw --stop-chrome
```

`--stop-chrome`/`--stop-edge` only close Chrome or Edge process(es) that belong to the scraper's isolated profile (`--user-data-dir`). They **never** kill by port or process name, so they cannot accidentally take down your main Chrome, Edge, Gmail, GitHub, or other signed-in sessions.

If you'd rather have a particular scrape close the dedicated Chrome once it finishes normally, add `--close-chrome`:

```bash
uv run python -m scripts.boss_cdp_raw --keyword "AI Agent" --city 上海 --pages 3 --close-chrome
```

`--close-chrome` is off by default, and it only fires on the **success path** of a completed scrape — login failures, crashes, and other early exits leave the Chrome running so the login state is preserved.

## 📌 TODO

- [ ] Strengthen the detail-page `Referer` and request fingerprinting to further reduce risk-control triggers

## License

MIT

## Friends

- [LINUX DO](https://linux.do/) — A sincere, friendly, and vibrant tech community. This project endorses and recommends it.

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=eatmoreduck/boss-zhipin-scraper&type=date&legend=top-left&sealed_token=linAWksW9v7s0YEw83L89xbRzD4QWaJWxKrQHvkJBmx9xwMH8PseUKUQC9QAcRYaBFK1jBA_Mod4Vs8qH9A47spODANKwiVWieL3CxxQ3f9ZLqHYRwzTiA)](https://www.star-history.com/?type=date&repos=eatmoreduck%2Fboss-zhipin-scraper)
