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
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")


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
    json_paths = []
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
            json_paths.append((json_path, brand_id))
        except Exception as e:
            print(f"详情爬取失败 [{brand_id}]: {e}")
            continue
    return json_paths


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


def run_full_pipeline(keyword, city_code, filters, scrape_list_fn, scrape_detail_fn):
    """完整管道: step1 → step2 → step3 → step4."""
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
        json_paths = step3_scrape_details(db, scrape_detail_fn)
        print(f"爬取详情: {len(json_paths)} 个公司")

        print("=== Step 4: 导入详情到 DB ===")
        detail_imported = step4_import_details(db, json_paths)
        print(f"导入详情: {detail_imported} 个公司")

        stats = db.get_stats()
        print(f"\n统计: {stats['total_jobs']} 职位, {stats['unique_companies']} 公司, "
              f"{stats['done_detail']} 详情已完成, {stats['pending_detail']} 待爬详情")
    finally:
        db.close()
