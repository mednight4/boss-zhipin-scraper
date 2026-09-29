"""BOSS 公司详情页爬虫：CDP 导航 → innerText 提取 → 结构化 JSON。"""
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

COMPANY_URL = "https://www.zhipin.com/gongsi/EXAMPLE_PLACEHOLDER.html"
OUTPUT_DIR = PROJECT_ROOT / "data"
CDP_PORT = 9222


# ── 文本提取 ────────────────────────────────────────────────────────
def extract_page_text(ws, sid, url: str, scroll_rounds: int = 8) -> dict:
    """导航到 URL 并提取 innerText。"""
    ws.send("Page.navigate", {"url": url}, sid)
    time.sleep(random.uniform(5, 8))

    for _ in range(scroll_rounds):
        ws.eval_js(f"window.scrollBy(0, {random.randint(200, 600)})", sid)
        time.sleep(random.uniform(0.8, 1.8))
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


# ── 文本解析 ────────────────────────────────────────────────────────
def _clean(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", text or "").strip()


def _split_lines(text: str) -> list[str]:
    return [l.strip() for l in text.splitlines() if l.strip()]


def parse_basic_info(text: str) -> dict:
    """解析公司名、融资、规模、行业。"""
    lines = _split_lines(text)

    # 公司名：在"收藏"之前独立出现的那行（排除导航关键词）
    company_name = ""
    skip = {"首页", "职位", "公司", "校园", "海归", "APP", "有了", "海外", "无障碍专区", "搜索", "消息", "简历", "收藏"}
    for i, line in enumerate(lines):
        if line == "收藏" and i > 0:
            candidate = lines[i - 1]
            if candidate and candidate not in skip and not candidate.isdigit():
                company_name = candidate
                break

    if not company_name:
        m = re.search(r"「(.+?)招聘」", text)
        if m:
            company_name = m.group(1)

    job_count = 0
    boss_count = 0
    for line in lines:
        m = re.search(r"(\d+)在招职位", line)
        if m:
            job_count = int(m.group(1))
        m = re.search(r"(\d+)位BOSS", line)
        if m:
            boss_count = int(m.group(1))

    combined = ""
    for line in lines:
        has_stage = any(kw in line for kw in (
            "未融资", "天使轮", "种子轮", "A轮", "B轮", "C轮", "D轮",
            "IPO", "上市", "不需要融资",
        ))
        has_scale = any(s in line for s in ("人",))
        if has_stage and has_scale and len(line) < 50:
            combined = line
            break

    stage = ""
    for s in (
        "未融资", "天使轮", "种子轮", "A轮", "B轮", "C轮", "D轮",
        "E轮", "F轮", "IPO", "上市", "不需要融资",
    ):
        if s in combined:
            stage = s
            combined = combined.replace(s, "", 1).strip()
            break

    scale = ""
    m = re.search(r"\d+-\d+人|\d+人以上|\d+人以下", combined)
    if m:
        scale = m.group(0)
        combined = combined.replace(m.group(0), "", 1).strip()

    industry = combined.strip()

    return {
        "company_name": company_name,
        "job_count": job_count,
        "boss_count": boss_count,
        "stage": stage,
        "scale": scale,
        "industry": industry,
    }


def parse_hot_jobs(text: str, default_total: int = 0) -> dict:
    """解析热招职位区块。"""
    lines = _split_lines(text)
    start = None
    for i, line in enumerate(lines):
        if line == "热招职位":
            start = i + 1
            break
    if start is None:
        return {"total": default_total, "shown": 0, "jobs": []}

    # 一线/新一线城市白名单；不匹配的统一标记为"二线城市"
    TIER1_CITIES = ("上海", "北京", "深圳", "广州", "杭州", "成都", "南京",
                     "苏州", "武汉", "重庆", "天津", "长沙", "西安")

    jobs = []
    i = start
    found_count = 0
    salary_re = re.compile(r"^\d{1,3}-\d{1,3}K(·\d{2,3}薪)?$|^\d{3}-\d{3}元/天$")
    boundary_markers = {"公司简介", "公司相册"}
    while i < len(lines):
        line = lines[i]
        if any(line.startswith(m) for m in boundary_markers):
            break
        m_count = re.search(r"(\d+)个职位", line)
        if m_count:
            found_count = int(m_count.group(1))
        if salary_re.match(line):
            job = {
                "salary": line,
                "title": lines[i + 1] if i + 1 < len(lines) else "",
                "experience": "",
                "degree": "",
                "location": "",
                "status": "",
            }
            j = i + 2
            location_set = False
            while j < len(lines):
                l = lines[j]
                if salary_re.match(l):
                    break
                if any(l.startswith(m) for m in boundary_markers):
                    break
                if l.strip() == "在线":
                    job["status"] = "在线"
                elif re.match(r"^\d+-\d+年$|^\d+年以上$", l):
                    job["experience"] = l
                elif l in ("本科", "大专", "硕士", "博士", "学历不限", "中专", "高中", "初中及以下"):
                    job["degree"] = l
                elif l.endswith("天/周") or l.endswith("个月"):
                    pass
                elif not location_set and len(l) <= 12 and not re.search(r"\d+K|元/天|在线", l):
                    if any(city in l for city in TIER1_CITIES):
                        job["location"] = l
                    else:
                        job["location"] = "二线城市"
                    location_set = True
                j += 1
            jobs.append(job)
            i = j
        else:
            i += 1

    total = found_count if found_count > 0 else default_total
    return {"total": total, "shown": len(jobs), "jobs": jobs}


def parse_description(text: str) -> dict:
    """解析公司简介和官网（取第二个"公司简介"，即真正的公司介绍）。"""
    lines = _split_lines(text)
    result = {"description": "", "website": ""}

    # 收集所有"公司简介"出现的位置
    indices = [i for i, l in enumerate(lines) if l == "公司简介"]
    # 跳过第一个（导航区的简介标题），取第二个
    for idx in indices[1:] if len(indices) > 1 else indices:
        desc_lines = []
        for j in range(idx + 1, min(idx + 30, len(lines))):
            l = lines[j]
            if l.startswith("公司官网"):
                result["website"] = l.replace("公司官网:", "").replace(
                    "公司官网：", ""
                ).strip()
                continue
            if l in ("公司相册", "展开"):
                break
            if any(kw in l for kw in ("公司", "专注", "致力于", "成立于", "业务", "领域")):
                desc_lines.append(l)
            elif desc_lines:
                desc_lines.append(l)
        if desc_lines:
            result["description"] = "\n".join(desc_lines).strip()
            # 去除开头的 "公司简介" 标题残留
            if result["description"].startswith("公司简介"):
                result["description"] = result["description"][4:].strip()
            break

    return result


def parse_products(text: str) -> list:
    """解析产品介绍区块。"""
    lines = _split_lines(text)
    start = None
    for i, line in enumerate(lines):
        if line == "产品介绍":
            start = i + 1
            break
    if start is None:
        return []

    products = []
    i = start
    while i < len(lines):
        line = lines[i]
        if line in ("工商信息", "公司地址", "工作时间及福利"):
            break
        name = line
        desc = ""
        if i + 1 < len(lines) and lines[i + 1] not in ("工商信息",):
            next_l = lines[i + 1]
            if not next_l.startswith("企业"):
                desc = next_l
                i += 1
        products.append({"name": name, "description": desc})
        i += 1
    return [p for p in products if p["name"]]


def parse_business_info(text: str) -> dict:
    """解析工商信息区块。"""
    lines = _split_lines(text)
    start = None
    for i, line in enumerate(lines):
        if "工商信息" in line:
            start = i + 1
            break
    if start is None:
        return {}

    fields = {}
    field_order = [
        "企业名称", "法定代表人", "成立时间", "企业类型", "经营状态",
        "注册资本", "注册地址", "营业期限", "所属地区", "统一社会信用代码",
        "核准日期", "曾用名", "登记机关", "所属行业", "经营范围",
    ]
    current_field = None
    current_value = []

    def flush():
        if current_field:
            fields[current_field] = _clean("\n".join(current_value))

    i = start
    while i < len(lines):
        line = lines[i]
        if "公司地址" in line and ":" not in line and len(line) < 12:
            break
        if "公司地址" == line.strip():
            break

        matched = False
        for f in field_order:
            if line.startswith(f) or line == f:
                flush()
                current_field = f
                current_value = []
                remainder = line[len(f):].strip().lstrip(":").lstrip("：").strip()
                if remainder:
                    current_value.append(remainder)
                matched = True
                break
        if not matched and current_field is not None:
            if re.match(r"^[一二三四五六七八九十、，。；（）【】\s]*$", line):
                current_value.append(line)
            elif "经营范围" == current_field:
                current_value.append(line)
            elif re.match(r"^[一般项目|无需许可|除此]", line):
                current_value.append(line)
            elif line == "-":
                current_value.append(line)
            elif re.match(r"^[\u4e00-\u9fff\d]", line) and not any(
                line.startswith(f) for f in field_order
            ):
                current_value.append(line)
        i += 1
    flush()
    return fields


BENEFIT_KEYWORDS = [
    "五险一金", "六险一金",
    "补充医疗", "补充医疗保险", "补充医保",
    "交通补助", "交通补贴",
    "餐补", "餐费补贴", "饭补",
    "通讯补贴", "通讯补助",
    "生日福利", "节日福利",
    "团建聚餐", "团建", "员工旅游",
    "股票期权", "年终奖", "年终奖金",
    "定期体检", "免费体检",
    "加班补助", "加班补贴",
    "零食下午茶", "下午茶",
    "免费班车", "班车",
    "带薪年假", "全勤奖",
    "租房补贴", "住房补贴",
    "弹性工作", "双休", "法定假日",
    "带薪病假", "产假", "婚假",
]


def parse_work_benefits(text: str) -> dict:
    """解析工作时间和福利。"""
    lines = _split_lines(text)
    result = {"address": "", "work_hours": "", "work_type": "", "benefits": []}

    for i, line in enumerate(lines):
        if line == "公司地址":
            for j in range(i + 1, min(i + 5, len(lines))):
                l = lines[j]
                if l.startswith("点击查看地图"):
                    continue
                if "工作时间及福利" in l:
                    continue
                result["address"] = l
                break
        if "工作时间及福利" in line:
            for j in range(i + 1, min(i + 15, len(lines))):
                l = lines[j]
                if re.match(r"^[上中下下午]+[:：]?\d{2}:\d{2}", l) or re.match(
                    r"^\d{2}:\d{2}", l
                ):
                    result["work_hours"] = l
                elif "休" in l or "弹性" in l:
                    result["work_type"] = l
                else:
                    # 包含匹配：从一行中提取所有福利关键词
                    found = [kw for kw in BENEFIT_KEYWORDS if kw in l]
                    if found:
                        result["benefits"].extend(found)
            break

    # 去重保留顺序
    result["benefits"] = list(dict.fromkeys(result["benefits"]))
    return result


def parse_recruiters(text: str) -> list:
    """解析底部 HR 招聘列表（不拆分 name/title，保留完整名字）。"""
    lines = _split_lines(text)
    recruiters = []
    for i, line in enumerate(lines):
        if line.startswith("正在招聘"):
            if i > 0:
                name = lines[i - 1]
                title = ""
                cleaned = line.replace("正在招聘", "").strip().strip("等职位").strip()
                job_quote = re.sub(r'^[\s"\u201c\u201d]+|[\s"\u201c\u201d]+$', '', cleaned).strip()
                recruiters.append({"name": name, "title": title, "active_job": job_quote})
    return recruiters


def parse_executives(text: str) -> list:
    """解析高管介绍区块（不一定存在）。"""
    lines = _split_lines(text)
    start = None
    for i, line in enumerate(lines):
        if line in ("高管介绍", "创始人介绍", "核心团队"):
            start = i + 1
            break
    if start is None:
        return []

    executives = []
    i = start
    boundary = {"公司简介", "工商信息", "产品介绍", "公司相册", "工作时间及福利", "热招职位"}
    title_kw = ("CEO", "CTO", "CFO", "COO", "创始人", "总经理", "总裁", "董事长",
                "合伙人", "副总裁", "总监", "负责人")
    while i < len(lines):
        line = lines[i]
        if line in boundary:
            break
        if not line:
            i += 1
            continue

        name = line
        title = ""
        # 同行内嵌职位，如 "CEO黄步添"
        m = re.match(r"^([A-Z]+)[\s　]*(.+)$", line)
        if m and m.group(1) in ("CEO", "CTO", "CFO", "COO"):
            title = m.group(1)
            name = m.group(2).strip()
        elif i + 1 < len(lines):
            next_l = lines[i + 1]
            if any(kw in next_l for kw in title_kw):
                title = next_l
                i += 1

        executives.append({"name": name, "title": title})
        i += 1

    return [e for e in executives if e["name"]]


# ── 主流程 ───────────────────────────────────────────────────────────
def scrape_company_detail(url: str = COMPANY_URL, cdp_port: int = CDP_PORT) -> dict:
    """抓取公司详情页并返回结构化数据。"""
    ws = CDPSession(cdp_port)
    tid, sid = create_page_session(ws, background=True)

    try:
        raw = extract_page_text(ws, sid, url)
        text = raw.get("text", "")
        page_url = raw.get("url", url)

        basic = parse_basic_info(text)
        result = {**basic}
        result["hot_jobs"] = parse_hot_jobs(text, default_total=basic["job_count"])

        desc_info = parse_description(text)
        result["description"] = desc_info["description"]
        result["website"] = desc_info["website"]
        result["products"] = parse_products(text)
        result["business_info"] = parse_business_info(text)
        wb = parse_work_benefits(text)
        result["address"] = wb["address"]
        result["work_hours"] = wb["work_hours"]
        result["work_type"] = wb["work_type"]
        result["benefits"] = wb["benefits"]
        result["recruiters"] = parse_recruiters(text)
        result["executives"] = parse_executives(text)
        result["url"] = page_url
        result["scraped_at"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

        # 用 URL 中的 brand_id 推断输出文件名
        m = re.search(r"gongsi/([a-zA-Z0-9_~.\-]+)\.html", page_url)
        if not m:
            m = re.search(r"gongsi/([a-zA-Z0-9_~.\-]+)", page_url)
        result["brand_id"] = m.group(1) if m else ""

        return result
    finally:
        ws.send("Target.closeTarget", {"targetId": tid})
        ws.close()


def main():
    url = sys.argv[1] if len(sys.argv) > 1 else COMPANY_URL
    data = scrape_company_detail(url)

    brand_id = data.get("brand_id", "unknown")
    out_path = OUTPUT_DIR / f"{brand_id}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved: {out_path}")
    print(json.dumps(data, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
