"""分阶段管道编排 — 列表爬取 → DB 导入 → 详情爬取 → DB 导入."""

import json
import os
import glob
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
    if output_path is None:
        os.makedirs(QUERY_DIR, exist_ok=True)
        query_url = build_query_url(keyword, city_code, filters)
        query_hash = compute_query_hash(query_url)
        output_path = os.path.join(QUERY_DIR, f"{query_hash}.json")

    city_name = city_code
    result = scrape_list_fn(
        keyword=keyword,
        city_input=city_code,
        max_pages=filters.get("_max_pages", 3),
        filters={k: v for k, v in filters.items() if not k.startswith("_")},
        output_path=output_path,
    )
    return output_path, result


def step2_import_list(db, json_path):
    """Step 2: 从 JSON 导入列表到 DB."""
    return db.import_list_from_json(json_path)


def step3_scrape_details(db, scrape_detail_fn, detail_json_dir=None):
    """Step 3: 扫描 DB → 逐公司爬取详情 → 保存 JSON → 返回 json_paths."""
    if detail_json_dir is None:
        detail_json_dir = COMPANY_DIR
    os.makedirs(detail_json_dir, exist_ok=True)

    brands = db.get_pending_detail_brands()
    imported = 0
    for brand in brands:
        brand_id = brand["encrypt_brand_id"]
        company_link = brand["company_link"]
        if not brand_id or not company_link:
            continue
        json_path = os.path.join(detail_json_dir, f"{brand_id}.json")
        try:
            detail = scrape_detail_fn(company_link)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(detail, f, ensure_ascii=False, indent=2)
            db.import_detail_from_json(json_path, brand_id)
            db.mark_detail_done(brand_id)
            imported += 1
        except Exception as e:
            print(f"详情爬取失败 [{brand_id}]: {e}")
            continue
    return imported


def step4_import_details(db, json_paths=None, detail_json_dir=None):
    """Step 4: 从 JSON 导入详情到 DB → 更新 has_detail."""
    if json_paths is None:
        if detail_json_dir is None:
            detail_json_dir = COMPANY_DIR
        json_paths = []
        for fp in glob.glob(os.path.join(detail_json_dir, "*.json")):
            brand_id = os.path.basename(fp).replace(".json", "")
            json_paths.append((fp, brand_id))

    imported = 0
    for json_path, brand_id in json_paths:
        if not os.path.exists(json_path):
            continue
        db.import_detail_from_json(json_path, brand_id)
        db.mark_detail_done(brand_id)
        imported += 1
    return imported


def step5_scrape_insights(db, scrape_insight_fn, insight_json_dir=None, delay_range=(15, 25)):
    """Step 5: 扫描 DB 中待跑洞察的公司 → 企查查抓取 → 保存 JSON → 导入 DB.

    Args:
        db: JobDatabase 实例
        scrape_insight_fn: 洞察抓取函数, 签名 fn(credit_code, cdp_port) -> dict
        insight_json_dir: JSON 输出目录
        delay_range: 每次抓取前的随机延迟范围(秒), 默认 15-25s

    Returns:
        int: 成功抓取的公司数
    """
    if insight_json_dir is None:
        insight_json_dir = INSIGHT_DIR
    os.makedirs(insight_json_dir, exist_ok=True)

    brands = db.get_pending_insight_brands()
    imported = 0
    skipped = 0
    for brand in brands:
        brand_id = brand["encrypt_brand_id"]
        credit_code = brand.get("credit_code", "")
        company_name = brand.get("company_name", "")

        # 没有 credit_code 无法查爱企查, 跳过
        if not credit_code:
            print(f"跳过 [{company_name or brand_id}]: 缺少 credit_code")
            skipped += 1
            continue

        json_path = os.path.join(insight_json_dir, f"aqc_{credit_code}.json")
        try:
            data = scrape_insight_fn(credit_code)
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            db.import_insight_from_json(json_path, brand_id)
            db.mark_insight_done(brand_id)
            imported += 1
            print(f"洞察抓取成功 [{company_name or brand_id}]: {credit_code}")
        except Exception as e:
            print(f"洞察爬取失败 [{company_name or brand_id}]: {e}")
            continue

    if skipped:
        print(f"洞察跳过: {skipped} 个公司 (无 credit_code)")
    return imported


def run_full_pipeline(keyword, city_code, filters, scrape_list_fn, scrape_detail_fn, scrape_insight_fn=None):
    """完整管道: step1 → step2 → step3 → step4 → step5(可选)."""
    db = JobDatabase()
    db.connect()
    db.init_schema()

    try:
        print("=== Step 1: 列表爬取 ===")
        json_path, result = step1_scrape_list(keyword, city_code, filters, scrape_list_fn)
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
        stats = db.get_stats()
        print(f"\n洞察抓取: {imported} 个公司")
        print(f"统计: {stats['done_insight']} 已完成, {stats['pending_insight']} 待爬")
        return imported
    finally:
        db.close()

FRESHNESS_HOURS = int(os.environ.get("BOSS_QUERY_FRESHNESS_HOURS", "24"))


# ── PipelineState 状态机 ──────────────────────────────────────

class PipelineState:
    """管道状态机 — 统一决策入口。

    用法:
        pipe = PipelineState(query_url="https://...", db=db)
        action = pipe.decide()
        if action != "SKIP":
            result = pipe.run(keyword="AI Agent", city_input="上海")
    """

    def __init__(self, query_url: str, db=None, query_hash=None):
        self.query_url = query_url
        self.query_hash = query_hash or compute_query_hash(query_url)
        self.db = db or JobDatabase()
        self.db.connect()
        self.db.init_schema()
        self._load_state()

    def _load_state(self):
        """从 DB 和文件系统恢复当前状态。"""
        info = self.db.get_query_info(self.query_hash)
        json_path = os.path.join(QUERY_DIR, f"{self.query_hash}.json")

        if info is None:
            if os.path.exists(json_path):
                self.step = "LIST_JSON_SAVED"
            else:
                self.step = "IDLE"
        elif info["detail_pending"] == 0:
            # 详情全部完成, 检查洞察进度
            if info.get("insight_pending", 0) and info["insight_pending"] > 0:
                self.step = "DETAIL_DONE"
            else:
                self.step = "COMPLETE"
        else:
            self.step = "LIST_DB_IMPORTED"

    def decide(self) -> str:
        """决策下一步动作：SKIP / IMPORT_LIST / SCRAPE_LIST / RESUME_REFRESH / SCRAPE_INSIGHT"""
        info = self.db.get_query_info(self.query_hash)
        if info:
            age = datetime.now() - datetime.fromisoformat(info["oldest_create_time"])
            from datetime import timedelta
            if age < timedelta(hours=FRESHNESS_HOURS):
                # 数据新鲜, 但检查是否还有未完成的洞察
                if info["insight_pending"] > 0:
                    return "SCRAPE_INSIGHT"
                return "SKIP"
            else:
                return "RESUME_REFRESH"
        json_path = os.path.join(QUERY_DIR, f"{self.query_hash}.json")
        if os.path.exists(json_path):
            return "IMPORT_LIST"
        return "SCRAPE_LIST"

    def run(self, keyword=None, city_input=None, filters=None,
            max_pages=3, cdp_port=9222, fmt="json", detail=True, insight=True,
            scrape_insight_fn=None) -> dict:
        """推进管线到 COMPLETE，根据 self.step 自动跳过已完成步骤。

        Args:
            detail: 是否执行详情抓取（step3-4）。False 时跳过。
            insight: 是否执行企查查洞察抓取（step5）。False 时跳过。
            scrape_insight_fn: 洞察抓取函数 fn(credit_code) -> dict

        Returns: {action, query_hash, step, stats, json_path, detail_count}
        """
        action = self.decide()
        if action == "SKIP":
            return {"action": action, "query_hash": self.query_hash, "step": self.step,
                    "stats": self.db.get_stats()}

        if action == "RESUME_REFRESH":
            self._cleanup_for_refresh()

        # SCRAPE_INSIGHT: 跳过 step1-4, 直接执行 step5
        if action != "SCRAPE_INSIGHT":
            if self.step in ("IDLE", "LIST_JSON_SAVED"):
                self._step_scrape_list(keyword, city_input, filters, max_pages, cdp_port, fmt)

            if self.step in ("LIST_JSON_SAVED",):
                self._step_import_list()

            if detail:
                if self.step in ("LIST_DB_IMPORTED",):
                    self._step_scrape_details(cdp_port)
                    self._step_import_details()
            else:
                # detail=False: 跳过 step3-4，标记为完成
                if self.step == "LIST_DB_IMPORTED":
                    self.step = "DETAIL_DONE"

        # Step 5: 企查查洞察
        if insight and scrape_insight_fn:
            if self.step in ("DETAIL_DONE", "COMPLETE"):
                self._step_scrape_insights(scrape_insight_fn)
                self.step = "COMPLETE"
        else:
            if self.step == "DETAIL_DONE":
                self.step = "COMPLETE"

        return {"action": action, "query_hash": self.query_hash, "step": self.step,
                "stats": self.db.get_stats()}

    def _cleanup_for_refresh(self):
        """过期刷新：删除旧数据，重置到 IDLE。"""
        self.db.delete_query(self.query_hash)
        self.step = "IDLE"

    def _step_scrape_list(self, keyword, city_input, filters, max_pages, cdp_port, fmt):
        """列表爬取 → 保存 JSON。"""
        from scripts.boss_cdp_raw import scrape_list
        os.makedirs(QUERY_DIR, exist_ok=True)
        city_name, city_code = city_input, city_input
        query_url = build_query_url(keyword, city_code, filters or {})
        query_hash = compute_query_hash(query_url)
        json_path = os.path.join(QUERY_DIR, f"{query_hash}.json")

        print(f"=== 列表抓取: {keyword} @ {city_input} ===")
        result = scrape_list(
            keyword, city_input, max_pages, filters or {}, json_path,
            cdp_port=cdp_port, fmt=fmt,
        )
        self.step = "LIST_JSON_SAVED"
        return json_path

    def _step_import_list(self, json_path=None):
        """导入 JSON → company_list。"""
        if json_path is None:
            json_path = os.path.join(QUERY_DIR, f"{self.query_hash}.json")
        inserted, skipped = self.db.import_list_from_json(json_path)
        print(f"导入列表: {inserted} 新增, {skipped} 跳过")
        self.step = "LIST_DB_IMPORTED"

    def _step_scrape_details(self, cdp_port):
        """扫描 has_detail=0 → 爬取详情 → 保存 JSON。"""
        from scripts.company_detail.extractor import scrape_company_detail
        brands = self.db.get_pending_detail_brands()
        os.makedirs(COMPANY_DIR, exist_ok=True)
        imported = 0
        for brand in brands:
            brand_id = brand["encrypt_brand_id"]
            company_link = brand["company_link"]
            if not brand_id or not company_link:
                continue
            json_path = os.path.join(COMPANY_DIR, f"{brand_id}.json")
            try:
                detail = scrape_company_detail(company_link, cdp_port=cdp_port)
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(detail, f, ensure_ascii=False, indent=2)
                self.db.import_detail_from_json(json_path, brand_id)
                self.db.mark_detail_done(brand_id)
                imported += 1
            except Exception as e:
                print(f"详情爬取失败 [{brand_id}]: {e}")
        print(f"detail sync: " + str(imported) + "/" + str(len(brands)) + " company")

    def _step_import_details(self):
        """导入详情 JSON → company_detail → 更新 has_detail=1。"""
        import glob as glob_mod
        for fp in glob_mod.glob(os.path.join(COMPANY_DIR, "*.json")):
            brand_id = os.path.basename(fp).replace(".json", "")
            self.db.import_detail_from_json(fp, brand_id)
            self.db.mark_detail_done(brand_id)
        self.step = "DETAIL_DONE"

    def _step_scrape_insights(self, scrape_insight_fn):
        """扫描待洞察公司 → 企查查抓取 → 导入 DB。"""
        imported = step5_scrape_insights(self.db, scrape_insight_fn, INSIGHT_DIR)
        print(f"insight sync: {imported} companies")


# ── 模块级便捷函数 ──────────────────────────────────────────────

def query(query_url: str, **kwargs) -> dict:
    """一键入口：给 URL → 得到结果。
    自动决定跳/查/恢复，返回 {action, query_hash, stats}。
    """
    pipe = PipelineState(query_url)
    action = pipe.decide()
    if action == "SKIP":
        info = pipe.db.get_query_info(pipe.query_hash)
        pipe.db.close()
        return {"action": action, "query_hash": pipe.query_hash, "stats": pipe.db.get_stats()}
    result = pipe.run(**kwargs)
    pipe.db.close()
    return result


def print_status():
    """打印所有查询批次状态。"""
    db = JobDatabase()
    db.connect()
    db.init_schema()
    try:
        queries = db.get_all_query_hashes()
        if not queries:
            print("暂无查询批次")
            return
        print(f"{'query_hash':<18} {'keyword':<15} {'city':<8} {'jobs':>6} {'created_at':<22}")
        print("-" * 75)
        for q in queries:
            print(f"{q['query_hash']:<18} {q['keyword'] or '':<15} {q['city'] or '':<8} "
                  f"{q['job_count']:>6} {q['oldest_create_time'] or '':<22}")
    finally:
        db.close()
