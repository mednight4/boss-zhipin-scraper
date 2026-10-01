"""公司列表只读查询回归测试。"""

import json
import os
import sqlite3
import sys
import tempfile
import unittest
import importlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.company_list.db import (
    COMPANY_INSIGHT_TABLE_SQL,
    JobDatabase,
    compute_query_hash,
    normalize_employee_count,
)  # noqa: E402

query_cli = importlib.import_module("scripts.company_list.query")


class NormalizeEmployeeCountTests(unittest.TestCase):
    def test_supported_values(self):
        cases = {
            0: 0,
            "0": 0,
            "28": 28,
            "28人": 28,
            " 1,234 人 ": 1234,
            "1,234": 1234,
            "1，234人": 1234,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(normalize_employee_count(raw), expected)

    def test_missing_or_ambiguous_values(self):
        for raw in (None, "", "-", "暂无", "未公示", "约 28 人", "28人以上"):
            with self.subTest(raw=raw):
                self.assertIsNone(normalize_employee_count(raw))


class ReadOnlyQueryTests(unittest.TestCase):
    QUERY_URL = "https://www.zhipin.com/web/geek/jobs?city=101020100&query=agent"
    QUERY_HASH = compute_query_hash(QUERY_URL)

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "jobs.db")
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        self._seed(db)
        db.close()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _seed(self, db):
        rows = [
            ("job-49", "低于边界", "brand-49", 49),
            ("job-50", "含下边界", "brand-50", 50),
            ("job-100", "含上边界", "brand-100", 100),
            ("job-101", "高于边界", "brand-101", 101),
        ]
        for job_id, title, brand_id, employee_count in rows:
            db.conn.execute(
                """INSERT INTO company_list (
                    job_id, query_url, query_hash, keyword, city, city_code,
                    title, location, encrypt_brand_id, job_link, company_link,
                    has_detail, has_insight, create_time, scraped_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)""",
                (
                    job_id,
                    self.QUERY_URL,
                    self.QUERY_HASH,
                    "大模型应用开发",
                    "上海",
                    "101020100",
                    title,
                    "上海·浦东新区",
                    brand_id,
                    f"https://www.zhipin.com/job_detail/{job_id}.html",
                    f"https://www.zhipin.com/gongsi/{brand_id}.html",
                    "2026-10-01T00:00:00",
                    "2026-10-01T00:00:00",
                ),
            )
            db.conn.execute(
                """INSERT INTO company_detail (
                    brand_id, company_name, url, create_time
                ) VALUES (?, ?, ?, ?)""",
                (
                    brand_id,
                    f"公司{brand_id}",
                    f"https://www.zhipin.com/gongsi/{brand_id}.html",
                    "2026-10-01T00:00:00",
                ),
            )
            db.conn.execute(
                """INSERT INTO company_insight (
                    brand_id, company_name, employee_count, url, scraped_at, create_time
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    brand_id,
                    f"公司{brand_id}",
                    int(employee_count),
                    f"https://aiqicha.baidu.com/company_detail_{brand_id}",
                    "2026-10-01T01:00:00",
                    "2026-10-01T00:00:00",
                ),
            )
        db.conn.execute(
            """INSERT INTO company_list (
                job_id, query_url, query_hash, keyword, city, city_code,
                title, location, encrypt_brand_id, job_link, company_link,
                has_detail, has_insight, create_time, scraped_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)""",
            (
                "job-50-second", self.QUERY_URL, self.QUERY_HASH,
                "大模型应用开发", "上海", "101020100", "同公司另一个职位",
                "上海·浦东新区", "brand-50",
                "https://www.zhipin.com/job_detail/job-50-second.html",
                "https://www.zhipin.com/gongsi/brand-50.html",
                "2026-10-01T00:00:00", "2026-10-01T00:00:00",
            ),
        )
        db.conn.commit()

    def test_inclusive_range_and_links(self):
        db = JobDatabase(self.db_path, read_only=True)
        db.connect()
        try:
            rows = db.query_jobs_by_employee_count(
                self.QUERY_HASH, employee_min=50, employee_max=100, limit=None
            )
            self.assertEqual(sorted(row["employee_count"] for row in rows), [50, 50, 100])
            self.assertEqual(rows[0]["boss_detail_url"], "https://www.zhipin.com/gongsi/brand-50.html")
            self.assertTrue(rows[0]["aiqicha_url"].startswith("https://aiqicha.baidu.com/"))
            self.assertEqual(db.count_jobs_by_employee_count(self.QUERY_HASH, 50, 100), 3)
        finally:
            db.close()

    def test_query_does_not_modify_database(self):
        with open(self.db_path, "rb") as handle:
            before = handle.read()
        db = JobDatabase(self.db_path, read_only=True)
        db.connect()
        try:
            db.get_query_batch_info(self.QUERY_HASH)
            db.query_jobs_by_employee_count(self.QUERY_HASH, 50, 100)
        finally:
            db.close()
        with open(self.db_path, "rb") as handle:
            after = handle.read()
        self.assertEqual(after, before)

    def test_missing_database_is_not_created(self):
        missing = os.path.join(self.tmpdir.name, "missing.db")
        db = JobDatabase(missing, read_only=True)
        with self.assertRaises(FileNotFoundError):
            db.connect()
        self.assertFalse(os.path.exists(missing))

    def test_query_url_selects_same_batch(self):
        db = JobDatabase(self.db_path, read_only=True)
        db.connect()
        try:
            args = query_cli.build_arg_parser().parse_args([
                "--query-url", self.QUERY_URL,
                "--employee-min", "50",
                "--employee-max", "100",
            ])
            args.query_hash = query_cli.resolve_query_hash(args)
            payload = query_cli.build_payload(db, args)
        finally:
            db.close()
        self.assertEqual(args.query_hash, self.QUERY_HASH)
        self.assertEqual(payload["matched_job_count"], 3)

    def test_read_only_methods_require_read_only_connection(self):
        db = JobDatabase(self.db_path)
        db.connect()
        try:
            with self.assertRaises(RuntimeError):
                db.query_jobs_by_employee_count(self.QUERY_HASH, 50, 100)
        finally:
            db.close()

    def test_list_batches(self):
        db = JobDatabase(self.db_path, read_only=True)
        db.connect()
        try:
            batches = db.list_query_batch_summaries()
        finally:
            db.close()
        self.assertEqual(len(batches), 1)
        self.assertEqual(batches[0]["query_hash"], self.QUERY_HASH)
        self.assertEqual(batches[0]["job_count"], 5)
        self.assertEqual(batches[0]["detail_done"], 4)
        self.assertEqual(batches[0]["insight_done"], 4)

    def test_cli_payload_contains_batch_and_results(self):
        db = JobDatabase(self.db_path, read_only=True)
        db.connect()
        try:
            args = query_cli.build_arg_parser().parse_args([
                "--db-path", self.db_path,
                "--query-hash", self.QUERY_HASH,
                "--employee-min", "50",
                "--employee-max", "100",
                "--format", "json",
            ])
            payload = query_cli.build_payload(db, args)
        finally:
            db.close()
        self.assertEqual(payload["batch"]["keyword"], "大模型应用开发")
        self.assertEqual(payload["matched_job_count"], 3)
        json.dumps(payload, ensure_ascii=False)


class EmployeeCountMigrationTests(unittest.TestCase):
    def test_old_text_column_is_migrated_idempotently(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "old.db")
            conn = sqlite3.connect(path)
            old_schema = COMPANY_INSIGHT_TABLE_SQL.replace(
                "employee_count  INTEGER", "employee_count  TEXT"
            )
            conn.executescript(old_schema)
            conn.execute(
                "INSERT INTO company_insight (brand_id, company_name, employee_count, url, create_time) VALUES (?, ?, ?, ?, ?)",
                ("brand-28", "原公司名", "28人", "https://example.com/detail", "2026-10-01"),
            )
            conn.execute(
                "INSERT INTO company_insight (brand_id, employee_count, create_time) VALUES (?, ?, ?)",
                ("brand-0", "0", "2026-10-01"),
            )
            conn.execute(
                "INSERT INTO company_insight (brand_id, employee_count, create_time) VALUES (?, ?, ?)",
                ("brand-empty", "", "2026-10-01"),
            )
            conn.execute(
                "INSERT INTO company_insight (brand_id, employee_count, create_time) VALUES (?, ?, ?)",
                ("brand-ambiguous", "约 3 人", "2026-10-01"),
            )
            conn.commit()
            conn.close()

            db = JobDatabase(path)
            db.connect()
            db.init_schema()
            column = db.conn.execute(
                "SELECT type FROM pragma_table_info('company_insight') WHERE name='employee_count'"
            ).fetchone()[0]
            values = dict(db.conn.execute(
                "SELECT brand_id, employee_count FROM company_insight"
            ).fetchall())
            preserved = db.conn.execute(
                "SELECT company_name, url FROM company_insight WHERE brand_id='brand-28'"
            ).fetchone()
            indexes = {
                row[0] for row in db.conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='company_insight'"
                )
            }
            db.init_schema()
            self.assertEqual(column.upper(), "INTEGER")
            self.assertEqual(values, {
                "brand-28": 28, "brand-0": 0, "brand-empty": None,
                "brand-ambiguous": None,
            })
            self.assertEqual(tuple(preserved), ("原公司名", "https://example.com/detail"))
            self.assertTrue({"idx_ci_brand_id", "idx_ci_credit_code"}.issubset(indexes))
            self.assertEqual(db.conn.execute("SELECT COUNT(*) FROM company_insight").fetchone()[0], 4)
            db.close()


class InsightImportNormalizationTests(unittest.TestCase):
    def test_old_text_json_and_new_integer_json_are_imported_as_integer(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = JobDatabase(os.path.join(tmpdir, "jobs.db"))
            db.connect()
            db.init_schema()
            for brand_id, employee_count in (("old-json", "28人"), ("new-json", 17), ("missing-json", "")):
                path = os.path.join(tmpdir, f"{brand_id}.json")
                with open(path, "w", encoding="utf-8") as handle:
                    json.dump({"employee_count": employee_count, "company_name": brand_id}, handle)
                db.import_insight_from_json(path, brand_id)
            values = dict(db.conn.execute(
                "SELECT brand_id, employee_count FROM company_insight"
            ).fetchall())
            self.assertEqual(values, {"old-json": 28, "new-json": 17, "missing-json": None})
            db.close()


class MigrationRollbackTests(unittest.TestCase):
    def test_incomplete_legacy_schema_is_not_dropped_on_migration_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "incomplete.db")
            conn = sqlite3.connect(path)
            legacy_schema = COMPANY_INSIGHT_TABLE_SQL.replace(
                "employee_count  INTEGER", "employee_count  TEXT"
            ).replace("create_time     TEXT NOT NULL", "create_time     TEXT")
            conn.executescript(legacy_schema)
            conn.execute(
                "INSERT INTO company_insight (brand_id, employee_count, create_time) VALUES (?, ?, ?)",
                ("preserve-me", "32人", None),
            )
            conn.commit()
            conn.close()

            db = JobDatabase(path)
            db.connect()
            with self.assertRaises(sqlite3.IntegrityError):
                db.init_schema()
            row = db.conn.execute(
                "SELECT brand_id, employee_count FROM company_insight"
            ).fetchone()
            self.assertEqual(tuple(row), ("preserve-me", "32人"))
            db.close()


if __name__ == "__main__":
    unittest.main()
