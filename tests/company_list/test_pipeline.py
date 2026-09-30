"""tests.company_list.test_pipeline — 管道状态盘点与洞察步骤回归（全 mock）.

覆盖 #97 的三类回归：
1. `--step status` 的 JSON 对账必须能识别孤儿/旧命名/重复抓取（否则 agent 只能自建 check 脚本）
2. 命中验证码时必须中止整轮，而不是逐家失败 44 次（否则看起来像卡死）
3. 同名 JSON 已存在但 has_insight 仍为 0 时必须复用补导入，不重复抓取
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.company_list.db import JobDatabase  # noqa: E402
from scripts.company_list import pipeline  # noqa: E402
from scripts.company_insight.scraper import InsightBlockedError  # noqa: E402


def _write_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)


class InsightFileCreditCodeTests(unittest.TestCase):
    """从文件名推断 credit_code —— 决定文件被归到规范命名还是旧命名。"""

    def test_aqc_prefixed_credit_code(self):
        self.assertEqual(
            pipeline.insight_file_credit_code("aqc_91310104MA1FR5RY3N.json"),
            "91310104MA1FR5RY3N",
        )

    def test_bare_credit_code_filename(self):
        self.assertEqual(
            pipeline.insight_file_credit_code("91310104MA1FR5RY3N.json"),
            "91310104MA1FR5RY3N",
        )

    def test_brand_id_filename_is_not_a_credit_code(self):
        self.assertIsNone(
            pipeline.insight_file_credit_code("0a422a981c88f5321H153dS6.json")
        )

    def test_tilde_brand_id_filename_is_not_a_credit_code(self):
        self.assertIsNone(
            pipeline.insight_file_credit_code("03b13ce50be625f903163929FlQ~.json")
        )


class ClassifyInsightFilesTests(unittest.TestCase):
    """JSON 对账分类 —— 上一轮就是在这里丢了 8 个重复抓取。"""

    CREDIT_CODE = "91310104MA1FR5RY3N"
    OTHER_CREDIT_CODE = "91310117324576081E"
    BRAND_ID = "0a422a981c88f5321H153dS6"

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.dir = self.tmpdir.name
        self.known = {self.CREDIT_CODE}

    def tearDown(self):
        self.tmpdir.cleanup()

    def _resolve(self, credit_code):
        return "brand-1" if credit_code in self.known else None

    def _classify(self):
        return pipeline.classify_insight_files(self.dir, self._resolve)

    def test_missing_dir_returns_empty_inventory(self):
        result = pipeline.classify_insight_files(
            os.path.join(self.dir, "nope"), self._resolve
        )
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["canonical"], [])

    def test_canonical_file(self):
        _write_json(os.path.join(self.dir, f"aqc_{self.CREDIT_CODE}.json"), {})
        result = self._classify()
        self.assertEqual(result["canonical"], [f"aqc_{self.CREDIT_CODE}.json"])
        self.assertEqual(result["orphan"], [])
        self.assertEqual(result["legacy"], [])

    def test_orphan_file_is_detected(self):
        name = f"aqc_{self.OTHER_CREDIT_CODE}.json"
        _write_json(os.path.join(self.dir, name), {})
        result = self._classify()
        self.assertEqual(result["orphan"], [name])
        self.assertEqual(result["canonical"], [])

    def test_legacy_bare_credit_code_file_is_detected(self):
        name = f"{self.CREDIT_CODE}.json"
        _write_json(os.path.join(self.dir, name), {})
        result = self._classify()
        self.assertEqual(result["legacy"], [name])

    def test_legacy_brand_id_file_is_detected(self):
        """文件名是 brand_id，只能靠回读 JSON 内容里的 credit_code 识别。"""
        name = f"{self.BRAND_ID}.json"
        _write_json(
            os.path.join(self.dir, name), {"credit_code": self.OTHER_CREDIT_CODE}
        )
        result = self._classify()
        self.assertEqual(result["legacy"], [name])
        self.assertEqual(result["unreadable"], [])

    def test_duplicate_pair_is_reported(self):
        """同一 credit_code 的 aqc_ 版与旧命名版必须被识别为重复抓取。"""
        canonical = f"aqc_{self.CREDIT_CODE}.json"
        legacy = f"{self.CREDIT_CODE}.json"
        _write_json(os.path.join(self.dir, canonical), {})
        _write_json(os.path.join(self.dir, legacy), {})
        result = self._classify()
        self.assertIn(self.CREDIT_CODE, result["duplicates"])
        self.assertEqual(
            sorted(result["duplicates"][self.CREDIT_CODE]),
            sorted([canonical, legacy]),
        )

    def test_duplicate_detected_across_brand_id_naming(self):
        """brand_id 命名的旧文件与 aqc_ 版指向同一公司时也算重复。"""
        canonical = f"aqc_{self.CREDIT_CODE}.json"
        brand_id_file = f"{self.BRAND_ID}.json"
        _write_json(os.path.join(self.dir, canonical), {})
        _write_json(
            os.path.join(self.dir, brand_id_file), {"credit_code": self.CREDIT_CODE}
        )
        result = self._classify()
        self.assertIn(self.CREDIT_CODE, result["duplicates"])

    def test_unreadable_file_is_reported(self):
        name = "broken.json"
        with open(os.path.join(self.dir, name), "w", encoding="utf-8") as f:
            f.write("{ not json")
        result = self._classify()
        self.assertEqual(result["unreadable"], [name])

    def test_non_json_files_are_ignored(self):
        with open(os.path.join(self.dir, "notes.txt"), "w", encoding="utf-8") as f:
            f.write("hi")
        result = self._classify()
        self.assertEqual(result["total"], 0)


class Step5BlockedAbortTests(unittest.TestCase):
    """命中验证码必须中止整轮，而不是继续下一家。"""

    CREDIT_CODES = ["91310104MA1FR5RY3N", "91310117324576081E"]

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "jobs.db")
        self.insight_dir = os.path.join(self.tmpdir.name, "insight")
        os.makedirs(self.insight_dir)
        self._seed_db()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _seed_db(self):
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        for index, credit_code in enumerate(self.CREDIT_CODES):
            brand_id = f"brand{index}"
            db.conn.execute(
                """INSERT INTO company_list (
                    job_id, query_url, query_hash, keyword, city, encrypt_brand_id,
                    has_detail, has_insight, create_time
                ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)""",
                (f"job{index}", "https://x", "hash1", "agent", "上海", brand_id,
                 "2026-09-30T00:00:00"),
            )
            db.conn.execute(
                """INSERT INTO company_detail (
                    brand_id, company_name, credit_code, create_time
                ) VALUES (?, ?, ?, ?)""",
                (brand_id, f"公司{index}", credit_code, "2026-09-30T00:00:00"),
            )
        db.conn.commit()
        db.close()

    def _run_step5(self, scrape_fn):
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        try:
            return pipeline.step5_scrape_insights(
                db, scrape_fn, insight_json_dir=self.insight_dir
            )
        finally:
            db.close()

    def test_blocked_error_aborts_whole_run(self):
        calls = []

        def scrape_fn(credit_code):
            calls.append(credit_code)
            raise InsightBlockedError("命中验证码")

        with self.assertRaises(InsightBlockedError):
            self._run_step5(scrape_fn)

        # 关键断言：只尝试了第一家就中止，没有把 2 家都跑一遍
        self.assertEqual(len(calls), 1)

    def test_per_company_failure_does_not_abort(self):
        calls = []

        def scrape_fn(credit_code):
            calls.append(credit_code)
            raise RuntimeError("页面结构变化")

        imported = self._run_step5(scrape_fn)

        self.assertEqual(imported, 0)
        self.assertEqual(len(calls), len(self.CREDIT_CODES))

    def test_successful_scrape_imports_and_marks_done(self):
        def scrape_fn(credit_code):
            return {
                "company_name": f"公司{credit_code}",
                "credit_code": credit_code,
                "legal_person": "张三",
                "company_type": "有限责任公司",
                "industry": "软件和信息技术服务业",
                "scraped_at": "2026-09-30T17:01:06",
            }

        imported = self._run_step5(scrape_fn)
        self.assertEqual(imported, len(self.CREDIT_CODES))

        db = JobDatabase(self.db_path)
        db.connect()
        try:
            self.assertEqual(db.get_stats()["done_insight"], len(self.CREDIT_CODES))
            self.assertEqual(db.get_stats()["pending_insight"], 0)
        finally:
            db.close()

    def test_existing_json_is_reused_without_rescraping(self):
        """同名 JSON 已存在但 has_insight=0：补导入，不再发请求。"""
        credit_code = self.CREDIT_CODES[0]
        _write_json(
            os.path.join(self.insight_dir, f"aqc_{credit_code}.json"),
            {
                "company_name": "公司0",
                "credit_code": credit_code,
                "legal_person": "张三",
                "company_type": "有限责任公司",
                "industry": "软件和信息技术服务业",
                "scraped_at": "2026-09-30T17:01:06",
            },
        )

        scraped = []

        def scrape_fn(cc):
            scraped.append(cc)
            return {
                "company_name": f"新抓{cc}",
                "credit_code": cc,
                "legal_person": "李四",
                "company_type": "有限责任公司",
                "industry": "软件和信息技术服务业",
                "scraped_at": "2026-09-30T18:00:00",
            }

        self._run_step5(scrape_fn)

        # 第一家走补导入、不应重新抓取；第二家没有 JSON，才会走抓取
        self.assertEqual(scraped, [self.CREDIT_CODES[1]])

        db = JobDatabase(self.db_path)
        db.connect()
        try:
            # 第一家补导入、第二家实抓，两家都应完成
            self.assertEqual(db.get_stats()["done_insight"], 2)
            self.assertEqual(db.get_stats()["pending_insight"], 0)
        finally:
            db.close()

    def test_company_without_credit_code_is_skipped(self):
        db = JobDatabase(self.db_path)
        db.connect()
        db.conn.execute(
            """INSERT INTO company_list (
                job_id, query_url, query_hash, keyword, city, encrypt_brand_id,
                has_detail, has_insight, create_time
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)""",
            ("jobX", "https://x", "hash1", "agent", "上海", "brandX",
             "2026-09-30T00:00:00"),
        )
        db.conn.execute(
            """INSERT INTO company_detail (
                brand_id, company_name, credit_code, create_time
            ) VALUES (?, ?, ?, ?)""",
            ("brandX", "无信用代码公司", "", "2026-09-30T00:00:00"),
        )
        db.conn.commit()
        db.close()

        calls = []

        def scrape_fn(credit_code):
            calls.append(credit_code)
            return {}

        self._run_step5(scrape_fn)
        self.assertNotIn("", calls)


class Step3BlockedAbortTests(unittest.TestCase):
    """详情链路命中验证码必须中止整轮，且不得把验证页当成详情写入 DB（#97）。"""

    BRAND_IDS = ["brand0", "brand1"]

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "jobs.db")
        self.detail_dir = os.path.join(self.tmpdir.name, "company")
        self._seed_db()

    def tearDown(self):
        self.tmpdir.cleanup()

    def _seed_db(self):
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        for index, brand_id in enumerate(self.BRAND_IDS):
            db.conn.execute(
                """INSERT INTO company_list (
                    job_id, query_url, query_hash, keyword, city, encrypt_brand_id,
                    company_link, has_detail, has_insight, create_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?)""",
                (f"job{index}", "https://x", "hash1", "agent", "上海", brand_id,
                 f"https://www.zhipin.com/gongsi/{brand_id}.html",
                 "2026-09-30T00:00:00"),
            )
        db.conn.commit()
        db.close()

    def _run_step3(self, scrape_fn):
        from scripts.boss_cdp_raw import SecurityCheckError

        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        try:
            return pipeline.step3_scrape_details(
                db, scrape_fn, detail_json_dir=self.detail_dir
            )
        finally:
            db.close()

    def test_security_check_aborts_whole_run(self):
        from scripts.boss_cdp_raw import SecurityCheckError

        calls = []

        def scrape_fn(company_link):
            calls.append(company_link)
            raise SecurityCheckError("命中验证码")

        with self.assertRaises(SecurityCheckError):
            self._run_step3(scrape_fn)

        # 只尝试第一家就中止，没有把两家都跑一遍
        self.assertEqual(len(calls), 1)

    def test_aborted_company_is_not_marked_done(self):
        """中止的那家不能被置 has_detail=1，否则状态入口会把它当成已完成。"""
        from scripts.boss_cdp_raw import SecurityCheckError

        def scrape_fn(company_link):
            raise SecurityCheckError("命中验证码")

        with self.assertRaises(SecurityCheckError):
            self._run_step3(scrape_fn)

        db = JobDatabase(self.db_path)
        db.connect()
        try:
            self.assertEqual(db.get_stats()["done_detail"], 0)
            self.assertEqual(db.get_stats()["pending_detail"], len(self.BRAND_IDS))
        finally:
            db.close()

    def test_per_company_failure_does_not_abort(self):
        calls = []

        def scrape_fn(company_link):
            calls.append(company_link)
            raise RuntimeError("页面结构变化")

        imported = self._run_step3(scrape_fn)

        self.assertEqual(imported, 0)
        self.assertEqual(len(calls), len(self.BRAND_IDS))

    def test_successful_scrape_marks_detail_done(self):
        def scrape_fn(company_link):
            return {
                "brand_id": company_link.rsplit("/", 1)[-1].replace(".html", ""),
                "company_name": "测试公司",
                "stage": "已上市",
                "scale": "1000-9999人",
                "industry": "互联网",
                "business_info": {"统一社会信用代码": "91310104MA1FR5RY3N"},
                "scraped_at": "2026-09-30T17:01:06",
            }

        imported = self._run_step3(scrape_fn)
        self.assertEqual(imported, len(self.BRAND_IDS))

        db = JobDatabase(self.db_path)
        db.connect()
        try:
            self.assertEqual(db.get_stats()["done_detail"], len(self.BRAND_IDS))
        finally:
            db.close()


class PrintStatusSmokeTests(unittest.TestCase):
    """status 是 agent 唯一的查状态入口，必须能在空库/有数据两种情况下跑通。"""

    def test_print_status_on_empty_db(self):
        import io
        from contextlib import redirect_stdout

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "empty.db")
            buf = io.StringIO()
            with redirect_stdout(buf):
                pipeline.print_status(
                    db_path=db_path, insight_json_dir=os.path.join(tmpdir, "insight")
                )
            output = buf.getvalue()

        self.assertIn("查询批次", output)
        self.assertIn("总体进度", output)
        self.assertIn("待爬洞察", output)


if __name__ == "__main__":
    unittest.main()
