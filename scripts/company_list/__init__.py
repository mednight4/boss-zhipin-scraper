"""BOSS Company List Scraper - 列表抓取子包.

导出:
  - JobDatabase: SQLite 三表桥接数据访问层
  - build_query_url: 构造完整查询 URL
  - compute_query_hash: 计算查询 URL 的 MD5 哈希
  - step1_scrape_list ~ step4_import_details / run_full_pipeline: 分阶段管道
  - PipelineState: 统一决策入口（状态机）
  - query: 一键入口便捷函数
  - print_status: 打印所有查询批次状态
  - FRESHNESS_HOURS: 查询结果新鲜度（小时）
"""

from scripts.company_list.db import (
    JobDatabase,
    build_query_url,
    compute_query_hash,
    DEFAULT_DB_PATH,
    QUERY_DIR,
    COMPANY_DIR,
)

from scripts.company_list.pipeline import (
    step1_scrape_list,
    step2_import_list,
    step3_scrape_details,
    step4_import_details,
    run_full_pipeline,
    PipelineState,
    query,
    print_status,
    FRESHNESS_HOURS,
)

__all__ = [
    "JobDatabase",
    "build_query_url",
    "compute_query_hash",
    "DEFAULT_DB_PATH",
    "QUERY_DIR",
    "COMPANY_DIR",
    "step1_scrape_list",
    "step2_import_list",
    "step3_scrape_details",
    "step4_import_details",
    "run_full_pipeline",
    "PipelineState",
    "query",
    "print_status",
    "FRESHNESS_HOURS",
]
