"""SQLite 数据访问层 — 三表桥接 (company_list / company_detail / company_insight)."""

import json
import os
import sqlite3
import hashlib
from datetime import datetime
from urllib.parse import urlencode

PACKAGE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
OUTPUT_DIR = os.path.join(PACKAGE_DIR, "output")
QUERY_DIR = os.path.join(OUTPUT_DIR, "query")
COMPANY_DIR = os.path.join(OUTPUT_DIR, "company")
DEFAULT_DB_PATH = os.path.join(OUTPUT_DIR, "jobs.db")

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS company_list (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id          TEXT NOT NULL UNIQUE,
    query_url       TEXT NOT NULL,
    query_hash      TEXT NOT NULL,
    keyword         TEXT,
    city            TEXT,
    city_code       TEXT,
    filters_json    TEXT,
    title           TEXT,
    salary          TEXT,
    salary_source   TEXT,
    location        TEXT,
    tags            TEXT,
    boss_name       TEXT,
    boss_title      TEXT,
    boss_active_status TEXT,
    company_scale   TEXT,
    company_stage   TEXT,
    company_industry TEXT,
    job_labels      TEXT,
    skills          TEXT,
    welfare         TEXT,
    encrypt_job_id  TEXT,
    encrypt_boss_id TEXT,
    encrypt_brand_id TEXT,
    job_link        TEXT,
    company_link    TEXT,
    is_new          INTEGER DEFAULT 1,
    has_detail      INTEGER DEFAULT 0,
    has_insight     INTEGER DEFAULT 0,
    create_time     TEXT NOT NULL,
    scraped_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_cl_query_hash ON company_list(query_hash);
CREATE INDEX IF NOT EXISTS idx_cl_brand_id ON company_list(encrypt_brand_id);
CREATE INDEX IF NOT EXISTS idx_cl_has_detail ON company_list(has_detail);
CREATE INDEX IF NOT EXISTS idx_cl_has_insight ON company_list(has_insight);

CREATE TABLE IF NOT EXISTS company_detail (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id        TEXT NOT NULL UNIQUE,
    company_list_id INTEGER,
    company_name    TEXT,
    job_count       INTEGER,
    boss_count      INTEGER,
    stage           TEXT,
    scale           TEXT,
    industry        TEXT,
    hot_jobs_json   TEXT,
    description     TEXT,
    website         TEXT,
    products_json   TEXT,
    business_info_json TEXT,
    address         TEXT,
    work_hours      TEXT,
    work_type       TEXT,
    benefits_json   TEXT,
    recruiters_json TEXT,
    executives_json TEXT,
    office_addresses_json TEXT,
    url             TEXT,
    json_path       TEXT,
    create_time     TEXT NOT NULL,
    scraped_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_cd_brand_id ON company_detail(brand_id);

CREATE TABLE IF NOT EXISTS company_insight (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id        TEXT NOT NULL UNIQUE,
    company_list_id INTEGER,
    company_name    TEXT,
    credit_code     TEXT,
    legal_person    TEXT,
    registered_capital TEXT,
    establish_date  TEXT,
    business_scope  TEXT,
    business_status TEXT,
    cap_json        TEXT,
    risk_json       TEXT,
    create_time     TEXT NOT NULL,
    scraped_at      TEXT
);
CREATE INDEX IF NOT EXISTS idx_ci_brand_id ON company_insight(brand_id);
CREATE INDEX IF NOT EXISTS idx_ci_credit_code ON company_insight(credit_code);
"""


def build_query_url(keyword, city_code, filters):
    """构造完整查询 URL，用于唯一标识一次搜索批次."""
    params = {"city": city_code, "query": keyword}
    key_order = ["experience", "degree", "industry", "scale", "salary", "stage"]
    for key in key_order:
        if key in filters:
            params[key] = filters[key]
    return f"https://www.zhipin.com/web/geek/jobs?{urlencode(params)}"


def compute_query_hash(query_url):
    """计算查询 URL 的 MD5 前 16 位，作为批次标识."""
    return hashlib.md5(query_url.encode("utf-8")).hexdigest()[:16]


class JobDatabase:
    """SQLite 三表桥接的数据访问层."""

    def __init__(self, db_path=None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.conn = None

    def connect(self):
        """建立连接（幂等）."""
        if self.conn is None:
            os.makedirs(os.path.dirname(self.db_path) or ".", exist_ok=True)
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self.conn.execute("PRAGMA journal_mode=WAL")
        return self

    def init_schema(self):
        """幂等建表."""
        self.connect()
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self):
        """关闭连接."""
        if self.conn is not None:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass
            self.conn = None

    def __enter__(self):
        self.connect()
        self.init_schema()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ── List 导入 ─────────────────────────────────────────────────

    def import_list_from_json(self, json_path):
        """读取列表 JSON → 写入 company_list.

        返回 (插入数, 跳过数).
        """
        self.connect()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        keyword = data.get("keyword", "")
        city = data.get("city", "")
        filters = data.get("filters", {})
        scraped_at = data.get("scraped_at", datetime.now().isoformat())
        jobs = data.get("jobs", [])

        city_code = ""
        for job in jobs:
            loc = job.get("location", "")
            if loc:
                city_code = loc.split("\u00b7")[0]
                break

        query_url = build_query_url(keyword, city_code, filters)
        query_hash = compute_query_hash(query_url)
        now = datetime.now().isoformat()

        inserted = 0
        skipped = 0
        cur = self.conn.cursor()
        for job in jobs:
            job_id = job.get("job_id", "")
            if not job_id:
                continue
            try:
                cur.execute(
                    """INSERT OR IGNORE INTO company_list (
                        job_id, query_url, query_hash, keyword, city, city_code,
                        filters_json, title, salary, salary_source, location, tags,
                        boss_name, boss_title, boss_active_status, company_scale,
                        company_stage, company_industry, job_labels, skills, welfare,
                        encrypt_job_id, encrypt_boss_id, encrypt_brand_id,
                        job_link, company_link, is_new, has_detail, has_insight,
                        create_time, scraped_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                              ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        job_id, query_url, query_hash, keyword, city, city_code,
                        json.dumps(filters, ensure_ascii=False),
                        job.get("title", ""), job.get("salary", ""),
                        job.get("salary_source", ""),
                        job.get("location", ""), job.get("tags", ""),
                        job.get("boss_name", ""), job.get("boss_title", ""),
                        job.get("boss_active_status", ""),
                        job.get("company_scale", ""),
                        job.get("company_stage", ""),
                        job.get("company_industry", ""),
                        job.get("job_labels", ""), job.get("skills", ""),
                        job.get("welfare", ""),
                        job.get("encrypt_job_id", ""),
                        job.get("encrypt_boss_id", ""),
                        job.get("encrypt_brand_id", ""),
                        job.get("job_link", ""), job.get("company_link", ""),
                        1 if job.get("is_new", True) else 0,
                        0, 0, now, scraped_at,
                    ),
                )
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
            except sqlite3.Error:
                skipped += 1
        self.conn.commit()
        return inserted, skipped

    # ── Detail 查询/导入 ──────────────────────────────────────────

    def get_pending_detail_brands(self):
        """查询 has_detail=0 的唯一 brand 列表（按 encrypt_brand_id 去重）."""
        self.connect()
        cur = self.conn.cursor()
        cur.execute(
            """SELECT MIN(id) as id, encrypt_brand_id, MIN(company_link) as company_link,
                      MIN(boss_name) as boss_name
               FROM company_list
               WHERE has_detail = 0 AND encrypt_brand_id != ''
               GROUP BY encrypt_brand_id
               ORDER BY MIN(id)"""
        )
        return [dict(r) for r in cur.fetchall()]

    def import_detail_from_json(self, json_path, brand_id):
        """读取公司详情 JSON → 写入 company_detail.

        如果 brand_id 已存在则更新.
        """
        self.connect()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        now = datetime.now().isoformat()
        business_info = data.get("business_info", {})
        company_name = business_info.get("企业名称", "") or data.get("company_name", "")
        stage = data.get("stage", "") or business_info.get("企业类型", "")
        scale = data.get("scale", "")
        industry = data.get("industry", "") or business_info.get("所属行业", "")

        cur = self.conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO company_detail (
                brand_id, company_list_id, company_name, job_count, boss_count,
                stage, scale, industry, hot_jobs_json, description, website,
                products_json, business_info_json, address, work_hours, work_type,
                benefits_json, recruiters_json, executives_json, office_addresses_json,
                url, json_path, create_time, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                brand_id,
                None,
                company_name,
                data.get("job_count", 0) or 0,
                data.get("boss_count", 0) or 0,
                stage,
                scale,
                industry,
                json.dumps(data.get("hot_jobs", {}), ensure_ascii=False),
                data.get("description", ""),
                data.get("website", ""),
                json.dumps(data.get("products", []), ensure_ascii=False),
                json.dumps(business_info, ensure_ascii=False),
                data.get("address", ""),
                data.get("work_hours", ""),
                data.get("work_type", ""),
                json.dumps(data.get("benefits", []), ensure_ascii=False),
                json.dumps(data.get("recruiters", []), ensure_ascii=False),
                json.dumps(data.get("executives", []), ensure_ascii=False),
                json.dumps(data.get("office_addresses", []), ensure_ascii=False),
                data.get("url", ""),
                json_path,
                now,
                data.get("scraped_at", now),
            ),
        )
        self.conn.commit()

    def mark_detail_done(self, brand_id):
        """更新关联的 company_list 行 has_detail=1."""
        self.connect()
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE company_list SET has_detail = 1 WHERE encrypt_brand_id = ?",
            (brand_id,),
        )
        self.conn.commit()

    # ── Insight 查询/导入（预留） ─────────────────────────────────

    def get_pending_insight_brands(self):
        """查询 has_insight=0 且 has_detail=1 的 brand 列表."""
        self.connect()
        cur = self.conn.cursor()
        cur.execute(
            """SELECT MIN(cl.id) as id, cl.encrypt_brand_id, MIN(cl.boss_name) as boss_name,
                      cd.business_info_json, cd.company_name
               FROM company_list cl
               JOIN company_detail cd ON cl.encrypt_brand_id = cd.brand_id
               WHERE cl.has_insight = 0 AND cl.has_detail = 1
               GROUP BY cl.encrypt_brand_id
               ORDER BY MIN(cl.id)"""
        )
        return [dict(r) for r in cur.fetchall()]

    def import_insight_from_json(self, json_path, brand_id):
        """读取企查查洞察 JSON → 写入 company_insight."""
        self.connect()
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        now = datetime.now().isoformat()
        cur = self.conn.cursor()
        cur.execute(
            """INSERT OR REPLACE INTO company_insight (
                brand_id, company_list_id, company_name, credit_code, legal_person,
                registered_capital, establish_date, business_scope, business_status,
                cap_json, risk_json, create_time, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                brand_id,
                None,
                data.get("company_name", ""),
                data.get("credit_code", ""),
                data.get("legal_person", ""),
                data.get("registered_capital", ""),
                data.get("establish_date", ""),
                data.get("business_scope", ""),
                data.get("business_status", ""),
                json.dumps(data.get("cap", {}), ensure_ascii=False),
                json.dumps(data.get("risk", []), ensure_ascii=False),
                now,
                data.get("scraped_at", now),
            ),
        )
        self.conn.commit()

    def mark_insight_done(self, brand_id):
        """更新关联的 company_list 行 has_insight=1."""
        self.connect()
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE company_list SET has_insight = 1 WHERE encrypt_brand_id = ?",
            (brand_id,),
        )
        self.conn.commit()

    # ── 统计 ──────────────────────────────────────────────────────

    def get_stats(self):
        """返回统计信息."""
        self.connect()
        cur = self.conn.cursor()

        cur.execute("SELECT COUNT(*) FROM company_list")
        total_jobs = cur.fetchone()[0]

        cur.execute("SELECT COUNT(DISTINCT encrypt_brand_id) FROM company_list WHERE encrypt_brand_id != ''")
        unique_companies = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM company_detail")
        done_detail = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM company_insight")
        done_insight = cur.fetchone()[0]

        cur.execute(
            """SELECT COUNT(DISTINCT encrypt_brand_id) FROM company_list
               WHERE has_detail = 0 AND encrypt_brand_id != ''"""
        )
        pending_detail = cur.fetchone()[0]

        cur.execute(
            """SELECT COUNT(DISTINCT cl.encrypt_brand_id) FROM company_list cl
               JOIN company_detail cd ON cl.encrypt_brand_id = cd.brand_id
               WHERE cl.has_insight = 0"""
        )
        pending_insight = cur.fetchone()[0]

        return {
            "total_jobs": total_jobs,
            "unique_companies": unique_companies,
            "done_detail": done_detail,
            "done_insight": done_insight,
            "pending_detail": pending_detail,
            "pending_insight": pending_insight,
        }

    # ── 查询批次元信息 ────────────────────────────────────────────

    def get_query_info(self, query_hash: str):
        """查询某批次的元信息。

        返回 dict 或 None。
        """
        self.connect()
        cur = self.conn.cursor()

        cur.execute(
            """SELECT COUNT(*) as job_count,
                      COUNT(DISTINCT encrypt_brand_id) as company_count,
                      MIN(create_time) as oldest_create_time
               FROM company_list WHERE query_hash = ?""",
            (query_hash,),
        )
        row = cur.fetchone()
        if row is None or row[0] == 0:
            return None

        cur.execute(
            "SELECT COUNT(*) FROM company_detail WHERE brand_id IN "
            "(SELECT DISTINCT encrypt_brand_id FROM company_list WHERE query_hash = ?)",
            (query_hash,),
        )
        detail_done = cur.fetchone()[0]

        cur.execute(
            """SELECT COUNT(DISTINCT encrypt_brand_id) FROM company_list
               WHERE query_hash = ? AND has_detail = 0 AND encrypt_brand_id != ''""",
            (query_hash,),
        )
        detail_pending = cur.fetchone()[0]

        return {
            "query_hash": query_hash,
            "job_count": row[0],
            "company_count": row[1],
            "oldest_create_time": row[2],
            "detail_done": detail_done,
            "detail_pending": detail_pending,
        }

    def get_all_query_hashes(self):
        """返回所有已有查询批次的摘要列表。"""
        self.connect()
        cur = self.conn.cursor()
        cur.execute(
            """SELECT query_hash, MIN(keyword) as keyword, MIN(city) as city,
                      COUNT(*) as job_count, MIN(create_time) as oldest_create_time
               FROM company_list
               GROUP BY query_hash
               ORDER BY MIN(create_time) DESC"""
        )
        return [dict(r) for r in cur.fetchall()]

    def delete_query(self, query_hash: str):
        """删除某 query_hash 的全部 company_list 行（用于过期刷新）。

        返回删除的行数。关联的 company_detail 行保留（按 brand_id 独立存在）。
        """
        self.connect()
        cur = self.conn.cursor()
        cur.execute("DELETE FROM company_list WHERE query_hash = ?", (query_hash,))
        deleted = cur.rowcount
        self.conn.commit()
        return deleted
