"""BOSS Company List Scraper - 列表抓取子包.

导出:
  - JobDatabase: SQLite 三表桥接数据访问层
  - build_query_url: 构造完整查询 URL
  - compute_query_hash: 计算查询 URL 的 MD5 哈希
  - DEFAULT_DB_PATH / QUERY_DIR / COMPANY_DIR: 路径常量
"""

from scripts.company_list.db import (
    JobDatabase,
    build_query_url,
    compute_query_hash,
    DEFAULT_DB_PATH,
    QUERY_DIR,
    COMPANY_DIR,
)

__all__ = [
    "JobDatabase",
    "build_query_url",
    "compute_query_hash",
    "DEFAULT_DB_PATH",
    "QUERY_DIR",
    "COMPANY_DIR",
]
