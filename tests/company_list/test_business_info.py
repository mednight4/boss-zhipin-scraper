"""tests.company_list.test_business_info — business_info 独立列单元测试。"""

import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from scripts.company_list.db import JobDatabase

FULL_BUSINESS_INFO = {
    "企业名称": "北京智数信达科技有限公司",
    "法定代表人": "孙秀兰",
    "成立时间": "2023-08-16",
    "企业类型": "有限责任公司（自然人独资）",
    "经营状态": "存续",
    "注册资本": "120万人民币",
    "注册地址": "北京市石景山区八大处路49号院4号楼4层4754A",
    "营业期限": "2023-08-16至-",
    "所属地区": "北京市",
    "统一社会信用代码": "91110112MACWAEA47T",
    "核准日期": "2026-06-15",
    "曾用名": "北京瑞数信达科技有限公司",
    "登记机关": "北京市石景山区市场监督管理局",
    "所属行业": "科技推广和应用服务业",
    "经营范围": "一般项目：技术服务、技术开发...",
}


def _make_detail_json(tmpdir, brand_id, business_info=None, include_biz=True):
    """创建详情 JSON 文件。"""
    path = os.path.join(tmpdir, f"{brand_id}.json")
    data = {
        "company_name": "测试公司",
        "job_count": 5,
        "boss_count": 2,
        "stage": "A轮",
        "scale": "100-499人",
        "industry": "互联网",
        "business_info": business_info if include_biz else {},
    }
    if business_info and not include_biz:
        data["business_info"] = business_info
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path


class TestImportBusinessInfoColumns(unittest.TestCase):
    """测试 import_detail_from_json 正确填充独立列。"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.db = JobDatabase(self.db_path)
        self.db.connect()
        self.db.init_schema()

    def tearDown(self):
        self.db.close()

    def test_import_extracts_all_15_fields(self):
        """完整 business_info → 15 个独立列全部填充。"""
        json_path = _make_detail_json(self.tmpdir, "brand001", FULL_BUSINESS_INFO)
        self.db.import_detail_from_json(json_path, "brand001")

        cur = self.db.conn.cursor()
        cur.execute(
            """SELECT business_name, legal_representative, established_date,
                      company_type, business_status, registered_capital,
                      registered_address, business_term, region,
                      credit_code, approval_date, former_name,
                      registration_authority, business_industry, business_scope
               FROM company_detail WHERE brand_id = ?""",
            ("brand001",),
        )
        row = cur.fetchone()

        self.assertEqual(row[0], "北京智数信达科技有限公司")
        self.assertEqual(row[1], "孙秀兰")
        self.assertEqual(row[2], "2023-08-16")
        self.assertEqual(row[3], "有限责任公司（自然人独资）")
        self.assertEqual(row[4], "存续")
        self.assertEqual(row[5], "120万人民币")
        self.assertEqual(row[6], "北京市石景山区八大处路49号院4号楼4层4754A")
        self.assertEqual(row[7], "2023-08-16至-")
        self.assertEqual(row[8], "北京市")
        self.assertEqual(row[9], "91110112MACWAEA47T")
        self.assertEqual(row[10], "2026-06-15")
        self.assertEqual(row[11], "北京瑞数信达科技有限公司")
        self.assertEqual(row[12], "北京市石景山区市场监督管理局")
        self.assertEqual(row[13], "科技推广和应用服务业")
        self.assertEqual(row[14], "一般项目：技术服务、技术开发...")

    def test_import_empty_business_info(self):
        """空 business_info → 新列为空字符串。"""
        json_path = _make_detail_json(self.tmpdir, "brand002", {})
        self.db.import_detail_from_json(json_path, "brand002")

        cur = self.db.conn.cursor()
        cur.execute(
            """SELECT business_name, legal_representative, credit_code
               FROM company_detail WHERE brand_id = ?""",
            ("brand002",),
        )
        row = cur.fetchone()
        self.assertEqual(row[0], "")
        self.assertEqual(row[1], "")
        self.assertEqual(row[2], "")

    def test_import_missing_business_info_key(self):
        """JSON 无 business_info 键 → 不报错，新列为空。"""
        path = os.path.join(self.tmpdir, "nobiz.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"company_name": "测试"}, f)
        self.db.import_detail_from_json(path, "brand003")

        cur = self.db.conn.cursor()
        cur.execute(
            "SELECT business_name FROM company_detail WHERE brand_id = ?",
            ("brand003",),
        )
        row = cur.fetchone()
        self.assertEqual(row[0], "")

    def test_business_info_json_retained(self):
        """business_info_json 列仍保留完整 blob。"""
        json_path = _make_detail_json(self.tmpdir, "brand004", FULL_BUSINESS_INFO)
        self.db.import_detail_from_json(json_path, "brand004")

        cur = self.db.conn.cursor()
        cur.execute(
            "SELECT business_info_json FROM company_detail WHERE brand_id = ?",
            ("brand004",),
        )
        row = cur.fetchone()
        stored = json.loads(row[0])
        self.assertEqual(stored["企业名称"], "北京智数信达科技有限公司")
        self.assertEqual(stored["统一社会信用代码"], "91110112MACWAEA47T")


if __name__ == "__main__":
    unittest.main()
