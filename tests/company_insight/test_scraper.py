"""tests.company_insight.test_scraper — 验证码检测 / 命名统一 / 入库路径（全 mock）.

覆盖 #97 的三类回归：
1. 爱企查返回验证码页时必须能识别（否则整轮 44 家静默失败、看起来像卡死）
2. 洞察 JSON 命名必须统一为 aqc_{credit_code}.json（曾出现 3 种命名并存）
3. 单条 CLI 抓完必须入库并置 has_insight=1（否则下轮重复抓取）
"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.company_insight import scraper  # noqa: E402


class DetectBlockPageTests(unittest.TestCase):
    """验证码/风控页识别 —— 命中必须报出，正常页必须不报。"""

    def test_normal_detail_page_is_not_blocked(self):
        self.assertIsNone(
            scraper.detect_block_page(
                "https://aiqicha.baidu.com/company_detail_24480804208684",
                "谷斗科技（上海）有限公司 - 爱企查",
                "开业 高新技术企业(2025) 法定代表人：高景龙 注册资本：1,483万(元)",
            )
        )

    def test_normal_search_page_is_not_blocked(self):
        self.assertIsNone(
            scraper.detect_block_page(
                "https://aiqicha.baidu.com/s?q=91310104MA1FR5RY3N",
                "爱企查-企业查询",
                "上海千匠网络科技有限公司 开业 法定代表人：张宗兵",
            )
        )

    def test_verify_url_is_blocked(self):
        reason = scraper.detect_block_page(
            "https://aiqicha.baidu.com/verify?token=abc", "", ""
        )
        self.assertIsNotNone(reason)
        self.assertIn("verify", reason)

    def test_wappass_url_is_blocked(self):
        self.assertIsNotNone(
            scraper.detect_block_page("https://wappass.baidu.com/static/captcha", "", "")
        )

    def test_safecheck_url_is_blocked(self):
        self.assertIsNotNone(
            scraper.detect_block_page("https://aiqicha.baidu.com/safecheck/index", "", "")
        )

    def test_captcha_title_is_blocked(self):
        reason = scraper.detect_block_page(
            "https://aiqicha.baidu.com/s?q=x", "百度安全验证", ""
        )
        self.assertIsNotNone(reason)
        self.assertIn("标题", reason)

    def test_slider_text_is_blocked(self):
        reason = scraper.detect_block_page(
            "https://aiqicha.baidu.com/s?q=x",
            "爱企查",
            "请完成安全验证\n拖动滑块完成拼图",
        )
        self.assertIsNotNone(reason)
        self.assertIn("正文", reason)

    def test_frequent_access_text_is_blocked(self):
        self.assertIsNotNone(
            scraper.detect_block_page("", "", "访问过于频繁，请稍后再试")
        )

    def test_text_marker_below_first_screen_is_ignored(self):
        """正文只在首屏 2000 字符内匹配，避免页脚常驻文字误报。"""
        padded = "正常内容" * 600  # 2400 字符，把标记挤出首屏
        self.assertIsNone(
            scraper.detect_block_page("", "", padded + "访问过于频繁")
        )

    def test_raise_if_blocked_raises_typed_error(self):
        state = {"url": "https://aiqicha.baidu.com/verify", "title": "", "text": ""}
        with self.assertRaises(scraper.InsightBlockedError) as ctx:
            scraper._raise_if_blocked(state, "91310104MA1FR5RY3N")
        message = str(ctx.exception)
        self.assertIn("91310104MA1FR5RY3N", message)
        self.assertIn("不会自动绕过", message)

    def test_blocked_error_is_runtime_error_subclass(self):
        """pipeline 的旧 except 分支仍能兜住，不破坏向后兼容。"""
        self.assertTrue(issubclass(scraper.InsightBlockedError, RuntimeError))

    def test_raise_if_blocked_passes_through_normal_page(self):
        state = {
            "url": "https://aiqicha.baidu.com/company_detail_1",
            "title": "某公司 - 爱企查",
            "text": "开业",
        }
        self.assertIsNone(scraper._raise_if_blocked(state, "91310104MA1FR5RY3N"))


class InsightJsonPathTests(unittest.TestCase):
    """命名统一 —— CLI 与 pipeline 必须落到同一个路径。"""

    CREDIT_CODE = "91310104MA1FR5RY3N"

    def test_default_path_uses_aqc_prefix(self):
        path = scraper.insight_json_path(self.CREDIT_CODE)
        self.assertEqual(path.name, f"aqc_{self.CREDIT_CODE}.json")

    def test_output_dir_override_is_respected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = scraper.insight_json_path(self.CREDIT_CODE, tmpdir)
            self.assertEqual(str(path.parent), tmpdir)
            self.assertEqual(path.name, f"aqc_{self.CREDIT_CODE}.json")

    def test_save_insight_json_writes_to_unified_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            data = {"company_name": "测试公司", "credit_code": self.CREDIT_CODE}
            out = scraper.save_insight_json(data, self.CREDIT_CODE)
            self.assertTrue(out.exists())
            self.assertEqual(out.name, f"aqc_{self.CREDIT_CODE}.json")
            with open(out, encoding="utf-8") as f:
                self.assertEqual(json.load(f), data)

    def test_pipeline_and_cli_agree_on_filename(self):
        """pipeline 的路径推导必须与 scraper 的 helper 一致（防命名再次漂移）。"""
        from scripts.company_list.pipeline import (
            INSIGHT_FILENAME_PREFIX,
            insight_file_credit_code,
        )

        name = scraper.insight_json_path(self.CREDIT_CODE).name
        self.assertTrue(name.startswith(INSIGHT_FILENAME_PREFIX))
        self.assertEqual(insight_file_credit_code(name), self.CREDIT_CODE)


class ImportInsightJsonTests(unittest.TestCase):
    """抓完入库 —— 不再出现「JSON 已落盘但 has_insight 仍为 0」。"""

    CREDIT_CODE = "91310104MA1FR5RY3N"
    BRAND_ID = "abc123brandid"

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmpdir.name, "jobs.db")
        self.json_path = os.path.join(
            self.tmpdir.name, f"aqc_{self.CREDIT_CODE}.json"
        )
        with open(self.json_path, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "company_name": "上海千匠网络科技有限公司",
                    "credit_code": self.CREDIT_CODE,
                    "legal_person": "张宗兵",
                    "registered_capital": "500万(元)",
                    "company_type": "有限责任公司",
                    "industry": "软件和信息技术服务业",
                    "scraped_at": "2026-09-30T17:01:06",
                },
                f,
                ensure_ascii=False,
            )

    def tearDown(self):
        self.tmpdir.cleanup()

    def _seed_company(self):
        """在 DB 里造一家待爬洞察的公司（has_detail=1, has_insight=0）。"""
        from scripts.company_list.db import JobDatabase

        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.conn.execute(
            """INSERT INTO company_list (
                job_id, query_url, query_hash, keyword, city, encrypt_brand_id,
                has_detail, has_insight, create_time
            ) VALUES (?, ?, ?, ?, ?, ?, 1, 0, ?)""",
            ("job1", "https://x", "hash1", "agent", "上海", self.BRAND_ID,
             "2026-09-30T00:00:00"),
        )
        db.conn.execute(
            """INSERT INTO company_detail (
                brand_id, company_name, credit_code, create_time
            ) VALUES (?, ?, ?, ?)""",
            (self.BRAND_ID, "上海千匠网络科技有限公司", self.CREDIT_CODE,
             "2026-09-30T00:00:00"),
        )
        db.conn.commit()
        db.close()

    def test_import_sets_has_insight(self):
        self._seed_company()
        from scripts.company_list.db import JobDatabase

        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        try:
            ok = scraper.import_insight_json(self.json_path, self.CREDIT_CODE, db=db)
            self.assertTrue(ok)
            self.assertEqual(db.get_stats()["done_insight"], 1)
            self.assertEqual(db.get_stats()["pending_insight"], 0)
        finally:
            db.close()

    def test_import_returns_false_when_credit_code_unknown(self):
        """不在当前批次内的 credit_code：只存 JSON，明确返回 False 而非静默丢弃。"""
        from scripts.company_list.db import JobDatabase

        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        try:
            ok = scraper.import_insight_json(
                self.json_path, "99999999MA1FR5RY3N", db=db
            )
            self.assertFalse(ok)
            self.assertEqual(db.get_stats()["done_insight"], 0)
        finally:
            db.close()


class EnableLineBufferingTests(unittest.TestCase):
    """行缓冲 helper 必须健壮：任何环境都不应抛异常。"""

    def test_helper_is_importable_and_idempotent(self):
        from scripts.boss_cdp_raw import enable_line_buffering

        enable_line_buffering()
        enable_line_buffering()

    def test_helper_survives_stream_without_reconfigure(self):
        from scripts.boss_cdp_raw import enable_line_buffering

        original = sys.stdout
        sys.stdout = object()  # 没有 reconfigure 的假流
        try:
            enable_line_buffering()
        finally:
            sys.stdout = original


if __name__ == "__main__":
    unittest.main()
