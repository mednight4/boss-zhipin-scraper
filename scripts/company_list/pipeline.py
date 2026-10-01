"""分阶段管道编排 — 列表爬取 → DB 导入 → 详情爬取 → DB 导入 → 洞察爬取 → DB 导入."""

import argparse
import json
import os
import glob
import re
import sqlite3
import sys
from datetime import datetime

from scripts.company_list.db import (
    JobDatabase,
    build_query_url,
    compute_query_hash,
    QUERY_DIR,
    COMPANY_DIR,
    OUTPUT_DIR,
)

INSIGHT_DIR = os.path.join(OUTPUT_DIR, "insight")


def step1_scrape_list(keyword, city_code, filters, scrape_list_fn, output_path=None):
    """Step 1: 爬取列表 → 保存 JSON → 返回 json_path."""
    from scripts.boss_cdp_raw import resolve_city

    _, city_code = resolve_city(city_code)
    query_filters = {k: v for k, v in filters.items() if not k.startswith("_")}
    if output_path is None:
        os.makedirs(QUERY_DIR, exist_ok=True)
        query_url = build_query_url(keyword, city_code, query_filters)
        query_hash = compute_query_hash(query_url)
        output_path = os.path.join(QUERY_DIR, f"{query_hash}.json")

    result = scrape_list_fn(
        keyword=keyword,
        city_input=city_code,
        max_pages=filters.get("_max_pages", 3),
        filters=query_filters,
        output_path=output_path,
    )
    return output_path, result


def step2_import_list(db, json_path):
    """Step 2: 从 JSON 导入列表到 DB."""
    return db.import_list_from_json(json_path)


def step3_scrape_details(db, scrape_detail_fn, detail_json_dir=None):
    """Step 3: 扫描 DB → 逐公司爬取详情 → 保存 JSON → 返回 json_paths.

    命中验证码/安全校验页时抛 SecurityCheckError 并中止整轮，交人工处理。
    这一点很关键：验证页文本同样能被解析成一份「几乎全空」的详情，若照旧写入
    DB 并置 has_detail=1，就会变成静默污染——状态入口显示已完成，实际没有数据。
    """
    from scripts.boss_cdp_raw import SecurityCheckError

    if detail_json_dir is None:
        detail_json_dir = COMPANY_DIR
    os.makedirs(detail_json_dir, exist_ok=True)

    # 上次中断时已落盘、但尚未入库的详情 JSON 优先恢复；仅剩余待办会触发页面访问。
    recovered = step4_import_details(db, detail_json_dir=detail_json_dir)
    brands = db.get_pending_detail_brands()
    imported = recovered
    for brand in brands:
        brand_id = brand["encrypt_brand_id"]
        company_link = brand["company_link"]
        if not brand_id or not company_link:
            continue
        label = brand.get("company_name") or brand_id
        json_path = os.path.join(detail_json_dir, f"{brand_id}.json")
        try:
            detail = scrape_detail_fn(company_link)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(detail, f, ensure_ascii=False, indent=2)
            db.import_detail_from_json(json_path, brand_id)
            db.mark_detail_done(brand_id)
            imported += 1
            print(f"详情抓取成功 [{label}]: {brand_id}", flush=True)
        except SecurityCheckError as e:
            # 验证码/安全校验：中止整轮。已完成的进度已入库，人工处理后重跑续做
            print(f"\n🛑 {e}", flush=True)
            print(
                f"   已中止本轮详情抓取（已完成 {imported} 家）。"
                f"人工完成验证后重跑同一命令即可续做。",
                flush=True,
            )
            raise
        except (OSError, sqlite3.Error, json.JSONDecodeError, TypeError,
                ValueError, AttributeError, RuntimeError) as e:
            print(f"详情爬取失败 [{label}]: {e}", flush=True)
            continue
    return imported


def step4_import_details(db, json_paths=None, detail_json_dir=None):
    """导入当前详情待办的 JSON；显式 json_paths 可覆盖默认待办范围。"""
    if json_paths is None:
        if detail_json_dir is None:
            detail_json_dir = COMPANY_DIR
        json_paths = [
            (os.path.join(detail_json_dir, f"{brand['encrypt_brand_id']}.json"),
             brand["encrypt_brand_id"])
            for brand in db.get_pending_detail_brands()
        ]

    imported = 0
    for json_path, brand_id in json_paths:
        if not os.path.exists(json_path):
            continue
        try:
            db.import_detail_from_json(json_path, brand_id)
            db.mark_detail_done(brand_id)
            imported += 1
        except (OSError, sqlite3.Error, json.JSONDecodeError, TypeError,
                ValueError, AttributeError) as e:
            print(f"详情 JSON 导入失败 [{brand_id}]: {e}", flush=True)
    return imported


def step5_scrape_insights(db, scrape_insight_fn, insight_json_dir=None, delay_range=(15, 25)):
    """Step 5: 扫描 DB 中待跑洞察的公司 → 企查查抓取 → 保存 JSON → 导入 DB → 更新 has_insight.

    两种中断恢复行为：
    - JSON 已存在但 has_insight 仍为 0（上次导入失败/进程被杀）：直接补导入，不重抓。
    - 命中验证码/风控页：抛 InsightBlockedError 中止整轮，交人工处理，不继续下一家。

    Args:
        db: JobDatabase 实例
        scrape_insight_fn: 洞察抓取函数, 签名 fn(credit_code, cdp_port) -> dict
        insight_json_dir: JSON 输出目录
        delay_range: 每次抓取前的随机延迟范围(秒), 默认 15-25s

    Returns:
        int: 成功抓取的公司数
    """
    from scripts.company_insight.scraper import InsightBlockedError, insight_json_path

    if insight_json_dir is None:
        insight_json_dir = INSIGHT_DIR
    os.makedirs(insight_json_dir, exist_ok=True)

    brands = db.get_pending_insight_brands()
    imported = 0
    reused = 0
    skipped = 0
    for brand in brands:
        brand_id = brand["encrypt_brand_id"]
        credit_code = brand.get("credit_code", "")
        company_name = brand.get("company_name", "")
        label = company_name or brand_id

        # 没有 credit_code 无法查爱企查, 跳过
        if not credit_code:
            print(f"跳过 [{label}]: 缺少 credit_code", flush=True)
            skipped += 1
            continue

        json_path = str(insight_json_path(credit_code, insight_json_dir))
        reusable_path = json_path if os.path.exists(json_path) else None
        if reusable_path is None:
            # 兼容历史 `{credit_code}.json` / `{brand_id}.json` 命名；
            # 先用内容或文件名反查信用代码，避免 step6 之前重复访问页面。
            for candidate in glob.glob(os.path.join(insight_json_dir, "*.json")):
                candidate_code = insight_file_credit_code(os.path.basename(candidate))
                if candidate_code is None:
                    candidate_code = read_credit_code_from_json(candidate)
                if candidate_code == credit_code:
                    reusable_path = candidate
                    break

        # JSON 已落盘但 has_insight 仍未闭环：复用结果补导入，不重抓。
        if reusable_path:
            try:
                db.import_insight_from_json(reusable_path, brand_id)
                db.mark_insight_done(brand_id)
                reused += 1
                print(f"洞察补导入 [{label}]: 复用 {os.path.basename(reusable_path)}", flush=True)
                continue
            except (json.JSONDecodeError, OSError, sqlite3.Error, TypeError,
                    ValueError, AttributeError) as e:
                print(f"已有 JSON 无法导入, 将重抓 [{label}]: {e}", flush=True)

        try:
            data = scrape_insight_fn(credit_code)
        except InsightBlockedError as e:
            # 风控/验证码：中止整轮, 已完成的进度已入库, 人工处理后可重跑续做
            print(f"\n🛑 {e}", flush=True)
            print(
                f"   已中止本轮洞察抓取（已完成 {imported} 家 + 补导入 {reused} 家）。"
                f"人工完成验证后重跑同一命令即可续做。",
                flush=True,
            )
            raise
        except Exception as e:
            print(f"洞察爬取失败 [{label}]: {e}", flush=True)
            continue

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            db.import_insight_from_json(json_path, brand_id)
            db.mark_insight_done(brand_id)
        except (OSError, sqlite3.Error, json.JSONDecodeError, TypeError,
                ValueError, AttributeError) as e:
            print(f"洞察入库失败 [{label}]: {e}", flush=True)
            continue

        imported += 1
        print(f"洞察抓取成功 [{label}]: {credit_code}", flush=True)

    if skipped:
        print(f"洞察跳过: {skipped} 个公司 (无 credit_code)", flush=True)
    if reused:
        print(f"洞察补导入: {reused} 个公司 (复用已有 JSON, 未重新抓取)", flush=True)

    # 导入后校验：检查是否有不完整数据
    total, incomplete_count, _ = db.validate_insight_completeness()
    if incomplete_count > 0:
        print(f"⚠️ 警告: company_insight 表中 {incomplete_count}/{total} 行存在空字段", flush=True)

    return imported + reused


def step6_import_insights(db, json_paths=None, insight_json_dir=None):
    """补导入洞察 JSON；损坏、孤儿和已完成文件分别记录并跳过。"""
    if json_paths is None:
        if insight_json_dir is None:
            insight_json_dir = INSIGHT_DIR
        if not os.path.isdir(insight_json_dir):
            return 0

        pending = db.get_pending_insight_brands()
        if not pending:
            return 0
        pending_by_code = {
            str(brand.get("credit_code") or "").strip(): brand["encrypt_brand_id"]
            for brand in pending
            if str(brand.get("credit_code") or "").strip()
        }
        json_paths = []
        for fp in glob.glob(os.path.join(insight_json_dir, "*.json")):
            filename = os.path.basename(fp)
            credit_code = insight_file_credit_code(filename)
            if credit_code is None:
                credit_code = read_credit_code_from_json(fp)
            brand_id = pending_by_code.get(credit_code)
            if brand_id:
                json_paths.append((fp, brand_id))
            elif credit_code:
                resolved = db.resolve_brand_id_by_credit_code(credit_code)
                if resolved:
                    print(f"洞察 JSON 对应公司不在当前待办状态 [{filename}]，跳过", flush=True)
                else:
                    print(f"洞察 JSON 无法反查 brand_id [{filename}]，跳过", flush=True)
            else:
                print(f"洞察 JSON 无法解析 credit_code [{filename}]，跳过", flush=True)

    # 显式路径也只导入仍未完成的 brand，避免重复文件覆盖已完成状态。
    pending_ids = {
        brand["encrypt_brand_id"] for brand in db.get_pending_insight_brands()
    }
    imported = 0
    for json_path, brand_id in json_paths:
        if not os.path.exists(json_path):
            continue
        if brand_id not in pending_ids:
            continue
        try:
            db.import_insight_from_json(json_path, brand_id)
            db.mark_insight_done(brand_id)
            pending_ids.discard(brand_id)
            imported += 1
        except (OSError, sqlite3.Error, json.JSONDecodeError, TypeError,
                ValueError, AttributeError) as e:
            print(f"洞察 JSON 导入失败 [{brand_id}] ({os.path.basename(json_path)}): {e}", flush=True)
    return imported


def run_full_pipeline(keyword, city_code, filters, scrape_list_fn, scrape_detail_fn, scrape_insight_fn=None):
    """完整管道: step1 → step2 → step3 → step4 → step5(可选)."""
    db = JobDatabase()
    db.connect()
    db.init_schema()

    try:
        print("=== Step 1: 列表爬取 ===")
        json_path, _ = step1_scrape_list(keyword, city_code, filters, scrape_list_fn)
        print(f"列表已保存: {json_path}")

        print("=== Step 2: 导入列表到 DB ===")
        inserted, skipped = step2_import_list(db, json_path)
        print(f"导入职位: {inserted} 新增, {skipped} 跳过")

        print("=== Step 3: 详情爬取 ===")
        imported = step3_scrape_details(db, scrape_detail_fn)
        print(f"爬取详情: {imported} 个公司")

        print("=== Step 4: 兜底导入残留 JSON ===")
        detail_imported = step4_import_details(db)
        print(f"兜底导入: {detail_imported} 个公司")

        # Step 5: 企查查洞察 (可选)
        if scrape_insight_fn:
            print("=== Step 5: 企查查洞察 ===")
            insight_imported = step5_scrape_insights(db, scrape_insight_fn)
            print(f"洞察抓取: {insight_imported} 个公司")

            print("=== Step 6: 兜底导入残留洞察 JSON ===")
            insight_fallback = step6_import_insights(db)
            print(f"兜底导入: {insight_fallback} 个公司")

        stats = db.get_stats()
        print(f"\n统计: {stats['total_jobs']} 职位, {stats['unique_companies']} 公司, "
              f"{stats['done_detail']} 详情已完成, {stats['pending_detail']} 待爬详情, "
              f"{stats['done_insight']} 洞察已完成, {stats['pending_insight']} 待爬洞察")
    finally:
        db.close()


def run_insight_pipeline(scrape_insight_fn, db_path=None):
    """独立运行企查查洞察管道 (不重新跑 step1-4).

    Args:
        scrape_insight_fn: 洞察抓取函数 fn(credit_code) -> dict
        db_path: 自定义 DB 路径

    Returns:
        int: 成功抓取的公司数
    """
    db = JobDatabase(db_path)
    db.connect()
    db.init_schema()
    try:
        print("=== 企查查洞察管道 ===")
        imported = step5_scrape_insights(db, scrape_insight_fn)
        fallback = step6_import_insights(db, insight_json_dir=INSIGHT_DIR)
        stats = db.get_stats()
        print(f"\n洞察导入: {imported + fallback} 个公司 (补导入 {fallback})")
        print(f"统计: {stats['done_insight']} 已完成, {stats['pending_insight']} 待爬")
        return imported + fallback
    finally:
        db.close()

FRESHNESS_HOURS = int(os.environ.get("BOSS_QUERY_FRESHNESS_HOURS", "24"))


# ── PipelineState 状态机 ──────────────────────────────────────

class PipelineState:
    """管道状态机；步骤完成始终从数据库重新读取，不依赖内存日志状态。"""

    def __init__(self, query_url: str, db=None, query_hash=None):
        self.query_url = self._canonical_query_url(query_url)
        self.query_hash = query_hash or compute_query_hash(self.query_url)
        self.db = db or JobDatabase()
        self.db.connect()
        self.db.init_schema()
        self._load_state()

    @staticmethod
    def _canonical_query_url(query_url):
        """将 BOSS 查询 URL 规范化为稳定参数顺序和解析后的城市码。"""
        from urllib.parse import parse_qs, urlparse

        parsed = urlparse(query_url)
        hostname = parsed.hostname or ""
        if hostname != "zhipin.com" and not hostname.endswith(".zhipin.com"):
            return query_url
        params = parse_qs(parsed.query)
        keyword = params.get("query", [""])[0]
        city_input = params.get("city", [""])[0]
        if not city_input:
            return query_url
        from scripts.boss_cdp_raw import resolve_city
        _, city_code = resolve_city(city_input)
        filters = {
            key: params[key][0]
            for key in ("experience", "degree", "industry", "scale", "salary", "stage")
            if params.get(key, [""])[0]
        }
        return build_query_url(keyword, city_code, filters)

    def _load_state(self):
        """从数据库和列表 JSON 恢复当前阶段。"""
        info = self.db.get_query_info(self.query_hash)
        json_path = os.path.join(QUERY_DIR, f"{self.query_hash}.json")
        if info is None:
            self.step = "LIST_JSON_SAVED" if os.path.exists(json_path) else "IDLE"
        elif info.get("detail_pending", 0):
            self.step = "LIST_DB_IMPORTED"
        elif info.get("insight_pending", 0):
            self.step = "DETAIL_DONE"
        else:
            self.step = "COMPLETE"

    def decide(self) -> str:
        """优先恢复详情，其次检查洞察输入，最后才根据新鲜度决定跳过或刷新。"""
        info = self.db.get_query_info(self.query_hash)
        if info:
            if info.get("detail_pending", 0) > 0:
                return "RESUME_DETAIL"
            if info.get("insight_pending", 0) > 0:
                if info.get("insight_input_ready", 0) > 0:
                    return "SCRAPE_INSIGHT"
                return "INSIGHT_INPUT_MISSING"
            try:
                age = datetime.now() - datetime.fromisoformat(info["oldest_create_time"])
            except (TypeError, ValueError):
                return "RESUME_REFRESH"
            from datetime import timedelta
            return "SKIP" if age < timedelta(hours=FRESHNESS_HOURS) else "RESUME_REFRESH"

        json_path = os.path.join(QUERY_DIR, f"{self.query_hash}.json")
        return "IMPORT_LIST" if os.path.exists(json_path) else "SCRAPE_LIST"

    def _result(self, action, json_path=None, skipped_steps=None):
        """读取最终 DB 状态并构造结果；JSON 存在与否不改变待办计数。"""
        self._load_state()
        info = self.db.get_query_info(self.query_hash)
        return {
            "action": action,
            "query_hash": self.query_hash,
            "step": self.step,
            "stats": self.db.get_stats(),
            "json_path": json_path,
            "pending_detail": info["detail_pending"] if info else 0,
            "pending_insight": info["insight_pending"] if info else 0,
            "skipped_steps": list(skipped_steps or []),
        }

    def run(
        self, keyword=None, city_input=None, filters=None, max_pages=3,
        cdp_port=9222, fmt="json", detail=True, insight=True,
        scrape_detail_fn=None, scrape_insight_fn=None, insight_delay=15,
        list_json_path=None, detail_json_dir=None, insight_json_dir=None,
    ) -> dict:
        """从当前数据库/JSON 状态继续阶段，并返回真实待办与用户跳过阶段。"""
        action = self.decide()
        json_path = list_json_path or os.path.join(QUERY_DIR, f"{self.query_hash}.json")
        if action == "SCRAPE_LIST" and list_json_path and os.path.isfile(list_json_path):
            action = "IMPORT_LIST"
        decision_action = action
        if action in ("SKIP", "INSIGHT_INPUT_MISSING"):
            early_skips = ["insight"] if action == "INSIGHT_INPUT_MISSING" and not insight else []
            return self._result(
                decision_action,
                json_path if os.path.exists(json_path) else None,
                early_skips,
            )

        if action in ("SCRAPE_LIST", "RESUME_REFRESH") and (not keyword or not city_input):
            raise ValueError("列表抓取或刷新需要 keyword 和 city_input")

        if action == "RESUME_REFRESH":
            self._cleanup_for_refresh()
            action = "SCRAPE_LIST"

        skipped = []
        if action == "SCRAPE_LIST":
            json_path = self._step_scrape_list(
                keyword, city_input, filters, max_pages, cdp_port, fmt
            )
            self._step_import_list(json_path)
        elif action == "IMPORT_LIST":
            self._step_import_list(json_path)
        elif action not in ("RESUME_DETAIL", "SCRAPE_INSIGHT"):
            return self._result(decision_action, json_path if os.path.exists(json_path) else None)

        if action != "SCRAPE_INSIGHT":
            if detail:
                self._step_scrape_details(
                    cdp_port, scrape_detail_fn=scrape_detail_fn,
                    detail_json_dir=detail_json_dir,
                )
            else:
                skipped.append("detail")

        info = self.db.get_query_info(self.query_hash)
        if insight and info and info.get("detail_pending", 0) == 0 and info.get("insight_pending", 0) > 0:
            if scrape_insight_fn is None:
                scrape_insight_fn = _insight_fn_factory(cdp_port, insight_delay)
            self._step_scrape_insights(scrape_insight_fn, insight_json_dir)
        elif not insight:
            skipped.append("insight")
        elif not detail and info and info.get("detail_pending", 0) > 0:
            skipped.append("insight")

        return self._result(decision_action, json_path, skipped)

    def _cleanup_for_refresh(self):
        """过期刷新只删除当前列表批次，再从规范列表 JSON 路径抓取。"""
        self.db.delete_query(self.query_hash)
        self.step = "IDLE"

    def _step_scrape_list(self, keyword, city_input, filters, max_pages, cdp_port, fmt):
        """按当前 query_hash 保存规范化列表 JSON。"""
        from scripts.boss_cdp_raw import resolve_city, scrape_list

        filters = filters or {}
        _, city_code = resolve_city(city_input)
        query_url = build_query_url(keyword, city_code, filters)
        if compute_query_hash(query_url) != self.query_hash:
            raise ValueError(
                "抓取参数生成的 query_hash 与 PipelineState 不一致；"
                "请传入同一查询的规范 URL、keyword、city 和 filters。"
            )
        os.makedirs(QUERY_DIR, exist_ok=True)
        json_path = os.path.join(QUERY_DIR, f"{self.query_hash}.json")
        print(f"=== 列表抓取: {keyword} @ {city_input} ===")
        scrape_list(
            keyword, city_code, max_pages, filters, json_path,
            cdp_port=cdp_port, fmt=fmt,
        )
        self.step = "LIST_JSON_SAVED"
        return json_path

    def _step_import_list(self, json_path=None):
        """导入当前批次 JSON，并拒绝不同批次的 JSON 文件。"""
        if json_path is None:
            json_path = os.path.join(QUERY_DIR, f"{self.query_hash}.json")
        identity = _query_identity_from_list_json(json_path)
        if identity["query_hash"] != self.query_hash:
            raise ValueError(
                "列表 JSON 的 query_hash 与 PipelineState 不一致: "
                f"{identity['query_hash']} != {self.query_hash}"
            )
        inserted, skipped = self.db.import_list_from_json(json_path)
        info = self.db.get_query_info(self.query_hash)
        if info is None:
            raise ValueError(
                f"列表 JSON 已导入，但 query_hash 不属于当前 PipelineState: {json_path}"
            )
        print(f"导入列表: {inserted} 新增, {skipped} 跳过")
        self.step = "LIST_DB_IMPORTED"

    def _step_scrape_details(self, cdp_port, scrape_detail_fn=None, detail_json_dir=None):
        """先补导入残留 JSON，再抓取并逐家公司入库。"""
        return step3_scrape_details(
            self.db,
            scrape_detail_fn or _detail_fn_factory(cdp_port),
            detail_json_dir=detail_json_dir,
        )

    def _step_import_details(self, detail_json_dir=None):
        """只为当前数据库待办补导入详情 JSON。"""
        return step4_import_details(self.db, detail_json_dir=detail_json_dir)

    def _step_scrape_insights(self, scrape_insight_fn, insight_json_dir=None):
        """抓取/补导入洞察，并对残留文件执行逐文件兜底。"""
        target_dir = insight_json_dir or INSIGHT_DIR
        imported = step5_scrape_insights(self.db, scrape_insight_fn, target_dir)
        fallback = step6_import_insights(self.db, insight_json_dir=target_dir)
        print(f"insight sync: {imported} (兜底+{fallback}) / {imported + fallback} companies")
        self.step = "INSIGHT_DONE"


# ── 模块级便捷函数 ──────────────────────────────────────────────

def query(query_url: str, db_path=None, **kwargs) -> dict:
    """一键入口：自动决策并推进流程，关闭前先读取最终数据库结果。"""
    db = JobDatabase(db_path)
    try:
        pipe = PipelineState(query_url, db=db)
        return pipe.run(**kwargs)
    finally:
        db.close()


# ── 状态盘点 ────────────────────────────────────────────────────
# 洞察 JSON 的文件名与 credit_code 映射规则，print_status 与清理工具共用。
CREDIT_CODE_RE = re.compile(r"^[0-9A-Z]{18}$")
INSIGHT_FILENAME_PREFIX = "aqc_"


def insight_file_credit_code(filename):
    """从洞察 JSON 文件名推断 credit_code；推断不出（如 brand_id 命名）返回 None。"""
    stem = filename[:-5] if filename.endswith(".json") else filename
    if stem.startswith(INSIGHT_FILENAME_PREFIX):
        stem = stem[len(INSIGHT_FILENAME_PREFIX):]
    return stem if CREDIT_CODE_RE.match(stem) else None


def read_credit_code_from_json(path):
    """读取 JSON 内容里的 credit_code 字段。

    用于反查 brand_id 命名的历史文件（文件名本身不含 credit_code），
    否则这类重复抓取在盘点上会隐形。
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    credit_code = str(data.get("credit_code") or "").strip()
    return credit_code if CREDIT_CODE_RE.match(credit_code) else None


def classify_insight_files(insight_dir, resolve_brand_id):
    """盘点 output/insight 下的文件，暴露命名漂移、孤儿与重复抓取。

    分类：
    - canonical: `aqc_{credit_code}.json` 且 credit_code 能反查到当前批次的 brand_id
    - orphan:    `aqc_{credit_code}.json` 但反查不到 brand_id（不在当前批次内）
    - legacy:    非 `aqc_` 前缀命名（历史 `{credit_code}.json` / `{brand_id}.json`）
    - duplicates: 同一 credit_code 对应多个文件（重复抓取留下的冗余）
    - unreadable: 无法解析出 credit_code 的文件（损坏或非洞察 JSON）

    文件名不含 credit_code 时回读 JSON 内容里的 credit_code，保证重复抓取不隐形。

    Args:
        insight_dir: 洞察 JSON 目录
        resolve_brand_id: callable(credit_code) -> brand_id 或 None

    Returns:
        dict: {"canonical", "orphan", "legacy", "duplicates", "unreadable", "total"}
    """
    canonical, orphan, legacy, unreadable = [], [], [], []
    by_credit_code = {}

    if not os.path.isdir(insight_dir):
        return {
            "canonical": canonical, "orphan": orphan, "legacy": legacy,
            "duplicates": {}, "unreadable": unreadable, "total": 0,
        }

    for name in sorted(os.listdir(insight_dir)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(insight_dir, name)
        credit_code = insight_file_credit_code(name)
        is_canonical_name = name.startswith(INSIGHT_FILENAME_PREFIX)

        if credit_code is None:
            # 文件名不含 credit_code：回读内容，识别 brand_id 命名的历史文件
            credit_code = read_credit_code_from_json(path)

        if credit_code is None:
            unreadable.append(name)
            continue

        by_credit_code.setdefault(credit_code, []).append(name)

        if is_canonical_name:
            if resolve_brand_id(credit_code):
                canonical.append(name)
            else:
                orphan.append(name)
        else:
            legacy.append(name)

    duplicates = {cc: names for cc, names in by_credit_code.items() if len(names) > 1}
    total = len(canonical) + len(orphan) + len(legacy) + len(unreadable)
    return {
        "canonical": canonical,
        "orphan": orphan,
        "legacy": legacy,
        "duplicates": duplicates,
        "unreadable": unreadable,
        "total": total,
    }


def _print_name_list(title, names, limit=20):
    """打印名称清单，超过 limit 只显示前 limit 条并提示剩余数量。"""
    if not names:
        return
    print(f"\n{title} ({len(names)})")
    for name in names[:limit]:
        print(f"  - {name}")
    if len(names) > limit:
        print(f"  ... 还有 {len(names) - limit} 家")


def print_status(db_path=None, insight_json_dir=None):
    """打印批次进度、待办清单与 JSON/DB 对账 —— 唯一的「现在到哪一步」入口。

    涵盖原来靠自建 check_*.py 才能回答的全部问题：哪些公司查过了、有数据吗、
    什么时候查的、还需要重新查吗、磁盘上的 JSON 有没有重复或孤儿。
    不要另写脚本查状态，用 `--step status`。
    """
    db = JobDatabase(db_path)
    db.connect()
    db.init_schema()
    try:
        stats = db.get_stats()
        queries = db.get_all_query_hashes()

        print("=" * 78)
        print("  BOSS 抓取管道状态")
        print("=" * 78)

        # ── 1. 批次概览 ──────────────────────────────────────────
        print("\n[1] 查询批次")
        if not queries:
            print("  暂无查询批次（还没跑过列表抓取）")
        else:
            print(f"  {'query_hash':<18}{'keyword':<16}{'city':<10}{'jobs':>6}  {'最早入库':<20}")
            print("  " + "-" * 74)
            for q in queries:
                print(f"  {q['query_hash']:<18}{(q['keyword'] or ''):<16}"
                      f"{(q['city'] or ''):<10}{q['job_count']:>6}  "
                      f"{(q['oldest_create_time'] or '')[:19]:<20}")

        # ── 2. 总体统计 ──────────────────────────────────────────
        print("\n[2] 总体进度")
        print(f"  职位            : {stats['total_jobs']}")
        print(f"  唯一公司        : {stats['unique_companies']}")
        print(f"  详情 已完成/待爬: {stats['done_detail']} / {stats['pending_detail']}")
        print(f"  洞察 已完成/待爬: {stats['done_insight']} / {stats['pending_insight']}")

        # ── 3. 待爬详情 ──────────────────────────────────────────
        pending_detail = db.get_pending_detail_brands()
        _print_name_list(
            "[3] 待爬详情（has_detail 未完成或 company_detail 行缺失）",
            [b["encrypt_brand_id"] for b in pending_detail],
        )
        if not pending_detail:
            print("\n[3] 待爬详情: 无")

        # ── 4. 待爬洞察（含阻塞原因）────────────────────────────
        pending_insight = db.get_pending_insight_brands()
        print(f"\n[4] 待爬洞察（has_detail=1 且洞察记录或 has_insight 未完成）: {len(pending_insight)} 家")
        blocked = []
        runnable = []
        for brand in pending_insight:
            label = brand.get("company_name") or brand["encrypt_brand_id"]
            credit_code = (brand.get("credit_code") or "").strip()
            if credit_code:
                runnable.append(f"{label} | {credit_code}")
            else:
                blocked.append(f"{label} | brand_id={brand['encrypt_brand_id']}")
        for line in runnable[:20]:
            print(f"  - {line}")
        if len(runnable) > 20:
            print(f"  ... 还有 {len(runnable) - 20} 家")
        if blocked:
            print(f"\n  ⚠️ 其中 {len(blocked)} 家缺 credit_code，无法查爱企查（需先补详情）:")
            for line in blocked[:10]:
                print(f"    ! {line}")

        # ── 5. 洞察 JSON 与 DB 对账 ─────────────────────────────
        if insight_json_dir is None:
            insight_json_dir = INSIGHT_DIR
        print(f"\n[5] 洞察 JSON 对账 ({insight_json_dir})")
        inventory = classify_insight_files(
            insight_json_dir, db.resolve_brand_id_by_credit_code
        )
        if inventory["total"] == 0:
            print("  目录不存在或没有 JSON（还没抓过洞察）")
        else:
            print(f"  JSON 文件总数     : {inventory['total']}")
            print(f"  规范命名          : {len(inventory['canonical'])}  (aqc_{{credit_code}}.json)")
            print(f"  孤儿（不在批次内）: {len(inventory['orphan'])}")
            print(f"  旧命名            : {len(inventory['legacy'])}")
            print(f"  无法解析          : {len(inventory['unreadable'])}")
            print(f"  重复 credit_code  : {len(inventory['duplicates'])}")
            _print_name_list("  孤儿文件（不在当前批次，可安全删除）", inventory["orphan"], limit=10)
            _print_name_list("  旧命名文件（规范版已存在即可删除）", inventory["legacy"], limit=10)
            _print_name_list("  无法解析文件（建议人工确认后删除）", inventory["unreadable"], limit=10)
            if inventory["duplicates"]:
                print(f"\n  重复抓取明细（同一公司多份文件，保留 aqc_ 版本即可）:")
                for credit_code, names in sorted(inventory["duplicates"].items())[:10]:
                    print(f"    {credit_code}: {', '.join(names)}")
                if len(inventory["duplicates"]) > 10:
                    print(f"    ... 还有 {len(inventory['duplicates']) - 10} 组")

        # ── 6. 最近抓取时间 ─────────────────────────────────────
        recent = db.get_recent_insight_scrapes(limit=5)
        if recent:
            print("\n[6] 最近入库的洞察")
            for row in recent:
                print(f"  {(row['scraped_at'] or '')[:19]}  "
                      f"{row['company_name'] or row['brand_id']}  ({row['credit_code']})")

        print("\n" + "=" * 78)
    finally:
        db.close()


# ── CLI 入口 ──────────────────────────────────────────────────────

def _insight_fn_factory(cdp_port: int = 9222, delay: float = 15):
    """创建 insight 抓取函数，绑定 cdp_port 和 delay 参数。"""
    def _fn(credit_code: str):
        from scripts.company_insight.scraper import scrape_aqc_by_credit_code
        return scrape_aqc_by_credit_code(credit_code, cdp_port=cdp_port, delay=delay)
    return _fn


def _detail_fn_factory(cdp_port: int = 9222):
    """创建 detail 抓取函数，绑定 cdp_port 参数。"""
    def _fn(company_link: str):
        from scripts.company_detail.extractor import scrape_company_detail
        return scrape_company_detail(company_link, cdp_port=cdp_port)
    return _fn


def _query_identity_from_list_json(json_path):
    """读取已有列表 JSON 的批次身份，兼容没有 query 元数据的旧文件。"""
    from urllib.parse import parse_qs, urlparse

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("列表 JSON 必须是对象")

    keyword = str(data.get("keyword") or "")
    city = str(data.get("city") or "")
    filters = data.get("filters") or {}
    if not isinstance(filters, dict):
        raise ValueError("列表 JSON 的 filters 必须是对象")
    query_url = str(data.get("query_url") or "").strip()
    query_hash = str(data.get("query_hash") or "").strip()
    city_code = str(data.get("city_code") or "").strip()
    if query_url:
        actual_hash = compute_query_hash(query_url)
        if query_hash and query_hash != actual_hash:
            raise ValueError("列表 JSON 的 query_hash 与 query_url 不一致")
        if not city_code:
            city_code = parse_qs(urlparse(query_url).query).get("city", [""])[0]
    if not city_code:
        city_code = city
    if not city_code:
        raise ValueError("列表 JSON 缺少可恢复的 city_code/city")
    from scripts.boss_cdp_raw import resolve_city
    _, city_code = resolve_city(city_code)
    canonical_url = build_query_url(keyword, city_code, filters)
    if query_url and query_url != canonical_url:
        raise ValueError("列表 JSON 的 query_url 与 keyword/city_code/filters 不一致")
    query_url = canonical_url
    query_hash = compute_query_hash(query_url)

    return {
        "keyword": keyword,
        "city": city_code or city,
        "filters": filters,
        "query_url": query_url,
        "query_hash": query_hash,
    }


def main():
    """CLI 入口: python -m scripts.company_list.pipeline --step <list|detail|insight|all|status>"""
    parser = argparse.ArgumentParser(
        description="BOSS直聘管道编排器 — 分阶段抓取列表/详情/企查查洞察"
    )
    parser.add_argument(
        "--step",
        choices=["list", "detail", "insight", "all", "status"],
        default="status",
        help="执行步骤: list=列表导入, detail=详情抓取, insight=企查查洞察, all=全部, status=查看状态"
    )
    parser.add_argument("--port", type=int, default=9222, help="Chrome CDP 端口 (默认 9222)")
    parser.add_argument("--db-path", type=str, default=None, help="SQLite 数据库路径 (默认 output/jobs.db)")
    parser.add_argument("--list-json", type=str, default=None, help="已有列表 JSON；list 导入，all 从此文件继续")
    parser.add_argument("--detail-json-dir", type=str, default=None, help="详情 JSON 目录；优先补导入目录中当前待办文件")
    parser.add_argument("--keyword", type=str, default=None, help="--step all 的列表关键词")
    parser.add_argument("--city", type=str, default=None, help="--step all 的城市名或 9 位城市码")
    parser.add_argument("--pages", type=int, default=3, help="--step all 的列表抓取页数")
    for filter_name in ("scale", "stage", "salary", "experience", "degree", "industry"):
        parser.add_argument(f"--{filter_name}", default=None, help=f"列表筛选代码 ({filter_name})")
    parser.add_argument(
        "--insight-delay", type=float, default=15,
        help="洞察抓取间隔基准秒数 (实际为 delay±5s, 最低5s)"
    )

    args = parser.parse_args()

    # 行缓冲：被 agent 当子进程调用时输出不被块缓冲，进度实时可见
    from scripts.boss_cdp_raw import CityResolutionError, SecurityCheckError, enable_line_buffering
    from scripts.company_insight.scraper import InsightBlockedError
    enable_line_buffering()

    if args.step == "status":
        print_status(db_path=args.db_path)
        return

    if args.step == "insight":
        try:
            imported = run_insight_pipeline(
                scrape_insight_fn=_insight_fn_factory(args.port, args.insight_delay),
                db_path=args.db_path,
            )
        except InsightBlockedError as e:
            print(f"\n🛑 {e}")
            print("   已中止本轮；人工完成验证后重跑同一命令即可续做。")
            sys.exit(2)
        print(f"\n洞察处理结束: 本轮导入 {imported} 家；请以数据库待办数确认是否全部完成。")
        return

    if args.step == "detail":
        db = JobDatabase(args.db_path)
        db.connect()
        db.init_schema()
        try:
            imported = step3_scrape_details(
                db, _detail_fn_factory(args.port), detail_json_dir=args.detail_json_dir
            )
            print(f"\n详情处理结束: 本轮导入 {imported} 家；请以数据库待办数确认剩余工作。")
        except SecurityCheckError as e:
            print(f"\n🛑 {e}")
            print("   已中止本轮；人工完成验证后重跑同一命令即可续做。")
            sys.exit(2)
        finally:
            db.close()
        return

    if args.step == "list":
        if not args.list_json:
            print("错误: --step list 需要指定 --list-json <path>")
            sys.exit(1)
        db = JobDatabase(args.db_path)
        db.connect()
        db.init_schema()
        try:
            inserted, skipped = step2_import_list(db, args.list_json)
            print(f"\n列表导入完成: {inserted} 新增, {skipped} 跳过")
        finally:
            db.close()
        return

    if args.step == "all":
        if args.list_json:
            try:
                identity = _query_identity_from_list_json(args.list_json)
            except (OSError, json.JSONDecodeError, ValueError) as e:
                print(f"错误: 无法从列表 JSON 恢复查询批次: {e}")
                sys.exit(1)
        else:
            if not args.keyword or not args.city:
                print("错误: --step all 需要 --list-json，或同时提供 --keyword 与 --city")
                sys.exit(1)
            from scripts.boss_cdp_raw import resolve_city
            try:
                _, city_code = resolve_city(args.city)
            except CityResolutionError as e:
                print(f"错误: {e}")
                sys.exit(1)
            filters = {
                name: getattr(args, name)
                for name in ("scale", "stage", "salary", "experience", "degree", "industry")
                if getattr(args, name)
            }
            query_url = build_query_url(args.keyword, city_code, filters)
            identity = {
                "keyword": args.keyword,
                "city": city_code,
                "filters": filters,
                "query_url": query_url,
                "query_hash": compute_query_hash(query_url),
            }

        db = JobDatabase(args.db_path)
        db.connect()
        db.init_schema()
        pipe = PipelineState(identity["query_url"], db=db, query_hash=identity["query_hash"])
        try:
            result = pipe.run(
                keyword=identity["keyword"],
                city_input=identity["city"],
                filters=identity["filters"],
                max_pages=args.pages,
                cdp_port=args.port,
                detail=True,
                insight=True,
                scrape_detail_fn=_detail_fn_factory(args.port),
                scrape_insight_fn=_insight_fn_factory(args.port, args.insight_delay),
                list_json_path=args.list_json,
                detail_json_dir=args.detail_json_dir,
            )
        except SecurityCheckError as e:
            print(f"\n🛑 {e}")
            print("   已中止本轮；人工完成验证后重跑同一命令即可续做。")
            sys.exit(2)
        except InsightBlockedError as e:
            print(f"\n🛑 {e}")
            print("   已中止本轮；人工完成验证后重跑同一命令即可续做。")
            sys.exit(2)
        finally:
            db.close()
        print(f"\n完整管道结束: {result['step']}")
        print(f"真实待办: detail={result['pending_detail']}, insight={result['pending_insight']}")
        print(f"统计: {result['stats']}")
        return


if __name__ == "__main__":
    main()
