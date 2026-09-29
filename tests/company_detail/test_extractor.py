"""Tests for company_detail extractor — pure text parsing, no Chrome/CDP needed."""

import unittest

from scripts.company_detail.extractor import (
    parse_basic_info,
    parse_hot_jobs,
    parse_description,
    parse_products,
    parse_business_info,
    parse_work_benefits,
    parse_recruiters,
    parse_executives,
    _clean,
    _split_lines,
)


SAMPLE_PAGE_TEXT = """
首页
职位
公司
校园
海归
APP
有了
海外
无障碍专区
搜索
消息
简历
李思
39在招职位3位BOSS
完善在线简历
新增附件简历
上海语生科学技术
收藏
未融资 100-499人 互联网
公司简介
招聘职位(39)
查看全部39个职位
热招职位
20-30K
3D 游戏特效师
3-5年
本科
上海
20-40K
AI产品经理（Agent方向）
3-5年
本科
在线
上海
20-40K
HRBP
5-10年
本科
在线
上海
公司简介
语生科学院以让人工智能普惠全球为愿景，助力年轻企业家，打破人工智能应用壁垒为使命。专注AI领域技术研究和AI智能业务发展，目前有AI穿越相机、AI陪伴机器人、虚拟人通讯IM、通用AI agent、AI文档、AI中医诊断等AI创新型产品，以及致力于自研大模型的深度研究与探索。
公司官网:https://www.genora.com/
展开
公司相册
上海浦东新区汇公馆4楼
上海市浦东新区汇公馆-8号楼
人才发展
完善的晋升机制
项目奖金
人才补贴
大牛带队
人脉积累
校招培养
产品介绍
语生科学
助力新生代创业者，打破人工智能应用壁垒。
工商信息
查看更多信息
企业名称：
上海语生科学技术有限公司
法定代表人：
郭忠祥
成立时间：
2024-06-28
企业类型：
有限责任公司（自然人投资或控股）
经营状态：
存续
注册资本：
10万元人民币
注册地址：
上海市闵行区江汉路223号1层
营业期限：
2024-06-28至无固定期限
所属地区：
上海市
统一社会信用代码：
91310112MADQUCFX6C
核准日期：
2024-06-28
曾用名：
-
登记机关：
闵行区市场监督管理局
所属行业：
软件开发
经营范围：
一般项目：技术服务、技术开发、技术咨询、技术交流、技术转让、技术推广；软件开发；人工智能应用软件开发。
公司地址
上海浦东新区汇公馆-8号楼4F
点击查看地图
工作时间及福利
上午10:00 - 下午07:00
双休、弹性工作
交通补助 生日福利 股票期权 年终奖 定期体检 五险一金
上海语生科学技术招聘Boss
正在招聘技术总监等职位
"""


class TestCleanAndSplit(unittest.TestCase):

    def test_clean_removes_extra_spaces(self):
        self.assertEqual(_clean("  hello   world  "), "hello world")

    def test_clean_handles_empty(self):
        self.assertEqual(_clean(""), "")
        self.assertEqual(_clean(None), "")

    def test_split_lines_skips_blanks(self):
        result = _split_lines("a\n\n  \nb\n")
        self.assertEqual(result, ["a", "b"])


class TestParseBasicInfo(unittest.TestCase):

    def test_company_name(self):
        result = parse_basic_info(SAMPLE_PAGE_TEXT)
        self.assertEqual(result["company_name"], "上海语生科学技术")

    def test_job_count(self):
        result = parse_basic_info(SAMPLE_PAGE_TEXT)
        self.assertEqual(result["job_count"], 39)

    def test_boss_count(self):
        result = parse_basic_info(SAMPLE_PAGE_TEXT)
        self.assertEqual(result["boss_count"], 3)

    def test_stage(self):
        result = parse_basic_info(SAMPLE_PAGE_TEXT)
        self.assertEqual(result["stage"], "未融资")

    def test_scale(self):
        result = parse_basic_info(SAMPLE_PAGE_TEXT)
        self.assertEqual(result["scale"], "100-499人")

    def test_industry(self):
        result = parse_basic_info(SAMPLE_PAGE_TEXT)
        self.assertEqual(result["industry"], "互联网")


class TestParseHotJobs(unittest.TestCase):

    def test_hot_jobs_count(self):
        result = parse_hot_jobs(SAMPLE_PAGE_TEXT)
        self.assertEqual(result["shown"], 3)

    def test_first_job(self):
        result = parse_hot_jobs(SAMPLE_PAGE_TEXT)
        jobs = result["jobs"]
        self.assertEqual(jobs[0]["salary"], "20-30K")
        self.assertEqual(jobs[0]["title"], "3D 游戏特效师")
        self.assertEqual(jobs[0]["experience"], "3-5年")
        self.assertEqual(jobs[0]["degree"], "本科")
        self.assertEqual(jobs[0]["location"], "上海")

    def test_online_status(self):
        result = parse_hot_jobs(SAMPLE_PAGE_TEXT)
        jobs = result["jobs"]
        self.assertEqual(jobs[1]["status"], "在线")

    def test_no_hot_jobs(self):
        result = parse_hot_jobs("没有热招职位的文本")
        self.assertEqual(result["jobs"], [])


class TestParseDescription(unittest.TestCase):

    def test_description_content(self):
        result = parse_description(SAMPLE_PAGE_TEXT)
        self.assertIn("语生科学院", result["description"])

    def test_website(self):
        result = parse_description(SAMPLE_PAGE_TEXT)
        self.assertEqual(result["website"], "https://www.genora.com/")


class TestParseProducts(unittest.TestCase):

    def test_products(self):
        result = parse_products(SAMPLE_PAGE_TEXT)
        self.assertGreaterEqual(len(result), 1)
        self.assertEqual(result[0]["name"], "语生科学")


class TestParseBusinessInfo(unittest.TestCase):

    def test_company_name(self):
        result = parse_business_info(SAMPLE_PAGE_TEXT)
        self.assertEqual(result.get("企业名称"), "上海语生科学技术有限公司")

    def test_legal_person(self):
        result = parse_business_info(SAMPLE_PAGE_TEXT)
        self.assertEqual(result.get("法定代表人"), "郭忠祥")

    def test_registration_capital(self):
        result = parse_business_info(SAMPLE_PAGE_TEXT)
        self.assertIn("10万元", result.get("注册资本", ""))

    def test_registered_address(self):
        result = parse_business_info(SAMPLE_PAGE_TEXT)
        self.assertIn("江汉路", result.get("注册地址", ""))


class TestParseWorkBenefits(unittest.TestCase):

    def test_address(self):
        result = parse_work_benefits(SAMPLE_PAGE_TEXT)
        self.assertEqual(result["address"], "上海浦东新区汇公馆-8号楼4F")

    def test_work_hours(self):
        result = parse_work_benefits(SAMPLE_PAGE_TEXT)
        self.assertIn("10:00", result["work_hours"])

    def test_work_type(self):
        result = parse_work_benefits(SAMPLE_PAGE_TEXT)
        self.assertIn("双休", result["work_type"])

    def test_benefits(self):
        result = parse_work_benefits(SAMPLE_PAGE_TEXT)
        self.assertIn("五险一金", result["benefits"])
        self.assertIn("年终奖", result["benefits"])


class TestParseRecruiters(unittest.TestCase):

    def test_recruiters(self):
        result = parse_recruiters(SAMPLE_PAGE_TEXT)
        self.assertGreaterEqual(len(result), 1)
        self.assertIn("技术总监", result[0].get("active_job", ""))


if __name__ == "__main__":
    unittest.main()
