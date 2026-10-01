"""已入库公司/职位的只读筛选查询入口。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys

from scripts.company_list.db import DEFAULT_DB_PATH, JobDatabase, compute_query_hash


def positive_int(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("必须是整数") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("必须是正整数")
    return value


def non_negative_int(raw):
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("必须是整数") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("必须是非负整数")
    return value


def build_arg_parser():
    parser = argparse.ArgumentParser(
        description="只读筛选已入库的 BOSS 职位及爱企查参保人数"
    )
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH, help="SQLite 数据库路径")
    batch_group = parser.add_mutually_exclusive_group(required=False)
    batch_group.add_argument("--query-hash", help="查询批次 hash")
    batch_group.add_argument("--query-url", help="规范化 BOSS 查询 URL")
    parser.add_argument("--list-batches", action="store_true", help="只读列出现有批次及筛选条件")
    parser.add_argument("--employee-min", type=non_negative_int, help="参保人数下限（包含）")
    parser.add_argument("--employee-max", type=non_negative_int, help="参保人数上限（包含）")
    parser.add_argument("--limit", type=positive_int, default=100, help="最多返回职位记录数")
    parser.add_argument("--offset", type=non_negative_int, default=0, help="跳过的职位记录数")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def _load_filters(raw):
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {"原始值": raw}
    return value if isinstance(value, dict) else {"原始值": value}


def resolve_query_hash(args):
    if args.query_url:
        return compute_query_hash(args.query_url)
    return args.query_hash


def build_payload(db, args):
    """读取一个批次并返回可序列化结果；不执行任何数据库写操作。"""
    batch = db.get_query_batch_info(args.query_hash)
    if batch is None:
        raise LookupError(f"未找到查询批次: {args.query_hash}")
    if (
        args.employee_min is not None
        and args.employee_max is not None
        and args.employee_min > args.employee_max
    ):
        raise ValueError("employee-min 不能大于 employee-max")

    total = db.count_jobs_by_employee_count(
        args.query_hash, args.employee_min, args.employee_max
    )
    rows = db.query_jobs_by_employee_count(
        args.query_hash,
        args.employee_min,
        args.employee_max,
        limit=args.limit,
        offset=args.offset,
    )
    batch["filters"] = _load_filters(batch.pop("filters_json", ""))
    return {
        "query": {
            "query_hash": args.query_hash,
            "employee_min": args.employee_min,
            "employee_max": args.employee_max,
            "inclusive": True,
            "limit": args.limit,
            "offset": args.offset,
        },
        "batch": batch,
        "matched_job_count": total,
        "returned_job_count": len(rows),
        "jobs": rows,
    }


def _markdown_link(label, url):
    return f"[{label}]({url})" if url else "未提供"


def format_text(payload):
    query = payload["query"]
    batch = payload["batch"]
    lower = query["employee_min"]
    upper = query["employee_max"]
    if lower is None and upper is None:
        range_text = "未限定"
    elif lower is None:
        range_text = f"≤ {upper} 人"
    elif upper is None:
        range_text = f"≥ {lower} 人"
    else:
        range_text = f"{lower}–{upper} 人（含边界）"

    lines = [
        "已完成数据库只读查询",
        f"查询批次: {query['query_hash']}",
        f"关键词/搜索城市: {batch.get('keyword') or '未记录'} / {batch.get('city') or '未记录'}",
        f"原始 BOSS 筛选: {json.dumps(batch.get('filters', {}), ensure_ascii=False)}",
        f"职位记录数: {batch.get('job_count', 0)}；参保人数条件: {range_text}",
        f"命中职位记录: {payload['matched_job_count']}；本页返回: {payload['returned_job_count']}",
        f"详情完成: {batch.get('detail_done', 0)}；详情待办: {batch.get('detail_pending', 0)}；洞察完成: {batch.get('insight_done', 0)}；洞察待办: {batch.get('insight_pending', 0)}",
    ]
    for index, row in enumerate(payload["jobs"], start=query["offset"] + 1):
        company = row.get("boss_company_name") or row.get("insight_company_name") or "未提供公司名"
        employee_count = row.get("employee_count")
        employee_text = f"{employee_count} 人" if employee_count is not None else "未披露"
        lines.extend([
            "",
            f"{index}. {company} | {row.get('title') or '未提供职位标题'} | 参保人数: {employee_text}",
            f"   BOSS职位: {_markdown_link('打开职位', row.get('job_link'))}",
            f"   BOSS公司: {_markdown_link('打开公司详情', row.get('boss_detail_url') or row.get('company_link'))}",
            f"   爱企查: {_markdown_link('打开爱企查详情', row.get('aiqicha_url'))}",
            f"   工作地点: {row.get('location') or '未提供'} | 洞察时间: {row.get('insight_scraped_at') or '未记录'}",
        ])
    if not payload["jobs"]:
        lines.extend(["", "没有匹配的已入库职位记录；这不代表该批次没有抓取结果。"])
    return "\n".join(lines)


def _format_batches_text(batches):
    if not batches:
        return "没有已入库的查询批次。"
    lines = ["已入库查询批次（只读）"]
    for batch in batches:
        lines.extend([
            "",
            f"批次: {batch.get('query_hash')}",
            f"关键词/搜索城市: {batch.get('keyword') or '未记录'} / {batch.get('city') or '未记录'}",
            f"筛选: {json.dumps(batch.get('filters', {}), ensure_ascii=False)}",
            f"职位记录: {batch.get('job_count', 0)}；BOSS 公司键数: {batch.get('company_count', 0)}",
            f"详情完成: {batch.get('detail_done', 0)}；详情待办: {batch.get('detail_pending', 0)}；洞察待办: {batch.get('insight_pending', 0)}",
            f"列表时间: {batch.get('scraped_at') or batch.get('oldest_create_time') or '未记录'}",
        ])
    return "\n".join(lines)


def main(argv=None):
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.list_batches and (args.query_hash or args.query_url):
        parser.error("--list-batches 不能与 --query-hash/--query-url 同时使用")
    if not args.list_batches and not (args.query_hash or args.query_url):
        parser.error("必须提供 --list-batches、--query-hash 或 --query-url")
    args.query_hash = resolve_query_hash(args)
    db = JobDatabase(args.db_path, read_only=True)
    try:
        if args.list_batches:
            batches = db.list_query_batch_summaries()
            for batch in batches:
                batch["filters"] = _load_filters(batch.pop("filters_json", ""))
            if args.format == "json":
                print(json.dumps({"batches": batches}, ensure_ascii=False, indent=2))
            else:
                print(_format_batches_text(batches))
            return 0
        payload = build_payload(db, args)
    except (FileNotFoundError, LookupError, ValueError, RuntimeError, sqlite3.Error) as exc:
        print(f"查询失败: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_text(payload))
    return 0


if __name__ == "__main__":
    sys.exit(main())
