"""tests.company_list.test_db — JobDatabase 单元测试（全 mock，不依赖 Chrome/网络）."""

import json
import os
import sys
import tempfile
import unittest

# 确保可导入 scripts 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.company_list.db import (
    JobDatabase,
    build_query_url,
    compute_query_hash,
    DEFAULT_DB_PATH,
)


def _make_list_json(tmpdir, jobs=None):
    """创建一个列表 JSON 文件，返回路径."""
    path = os.path.join(tmpdir, "test_list.json")
    data = {
        "keyword": "agent",
        "city": "上海",
        "filters": {"scale": "303"},
        "scraped_at": "2026-09-29T23:14:15",
        "total": 0,
        "jobs": jobs or [],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _make_detail_json(tmpdir, brand_id, company_name="测试公司"):
    """创建一个详情 JSON 文件，返回路径."""
    path = os.path.join(tmpdir, f"{brand_id}.json")
    data = {
        "company_name": company_name,
        "job_count": 5,
        "boss_count": 2,
        "stage": "A轮",
        "scale": "100-499人",
        "industry": "互联网",
        "hot_jobs": {"total": 5, "shown": 0, "jobs": []},
        "description": "测试公司简介",
        "website": "https://example.com",
        "products": [],
        "business_info": {
            "企业名称": company_name,
            "法定代表人": "张三",
            "成立时间": "2020-01-01",
            "企业类型": "有限责任公司",
            "经营状态": "存续",
            "注册资本": "100万元",
            "注册地址": "上海市",
            "营业期限": "2020-01-01至-",
            "所属地区": "上海市",
            "统一社会信用代码": "91310112TESTCODE01",
            "核准日期": "2020-01-01",
            "曾用名": "-",
            "登记机关": "市场监管局",
            "所属行业": "互联网",
            "经营范围": "技术开发",
        },
        "address": "上海市",
        "work_hours": "上午09:00 - 下午06:00",
        "work_type": "双休",
        "benefits": ["五险一金", "年终奖"],
        "recruiters": [],
        "executives": [],
        "office_addresses": [],
        "url": f"https://www.zhipin.com/gongsi/{brand_id}.html",
        "scraped_at": "2026-09-29T23:43:30",
        "brand_id": brand_id,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


def _make_jobs():
    """创建测试用的职位列表."""
    return [
        {
            "title": "AI Agent开发工程师",
            "salary": "15-30K",
            "salary_source": "api",
            "location": "上海·徐汇区",
            "tags": "3-5年 | 本科",
            "boss_name": "测试科技",
            "boss_title": "招聘者",
            "boss_active_status": "",
            "company_scale": "100-499人",
            "company_stage": "A轮",
            "company_industry": "互联网",
            "job_labels": "3-5年 | 本科",
            "skills": "Python | AI",
            "welfare": "五险一金 | 年终奖",
            "encrypt_job_id": "abc123",
            "encrypt_boss_id": "boss456",
            "encrypt_brand_id": "brand789",
            "job_link": "https://www.zhipin.com/job_detail/abc123.html",
            "company_link": "https://www.zhipin.com/gongsi/brand789.html",
            "is_new": True,
            "job_id": "job001",
        },
        {
            "title": "Prompt Engineer",
            "salary": "20-40K",
            "salary_source": "api",
            "location": "上海·浦东新区",
            "tags": "5-10年 | 硕士",
            "boss_name": "测试科技",
            "boss_title": "HR",
            "boss_active_status": "在线",
            "company_scale": "100-499人",
            "company_stage": "A轮",
            "company_industry": "互联网",
            "job_labels": "5-10年 | 硕士",
            "skills": "LLM | Prompt",
            "welfare": "股票期权 | 弹性工作",
            "encrypt_job_id": "def456",
            "encrypt_boss_id": "boss789",
            "encrypt_brand_id": "brand789",
            "job_link": "https://www.zhipin.com/job_detail/def456.html",
            "company_link": "https://www.zhipin.com/gongsi/brand789.html",
            "is_new": True,
            "job_id": "job002",
        },
        {
            "title": "数据分析师",
            "salary": "10-20K",
            "salary_source": "api",
            "location": "北京·朝阳区",
            "tags": "1-3年 | 本科",
            "boss_name": "数据公司",
            "boss_title": "招聘者",
            "boss_active_status": "",
            "company_scale": "500-999人",
            "company_stage": "B轮",
            "company_industry": "企业服务",
            "job_labels": "1-3年 | 本科",
            "skills": "SQL | Python",
            "welfare": "五险一金",
            "encrypt_job_id": "ghi789",
            "encrypt_boss_id": "boss012",
            "encrypt_brand_id": "brand345",
            "job_link": "https://www.zhipin.com/job_detail/ghi789.html",
            "company_link": "https://www.zhipin.com/gongsi/brand345.html",
            "is_new": False,
            "job_id": "job003",
        },
    ]


class TestBuildQueryUrl(unittest.TestCase):
    """测试 build_query_url."""

    def test_basic(self):
        url = build_query_url("agent", "101020100", {})
        self.assertIn("city=101020100", url)
        self.assertIn("query=agent", url)
        self.assertTrue(url.startswith("https://www.zhipin.com/web/geek/jobs?"))

    def test_with_filters(self):
        url = build_query_url("agent", "101020100", {"scale": "303", "experience": "105"})
        self.assertIn("city=101020100", url)
        self.assertIn("query=agent", url)
        self.assertIn("scale=303", url)
        self.assertIn("experience=105", url)

    def test_filter_order(self):
        """筛选参数按固定顺序出现."""
        filters = {"salary": "406", "scale": "303", "experience": "105"}
        url = build_query_url("agent", "101020100", filters)
        exp_pos = url.index("experience=")
        scale_pos = url.index("scale=")
        salary_pos = url.index("salary=")
        self.assertLess(exp_pos, scale_pos)
        self.assertLess(scale_pos, salary_pos)


class TestComputeQueryHash(unittest.TestCase):
    """测试 compute_query_hash."""

    def test_stable(self):
        url = "https://www.zhipin.com/web/geek/jobs?city=101020100&query=agent"
        h1 = compute_query_hash(url)
        h2 = compute_query_hash(url)
        self.assertEqual(h1, h2)

    def test_length(self):
        url = "https://www.zhipin.com/web/geek/jobs?city=101020100&query=agent"
        h = compute_query_hash(url)
        self.assertEqual(len(h), 16)

    def test_different_urls(self):
        h1 = compute_query_hash("https://example.com?a=1")
        h2 = compute_query_hash("https://example.com?a=2")
        self.assertNotEqual(h1, h2)


class TestJobDatabaseSchema(unittest.TestCase):
    """测试建表."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        os.rmdir(self.tmpdir)

    def test_init_schema_idempotent(self):
        """重复建表不报错."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.init_schema()  # 第二次不应报错
        db.close()

    def test_tables_exist(self):
        """表已创建."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        cur = db.conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {r[0] for r in cur.fetchall()}
        self.assertIn("company_list", tables)
        self.assertIn("company_detail", tables)
        self.assertIn("company_insight", tables)
        db.close()


class TestImportListFromJson(unittest.TestCase):
    """测试 import_list_from_json."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.json_path = _make_list_json(self.tmpdir, _make_jobs())

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_import(self):
        """正常导入."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        inserted, skipped = db.import_list_from_json(self.json_path)
        self.assertEqual(inserted, 3)
        self.assertEqual(skipped, 0)
        db.close()

    def test_dedup(self):
        """重复导入不重复插入."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        inserted1, _ = db.import_list_from_json(self.json_path)
        inserted2, skipped2 = db.import_list_from_json(self.json_path)
        self.assertEqual(inserted1, 3)
        self.assertEqual(inserted2, 0)
        self.assertEqual(skipped2, 3)
        db.close()

    def test_empty_jobs(self):
        """空 jobs 列表."""
        json_path = _make_list_json(self.tmpdir, [])
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        inserted, skipped = db.import_list_from_json(json_path)
        self.assertEqual(inserted, 0)
        self.assertEqual(skipped, 0)
        db.close()


class TestGetPendingDetailBrands(unittest.TestCase):
    """测试 get_pending_detail_brands."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.json_path = _make_list_json(self.tmpdir, _make_jobs())

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_dedup_brands(self):
        """同一 brand_id 只返回一条."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_list_from_json(self.json_path)
        brands = db.get_pending_detail_brands()
        # 3 个职位来自 2 个不同 brand
        self.assertEqual(len(brands), 2)
        db.close()

    def test_empty_when_all_done(self):
        """全部完成后返回空列表."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_list_from_json(self.json_path)
        brands = db.get_pending_detail_brands()
        for b in brands:
            db.conn.execute(
                "INSERT INTO company_detail (brand_id, create_time) VALUES (?, ?)",
                (b["encrypt_brand_id"], "2026-09-30T00:00:00"),
            )
            db.mark_detail_done(b["encrypt_brand_id"])
        brands = db.get_pending_detail_brands()
        self.assertEqual(len(brands), 0)
        db.close()


class TestImportDetailFromJson(unittest.TestCase):
    """测试 import_detail_from_json."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.detail_path = _make_detail_json(self.tmpdir, "brand789", "上海测试科技有限公司")

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_import(self):
        """正常导入."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_detail_from_json(self.detail_path, "brand789")
        cur = db.conn.cursor()
        cur.execute("SELECT company_name, job_count FROM company_detail WHERE brand_id = ?", ("brand789",))
        row = cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "上海测试科技有限公司")
        self.assertEqual(row[1], 5)
        db.close()

    def test_upsert(self):
        """brand_id 冲突时更新."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_detail_from_json(self.detail_path, "brand789")
        # 修改后重新导入
        data = json.loads(open(self.detail_path, encoding="utf-8").read())
        data["job_count"] = 99
        with open(self.detail_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        db.import_detail_from_json(self.detail_path, "brand789")
        cur = db.conn.cursor()
        cur.execute("SELECT job_count FROM company_detail WHERE brand_id = ?", ("brand789",))
        row = cur.fetchone()
        self.assertEqual(row[0], 99)
        db.close()

    def test_business_info_json(self):
        """business_info 正确序列化."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_detail_from_json(self.detail_path, "brand789")
        cur = db.conn.cursor()
        cur.execute("SELECT business_info_json FROM company_detail WHERE brand_id = ?", ("brand789",))
        row = cur.fetchone()
        bi = json.loads(row[0])
        self.assertEqual(bi["企业名称"], "上海测试科技有限公司")
        self.assertIn("统一社会信用代码", bi)
        db.close()


class TestMarkDetailDone(unittest.TestCase):
    """测试 mark_detail_done."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.json_path = _make_list_json(self.tmpdir, _make_jobs())

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_mark_done(self):
        """更新关联行 has_detail=1."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_list_from_json(self.json_path)
        db.mark_detail_done("brand789")
        cur = db.conn.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM company_list WHERE encrypt_brand_id = ? AND has_detail = 1",
            ("brand789",),
        )
        row = cur.fetchone()
        # brand789 有 2 个职位，都应更新
        self.assertEqual(row[0], 2)
        db.close()


class TestGetStats(unittest.TestCase):
    """测试 get_stats."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.json_path = _make_list_json(self.tmpdir, _make_jobs())

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_stats(self):
        """统计数字正确."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_list_from_json(self.json_path)
        stats = db.get_stats()
        self.assertEqual(stats["total_jobs"], 3)
        self.assertEqual(stats["unique_companies"], 2)
        self.assertEqual(stats["pending_detail"], 2)
        self.assertEqual(stats["done_detail"], 0)
        self.assertEqual(stats["done_insight"], 0)
        db.close()

    def test_stats_after_detail(self):
        """导入详情后统计更新."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_list_from_json(self.json_path)
        detail_path = _make_detail_json(self.tmpdir, "brand789", "测试公司")
        db.import_detail_from_json(detail_path, "brand789")
        db.mark_detail_done("brand789")
        stats = db.get_stats()
        self.assertEqual(stats["done_detail"], 1)
        self.assertEqual(stats["pending_detail"], 1)
        db.close()


class TestGetPendingInsightBrands(unittest.TestCase):
    """测试 get_pending_insight_brands."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.json_path = _make_list_json(self.tmpdir, _make_jobs())

    def tearDown(self):
        for f in os.listdir(self.tmpdir):
            os.remove(os.path.join(self.tmpdir, f))
        os.rmdir(self.tmpdir)

    def test_no_pending_without_detail(self):
        """没有 detail 时返回空."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_list_from_json(self.json_path)
        brands = db.get_pending_insight_brands()
        self.assertEqual(len(brands), 0)
        db.close()

    def test_pending_after_detail(self):
        """有 detail 后返回待洞察品牌."""
        db = JobDatabase(self.db_path)
        db.connect()
        db.init_schema()
        db.import_list_from_json(self.json_path)
        detail_path = _make_detail_json(self.tmpdir, "brand789", "测试公司")
        db.import_detail_from_json(detail_path, "brand789")
        db.mark_detail_done("brand789")
        brands = db.get_pending_insight_brands()
        self.assertEqual(len(brands), 1)
        self.assertEqual(brands[0]["encrypt_brand_id"], "brand789")
        db.close()


class TestContextManager(unittest.TestCase):
    """测试上下文管理器."""

    def test_with(self):
        tmpdir = tempfile.mkdtemp()
        db_path = os.path.join(tmpdir, "test.db")
        try:
            with JobDatabase(db_path) as db:
                db.init_schema()
                cur = db.conn.cursor()
                cur.execute("SELECT 1")
                self.assertEqual(cur.fetchone()[0], 1)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)
            os.rmdir(tmpdir)




class TestListQueryIdentity(unittest.TestCase):
    """列表 JSON、文件名和数据库使用同一规范批次身份。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = JobDatabase(os.path.join(self.tmpdir.name, "jobs.db"))
        self.db.connect()
        self.db.init_schema()

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_import_uses_canonical_metadata_identity(self):
        city_code = "101020100"
        query_url = build_query_url("agent", city_code, {"scale": "303"})
        query_hash = compute_query_hash(query_url)
        path = os.path.join(self.tmpdir.name, f"{query_hash}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "keyword": "agent", "city": "上海", "city_code": city_code,
                "filters": {"scale": "303"}, "query_url": query_url,
                "query_hash": query_hash, "jobs": _make_jobs()[:1],
            }, f, ensure_ascii=False)

        self.db.import_list_from_json(path)
        row = self.db.conn.execute(
            "SELECT query_url, query_hash, city_code FROM company_list"
        ).fetchone()
        self.assertEqual(tuple(row), (query_url, query_hash, city_code))
        self.assertEqual(os.path.splitext(os.path.basename(path))[0], row["query_hash"])

    def test_legacy_json_resolves_city_name_not_job_location(self):
        path = _make_list_json(self.tmpdir.name, _make_jobs()[:1])
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        data["jobs"][0]["location"] = "北京·朝阳区"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

        self.db.import_list_from_json(path)
        row = self.db.conn.execute(
            "SELECT city_code, query_hash FROM company_list"
        ).fetchone()
        expected_url = build_query_url("agent", "101020100", {"scale": "303"})
        self.assertEqual(row["city_code"], "101020100")
        self.assertEqual(row["query_hash"], compute_query_hash(expected_url))

    def test_inconsistent_json_query_hash_is_rejected(self):
        query_url = build_query_url("agent", "101020100", {})
        path = os.path.join(self.tmpdir.name, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "keyword": "agent", "city": "上海", "city_code": "101020100",
                "filters": {}, "query_url": query_url, "query_hash": "wrong",
                "jobs": _make_jobs()[:1],
            }, f, ensure_ascii=False)

        with self.assertRaisesRegex(ValueError, "query_hash"):
            self.db.import_list_from_json(path)


class TestCompletionStateBoundaries(unittest.TestCase):
    """结果表记录和列表状态标记必须同时成立才算完成。"""

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db = JobDatabase(os.path.join(self.tmpdir.name, "jobs.db"))
        self.db.connect()
        self.db.init_schema()
        self.db.conn.execute(
            """INSERT INTO company_list (
                job_id, query_url, query_hash, keyword, city, encrypt_brand_id,
                has_detail, has_insight, create_time
            ) VALUES ('job1', 'url', 'hash', 'agent', '上海', 'brand1', 1, 1, '2026-09-30T00:00:00')"""
        )
        self.db.conn.commit()

    def tearDown(self):
        self.db.close()
        self.tmpdir.cleanup()

    def test_missing_result_rows_remain_pending_even_when_flags_are_set(self):
        stats = self.db.get_stats()
        self.assertEqual(stats["done_detail"], 0)
        self.assertEqual(stats["pending_detail"], 1)
        self.assertEqual(stats["done_insight"], 0)
        self.assertEqual(stats["pending_insight"], 1)

    def test_mixed_status_flags_keep_brand_pending_until_all_jobs_are_marked(self):
        self.db.conn.execute(
            """INSERT INTO company_list (
                job_id, query_url, query_hash, keyword, city, encrypt_brand_id,
                has_detail, has_insight, create_time
            ) VALUES ('job2', 'url', 'hash', 'agent', '上海', 'brand1', 1, 0, '2026-09-30T00:00:00')"""
        )
        self.db.conn.execute(
            "INSERT INTO company_detail (brand_id, credit_code, create_time) VALUES ('brand1', '91310104MA1FR5RY3N', 'now')"
        )
        self.db.conn.execute(
            "INSERT INTO company_insight (brand_id, credit_code, create_time) VALUES ('brand1', '91310104MA1FR5RY3N', 'now')"
        )
        self.db.conn.commit()

        stats = self.db.get_stats()

        self.assertEqual(stats["done_detail"], 1)
        self.assertEqual(stats["pending_detail"], 0)
        self.assertEqual(stats["done_insight"], 0)
        self.assertEqual(stats["pending_insight"], 1)

    def test_flags_and_result_rows_are_both_required_for_completion(self):
        self.db.conn.execute(
            "INSERT INTO company_detail (brand_id, credit_code, create_time) VALUES ('brand1', '91310104MA1FR5RY3N', 'now')"
        )
        self.db.conn.execute(
            "INSERT INTO company_insight (brand_id, credit_code, create_time) VALUES ('brand1', '91310104MA1FR5RY3N', 'now')"
        )
        self.db.conn.commit()
        stats = self.db.get_stats()
        self.assertEqual(stats["pending_detail"], 0)
        self.assertEqual(stats["done_detail"], 1)
        self.assertEqual(stats["pending_insight"], 0)
        self.assertEqual(stats["done_insight"], 1)


if __name__ == "__main__":
    unittest.main()
