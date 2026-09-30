"""爱企查公司详情爬虫：CDP 导航 → 点击搜索结果 → 提取工商信息。

复用 boss_cdp_raw.py 的 CDPSession + create_page_session 基础设施。
"""
from __future__ import annotations

import json
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.boss_cdp_raw import CDPSession, create_page_session  # noqa: E402

SEARCH_URL_TEMPLATE = "https://aiqicha.baidu.com/s?q={credit_code}"
OUTPUT_DIR = PROJECT_ROOT / "output" / "insight"
CDP_PORT = 9222


# ── 文本工具 ─────────────────────────────────────────────────────
def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _split_lines(text: str) -> list[str]:
    raw_lines = text.split("\n")
    lines = []
    for line in raw_lines:
        stripped = line.strip()
        if stripped:
            lines.append(stripped)
    return lines


# ── 页面交互 ─────────────────────────────────────────────────────
def navigate_and_click_company(ws, sid, credit_code, timeout=15):
    """导航到爱企查搜索页，提取公司 ID，直接跳转详情页。

    爱企查搜索结果页中公司卡片为 <a class="card" data-log-title="item-{company_id}">，
    详情页 URL: https://aiqicha.baidu.com/company_detail_{company_id}

    Args:
        ws: CDPSession 实例
        sid: 页面 session ID
        credit_code: 统一社会信用代码
        timeout: 等待搜索结果加载的超时秒数

    Returns:
        str: 详情页的 URL
    """
    search_url = SEARCH_URL_TEMPLATE.format(credit_code=credit_code)
    ws.send("Page.navigate", {"url": search_url}, sid)
    time.sleep(random.uniform(5, 8))

    # 从搜索结果中提取公司 ID
    extract_id_js = """
    (function() {
        var card = document.querySelector('a.card[data-log-title]');
        if (!card) {
            // 回退：找任何带 data-log-title 的链接
            card = document.querySelector('[data-log-title^="item-"]');
        }
        if (card) {
            var title = card.getAttribute('data-log-title');
            var m = title.match(/item-(\\d+)/);
            if (m) return m[1];
        }
        return '';
    })()
    """
    company_id = ws.eval_js(extract_id_js, sid)
    if not company_id:
        time.sleep(3)
        company_id = ws.eval_js(extract_id_js, sid)

    if not company_id:
        raise RuntimeError(
            "未找到公司 ID (credit_code={})，"
            "可能需要人工处理验证码或页面结构已变化".format(credit_code)
        )

    # 直接导航到详情页
    detail_url = "https://aiqicha.baidu.com/company_detail_{}".format(company_id)
    ws.send("Page.navigate", {"url": detail_url}, sid)
    time.sleep(random.uniform(5, 8))
    return detail_url


def extract_page_text(ws, sid, scroll_rounds=6) -> dict:
    """在当前页面提取 innerText（详情页）。"""
    for _ in range(scroll_rounds):
        delta = random.randint(200, 500)
        ws.eval_js(f"window.scrollBy(0, {delta})", sid)
        time.sleep(random.uniform(0.5, 1.5))

    ws.eval_js("window.scrollTo(0, 0)", sid)
    time.sleep(0.5)

    js = """
    (function(){
        var text = document.body ? document.body.innerText : '';
        var html = document.documentElement ? document.documentElement.outerHTML : '';
        return JSON.stringify({
            url: location.href,
            title: document.title || '',
            text: text,
            html: html.substring(0, 80000)
        });
    })()
    """
    val = ws.eval_js(js, sid)
    return json.loads(val) if isinstance(val, str) else {}


# ── 文本解析 ─────────────────────────────────────────────────────
def parse_aqc_business_info(text: str) -> dict:
    """解析爱企查详情页的工商信息区块。

    爱企查详情页特点：
    - 顶部有 tab 导航（"基本信息 爱企查图谱 工商注册..."），一行内多个短词
    - 字段标签和值常在同一行，用空格/冒号分隔
    - 经营范围很长，独占多行

    策略：先清理 tab 导航行，再按字段标签位置分段匹配。
    """
    # ── 第一步：清理 tab 导航行 ─────────────────────────────────
    # 爱企查页面顶部常有 "基本信息 爱企查图谱 工商注册 风险洞察..." 这样的 tab 行
    # 特征：一行内有 4+ 个空格分隔的短词，且包含已知的 tab 关键词
    TAB_KEYWORDS = {
        "基本信息", "爱企查图谱", "工商注册", "风险洞察", "股东信息",
        "股权穿透图", "主要人员", "企业受益", "实际控制人", "最终受益人",
        "对外投资", "控股企业", "协同股东", "间接持股", "变更记录",
        "财务数据", "企业年报", "分支机构", "总公司", "商品服务",
        "司法信息", "司法案件", "涉诉关系", "立案信息", "开庭公告",
        "裁判文书", "被执行人", "股权冻结", "司法拍卖", "限制高消费",
        "失信被执行人", "终本案件", "法院公告", "经营诊断", "财产线索",
        "合作风险", "竞争风险", "经营纠纷", "空壳扫描", "经营异常",
        "行政处罚", "知识产权", "出质", "动产抵押", "清算组", "简易注销",
        "严重违法", "税务违法", "环保处罚", "欠税公告", "破产重整",
        "土地抵押", "网站备案", "商标信息", "专利信息", "软件著作权",
        "作品著作权", "企业发展", "融资信息", "核心成员", "企业项目",
        "荣誉", "竞品信息", "投资机构", "私募基金", "企业实力",
        "新闻资讯", "经营状况", "行政许可", "质量监督检查", "资质证书",
        "招投标", "微博", "微信公众号", "APP", "公司研报", "相关研报",
        "地块公示", "土地转让", "购地信息", "一般纳税人", "进出口信用",
        "客户供应商", "上榜榜单", "求职检测", "招聘信息", "工资待遇",
        "债券信息", "建筑资质", "第三方评级", "历史信息", "已认证人员",
        "疑似关系", "食品抽检", "抽查检查", "双随机", "询价评估",
    }

    raw_lines = text.split("\n")
    clean_lines = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue
        # 检测是否为 tab 导航行：一行内 3+ 个 tab 关键词
        words = stripped.split()
        tab_count = sum(1 for w in words if w in TAB_KEYWORDS)
        if tab_count >= 3:
            continue  # 跳过 tab 导航行
        clean_lines.append(stripped)

    # ── 第二步：将多字段同行拆分为独立 segment ─────────────────
    # 爱企查常见模式："法定代表人：张宗兵 注册资本：1,111.11万(元) 成立时间：2016-10-14"
    # 需要按字段标签位置切割
    FIELD_LABELS = [
        "企业名称", "法定代表人", "法人", "执行事务合伙人",
        "注册资本", "实缴资本", "成立时间", "成立日期", "注册日期",
        "经营状态", "登记状态",
        "公司类型", "企业类型", "所属行业",
        "注册地址", "住所",
        "统一社会信用代码", "信用代码",
        "经营范围", "营业期限", "登记机关", "核准日期", "核准",
        "工商注册号", "组织机构代码", "纳税人识别号", "纳税人资质",
        "参保人数", "曾用名", "行政区划",
        "企业规模", "简介",
    ]

    # 构建正则：匹配 "标签：值" 或 "标签 值"，值到下一个标签或行尾
    label_pattern = "|".join(re.escape(l) for l in FIELD_LABELS)
    segment_re = re.compile(
        r"(" + label_pattern + r")\s*[：:\t]\s*.*?(?=(?:" + label_pattern + r")\s*[：:\t]|$)",
        re.DOTALL
    )

    segments = []
    for line in clean_lines:
        matches = list(segment_re.finditer(line))
        if matches:
            for m in matches:
                seg = m.group(0).strip()
                if seg:
                    segments.append(seg)
        else:
            segments.append(line)

    # ── 第三步：将 segments 映射到标准字段 ─────────────────────
    FIELD_MAP = {
        "企业名称": "企业名称",
        "法定代表人": "legal_person",
        "法人": "legal_person",
        "执行事务合伙人": "legal_person",
        "注册资本": "registered_capital",
        "实缴资本": "paid_in_capital",
        "成立时间": "establish_date",
        "成立日期": "establish_date",
        "注册日期": "establish_date",
        "经营状态": "business_status",
        "登记状态": "business_status",
        "公司类型": "company_type",
        "企业类型": "company_type",
        "所属行业": "industry",
        "注册地址": "registered_address",
        "住所": "registered_address",
        "统一社会信用代码": "credit_code",
        "信用代码": "credit_code",
        "经营范围": "business_scope",
        "营业期限": "business_term",
        "登记机关": "registration_authority",
        "核准日期": "approval_date",
        "核准": "approval_date",
        "工商注册号": "registration_number",
        "组织机构代码": "org_code",
        "纳税人识别号": "taxpayer_id",
        "纳税人资质": "taxpayer_qualification",
        "参保人数": "employee_count",
        "曾用名": "former_name",
        "行政区划": "administrative_division",
        "企业规模": "scale",
        "简介": "description",
    }

    fields = {}
    current_field = None
    current_value = []

    def flush():
        if current_field and current_value:
            value = _clean(" ".join(current_value))
            value = re.sub(r"^" + re.escape(current_field_label) + r"\s*[：:]\s*", "", value)
            if value and value != "-":
                std_name = FIELD_MAP.get(current_field, current_field)
                fields[std_name] = value

    for seg in segments:
        matched = False
        for label in FIELD_LABELS:
            if seg.startswith(label):
                flush()
                current_field = label
                current_field_label = label
                remainder = seg[len(label):]
                remainder = re.sub(r"^\s*[：:]\s*", "", remainder)
                current_value = [remainder] if remainder and remainder != "-" else []
                matched = True
                break

        if not matched:
            if current_field and seg:
                # 检查是否是其他已知字段的开头（表示当前字段结束）
                is_new_field = any(seg.startswith(l) for l in FIELD_LABELS)
                if is_new_field:
                    flush()
                    current_field = None
                    current_value = []
                else:
                    current_value.append(seg)

    flush()
    return fields


def _is_section_boundary(line: str, field_patterns: dict) -> bool:
    """判断是否为新区段开始（非字段的独立标题行）。"""
    section_markers = [
        "主要人员", "股东信息", "对外投资", "分支机构",
        "变更记录", "司法风险", "经营风险", "企业年报",
        "实际控制人", "最终受益人", "历史股东", "高管",
    ]
    return any(line.startswith(m) for m in section_markers)


def parse_company_name(text: str, title: str = "") -> str:
    """提取公司名称。

    优先从页面标题（document.title）提取，格式通常为 "企业名称 - 爱企查"。
    回退：从文本前几行中找不含导航关键词的行。
    """
    # 优先从 title 提取
    if title:
        # 格式: "企业名称 - 品牌名 - 爱企查" 或 "企业名称 - 爱企查"
        m = re.match(r"(.+?)\s*[-–—]\s*(.+?)?\s*[-–—]\s*爱企查", title)
        if m:
            return m.group(1).strip()
        m = re.match(r"(.+?)\s*[-–—]\s*爱企查", title)
        if m:
            return m.group(1).strip()
        # 如果没有 " - 爱企查" 格式，直接清理尾部
        title = re.sub(r"\s*[-–—]\s*爱企查.*", "", title).strip()
        if title:
            return title

    # 回退：从前几行找
    lines = _split_lines(text)
    skip_keywords = ["爱企查", "百度", "搜索", "登录", "查一下", "查企业", "APP"]
    for line in lines[:8]:
        if line and len(line) > 2 and not any(kw in line for kw in skip_keywords):
            return line
    return ""


def parse_contact_info(text: str) -> dict:
    """解析联系信息（电话、邮箱、网址）。

    页面结构:
        电话：
        021-54355235
        更多电话
        邮箱：
        caiwu@qianjiangcloud.c...
        获取更多邮箱
        网址：
        www.qjclouds.cn更多
    """
    lines = _split_lines(text)
    result = {"phone": "", "email": "", "website": ""}

    LABEL_MAP = {
        "电话：": "phone",
        "邮箱：": "email",
        "网址：": "website",
    }

    for i, line in enumerate(lines[:60]):
        for label, field in LABEL_MAP.items():
            if line == label and i + 1 < len(lines):
                val = lines[i + 1].strip()
                # 清理尾部噪音
                val = re.sub(r"\s*更多$", "", val)           # "www.qjclouds.cn更多" → "www.qjclouds.cn"
                val = re.sub(r"\s*更多电话.*$", "", val)
                val = re.sub(r"\s*获取更多邮箱.*$", "", val)
                if val and not val.startswith("更多") and not val.startswith("获取"):
                    result[field] = val
                break

    return result


def parse_top_tags(text: str) -> dict:
    """解析详情页顶部的标签行（融资阶段、税务等级、风险统计等）。

    页面结构（innerText 前几行）:
        开业
        Pre-A轮
        A级纳税人(2025)
        自身风险45条
        司法案件26条
        涉诉关系4个
    """
    lines = _split_lines(text)
    tags = []
    stage = ""

    # 融资阶段关键词
    STAGE_KEYWORDS = [
        "未融资", "天使轮", "种子轮", "A轮", "B轮", "C轮", "D轮",
        "E轮", "F轮", "IPO", "上市", "不需要融资", "Pre-A轮",
        "Pre-A+", "A+", "B+", "C+", "D+",
    ]

    # UI 残留排除（按钮、tab 名称等）
    UI_EXCLUDES = {"风险监控", "发生变更时提醒我", "下载数据", "全屏查看", "导出"}

    for line in lines[:20]:
        # 排除 UI 元素
        if line in UI_EXCLUDES:
            continue

        # 检测融资阶段
        for s in STAGE_KEYWORDS:
            if line == s:
                stage = s
                break

        # 检测风险/税务标签（排除纯统计行如"自身风险0"）
        if any(kw in line for kw in ["纳税人", "高新技术企业", "科技型中小企业",
                                       "小微企业", "专精特新", "A级纳税人", "B级纳税人"]):
            tags.append(line)

    return {"stage": stage, "tags": tags}


def parse_products(text: str) -> list:
    """解析商品服务列表。

    页面结构:
        商品服务
        供应链商城系统 S2B供应链平台 ...
        千匠星云福利商城系统 ...
        ...
        当前企业未认领...
    """
    lines = _split_lines(text)
    products = []

    start = None
    for i, line in enumerate(lines):
        if line == "商品服务":
            # 取最后一个出现的 "商品服务"（内容区，非 tab 导航区）
            start = i + 1

    if start is None:
        return []

    skip_keywords = ["当前企业未认领", "我是企业主", "全部数据维度", "收起",
                     "基本信息", "爱企查图谱"]
    for i in range(start, min(start + 20, len(lines))):
        line = lines[i]
        if any(line.startswith(kw) for kw in skip_keywords):
            break
        if line and len(line) > 2:
            products.append(line)

    return [p for p in products if p]


def _clean_field_value(field_name: str, value: str) -> str:
    """清理字段值中的残留噪音（履历、查看地图等 DOM 残留）。"""
    if not value:
        return value

    # 通用清理：去掉尾部 "查看地图"、"查看详情" 等交互文字
    value = re.sub(r"\s*(查看地图|查看详情|全屏查看|导出|下载数据|持股详情|股权结构|立即联系企业|联系企业|发生变更时提醒我).*", "", value)

    # 字段特定清理
    cleaners = {
        "legal_person": [
            (r"^\s*[\u4e00-\u9fff]\s+", ""),  # 去掉开头单字头像缩写（"张 张宗兵" → "张宗兵"）
            (r"\s*履历.*", ""),           
            (r"\s*TA有\d+家企业.*", ""),
        ],
        "establish_date": [
            (r"\s*行政区划.*", ""),        # "2016-10-14 行政区划 上海市徐汇区" → "2016-10-14"
            (r"^(?!\d{4}-).*$", ""),        # 不以 YYYY- 开头 → 非日期，整行置空
        ],
        "registered_capital": [
            (r"\s*实缴资本.*", ""),        # "1,111.11万(元) 实缴资本 775.9104万(元)" → "1,111.11万(元)"
        ],
        "business_term": [
            (r"\s*核准日期.*", ""),        # "2016-10-14 至 2036-10-13 核准日期 ****-**-**" → 保留期限部分
        ],
        "registered_address": [
            (r"\s*查看地图.*", ""),
        ],
        "company_type": [
            (r"\s*所属行业.*", ""),        # "有限责任公司(自然人投资或控股) 所属行业 科技推广和应用服务业" → 保留类型
        ],
        "registration_number": [
            (r"\s*组织机构代码.*", ""),    # "310104000680964 组织机构代码 MA1FR5RY-3" → "310104000680964"
        ],
        "taxpayer_id": [
            (r"\s*纳税人资质.*", ""),
        ],
        "employee_count": [
            (r"\s*登记机关.*", ""),        # "35人 登记机关 徐汇区市场监督管理局" → "35人"
        ],
        "former_name": [
            (r"^\d.*$", ""),               # 以数字开头（如 "3.57143%"）→ 非曾用名，整行置空
            (r"^[%.].*$", ""),             # 以 % 或 . 开头 → 非曾用名，整行置空
            (r"^持股.*$", ""),              # "持股详情..." → 非曾用名，整行置空
        ],
        "scale": [
            (r"^[^\u4e00-\u9fff]*", ""),   # 去掉开头非中文字符（如 "S"）
            (r"\s+[A-Z]+\s*$", ""),         # 去掉尾部字母标（如 "小型 S" "微型 XS" → "小型"/"微型"）
        ],
        "phone": [
            (r"\s*更多电话.*$", ""),
            (r"\s*获取更多.*$", ""),
        ],
        "email": [
            (r"\s*更多$", ""),
            (r"\s*获取更多邮箱.*$", ""),
        ],
        "website": [
            (r"\s*更多$", ""),
            (r"\s*获取更多.*$", ""),
            (r"^暂无网址$", ""),            # "暂无网址" → 空
        ],
        "approval_date": [
            (r"^[\*-]+$", ""),             # "****-**-**" → 空
        ],
    }

    for pattern, repl in cleaners.get(field_name, []):
        value = re.sub(pattern, repl, value)

    return value.strip()


def _clean_business_info_raw(business: dict) -> dict:
    """清理 business_info_raw 原始字典。

    - description 在 "... 展开" 处截断，只保留经营范围描述
    - 删除 former_name（该字段经常被股权结构数据污染，无实际价值）
    """
    raw = dict(business)

    desc = raw.get("description", "")
    if desc:
        idx = desc.find("... 展开")
        if idx > 0:
            raw["description"] = desc[:idx]

    raw.pop("former_name", None)

    return raw


def scrape_aqc_by_credit_code(credit_code: str, cdp_port: int = CDP_PORT) -> dict:
    """通过统一社会信用代码抓取爱企查公司详情。

    Args:
        credit_code: 统一社会信用代码（如 91310104MA1FR5RY3N）
        cdp_port: Chrome CDP 端口

    Returns:
        dict: 结构化的公司工商信息
    """
    ws = CDPSession(cdp_port)
    tid, sid = create_page_session(ws, background=True)

    try:
        # 1. 导航搜索页 + 点击公司链接
        navigate_and_click_company(ws, sid, credit_code)

        # 2. 提取详情页文本
        raw = extract_page_text(ws, sid)
        text = raw.get("text", "")
        page_url = raw.get("url", "")
        page_title = raw.get("title", "")

        if not text:
            raise RuntimeError(f"详情页文本提取为空 (credit_code={credit_code})")

        # 3. 解析字段
        business = parse_aqc_business_info(text)
        company_name = parse_company_name(text, title=page_title) or business.get("企业名称", "")

        # 解析额外字段
        top_info = parse_top_tags(text)
        products = parse_products(text)
        contact_info = parse_contact_info(text)

        result = {
            "company_name": company_name,
            "credit_code": credit_code,
            "legal_person": _clean_field_value("legal_person", business.get("legal_person", "")),
            "registered_capital": _clean_field_value("registered_capital", business.get("registered_capital", "")),
            "establish_date": _clean_field_value("establish_date", business.get("establish_date", "")),
            "business_status": _clean_field_value("business_status", business.get("business_status", "")),
            "company_type": _clean_field_value("company_type", business.get("company_type", "")),
            "industry": _clean_field_value("industry", business.get("industry", "")),
            "registered_address": _clean_field_value("registered_address", business.get("registered_address", "")),
            "business_term": _clean_field_value("business_term", business.get("business_term", "")),
            "registration_authority": _clean_field_value("registration_authority", business.get("registration_authority", "")),
            "approval_date": _clean_field_value("approval_date", business.get("approval_date", "")),
            "registration_number": _clean_field_value("registration_number", business.get("registration_number", "")),
            "org_code": _clean_field_value("org_code", business.get("org_code", "")),
            "taxpayer_id": _clean_field_value("taxpayer_id", business.get("taxpayer_id", "")),
            "employee_count": _clean_field_value("employee_count", business.get("employee_count", "")),
            "former_name": _clean_field_value("former_name", business.get("former_name", "")),
            # 联系信息
            "phone": _clean_field_value("phone", contact_info.get("phone", "")),
            "email": _clean_field_value("email", contact_info.get("email", "")),
            "website": _clean_field_value("website", contact_info.get("website", "")),
            # 新增字段
            "scale": _clean_field_value("scale", business.get("scale", "")),
            "stage": top_info.get("stage", ""),
            "tags": top_info.get("tags", []),
            "products": products,
            "business_info_raw": _clean_business_info_raw(business),
            "url": page_url,
            "scraped_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        }

        return result

    finally:
        ws.send("Target.closeTarget", {"targetId": tid})
        ws.close()


# ── CLI 入口 ─────────────────────────────────────────────────────
def main():
    """CLI 入口: uv run python3 scripts/company_insight/scraper.py <credit_code> [--port 9222]"""
    if len(sys.argv) < 2:
        print("用法: python3 scripts/company_insight/scraper.py <统一社会信用代码> [--port 9222]")
        print("示例: python3 scripts/company_insight/scraper.py 91310104MA1FR5RY3N")
        sys.exit(1)

    credit_code = sys.argv[1].strip()
    cdp_port = CDP_PORT

    # 简单解析 --port 参数
    if "--port" in sys.argv:
        idx = sys.argv.index("--port")
        if idx + 1 < len(sys.argv):
            cdp_port = int(sys.argv[idx + 1])

    print(f"正在抓取爱企查: credit_code={credit_code}, port={cdp_port}")
    data = scrape_aqc_by_credit_code(credit_code, cdp_port)

    # 输出到文件
    out_path = OUTPUT_DIR / f"{credit_code}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\nSaved: {out_path}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
