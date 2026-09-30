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

`pipeline` 的导出走模块级 `__getattr__` 惰性转发，不在导入包时立刻执行。
原因：`python -m scripts.company_list.pipeline` 会先导入包再以 `__main__` 执行
`pipeline` 模块，若包在导入时就把它塞进 `sys.modules`，runpy 会打
「found in sys.modules after import of package ... may result in unpredictable
behaviour」的 RuntimeWarning——而 `--step status` 现在是推荐的第一入口，
这条警告会误导使用者。
"""

from scripts.company_list.db import (
    JobDatabase,
    build_query_url,
    compute_query_hash,
    DEFAULT_DB_PATH,
    QUERY_DIR,
    COMPANY_DIR,
)

_LAZY_PIPELINE_EXPORTS = frozenset({
    "step1_scrape_list",
    "step2_import_list",
    "step3_scrape_details",
    "step4_import_details",
    "run_full_pipeline",
    "PipelineState",
    "query",
    "print_status",
    "FRESHNESS_HOURS",
})

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


def __getattr__(name):
    """惰性转发 `pipeline` 的导出（PEP 562），保持 `from scripts.company_list import X` 可用。"""
    if name in _LAZY_PIPELINE_EXPORTS:
        from scripts.company_list import pipeline

        return getattr(pipeline, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(__all__)
