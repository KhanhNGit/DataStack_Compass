"""
DataStack Compass — Universal Search Router
============================================

API /api/v1/search?q={query}&type={all|tool|cve|version}
Chạy đồng thời 3 queries trên StarRocks qua asyncio.gather,
tổng hợp và sắp xếp theo: CVE (critical lên đầu) -> Tools -> Versions.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Query

from api.database import execute_query
from api.models.response import BaseResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# =============================================================================
# StarRocks External Catalog table references
# =============================================================================

_GOLD_SUMMARY = "minio_delta_catalog.gold.gold_tool_summary"
_SILVER_RELEASES = "minio_delta_catalog.silver.silver_releases"
_SILVER_CVES = "minio_delta_catalog.silver.silver_cves"


def _sanitize_like_input(value: str) -> str:
    """Remove LIKE special characters to prevent pattern injection."""
    return value.replace("%", "").replace("_", " ").replace(";", "").strip()


@router.get(
    "/",
    summary="Universal Search",
    response_model=BaseResponse,
)
async def universal_search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    type: str = Query("all", pattern="^(all|tool|cve|version)$", description="Filter by result type"),
):
    """
    Tìm kiếm universal kết hợp Tools, CVEs, Versions.
    Thực thi tối đa 3 câu SQL đồng thời qua connection pool.
    """
    sanitized_q = _sanitize_like_input(q)
    if not sanitized_q:
        return BaseResponse(
            data={"results": [], "total": 0, "query": q},
            meta={"type_filter": type},
        )
    like_pattern = f"%{sanitized_q}%"

    tasks = []

    # execute_query manages its own pool connection — safe for asyncio.to_thread
    def run_query(sql, params):
        return execute_query(sql, params)

    # 1. Tools query
    if type in ("all", "tool"):
        sql_tools = f"""
            SELECT tool_name, latest_version, 'tool' as result_type,
                   tool_name as display_title,
                   CONCAT('Latest: ', IFNULL(latest_version, 'N/A')) as display_subtitle
            FROM {_GOLD_SUMMARY}
            WHERE tool_name LIKE %s
            LIMIT 5
        """
        tasks.append(asyncio.to_thread(run_query, sql_tools, (like_pattern,)))
    else:
        tasks.append(asyncio.to_thread(lambda: []))

    # 2. CVEs query
    if type in ("all", "cve"):
        sql_cves = f"""
            SELECT cve_id, tool_name, severity, cvss_score, 'cve' as result_type,
                   cve_id as display_title,
                   CONCAT(tool_name, ' · CVSS ', IFNULL(CAST(cvss_score AS VARCHAR), 'N/A')) as display_subtitle
            FROM {_SILVER_CVES}
            WHERE cve_id LIKE %s OR description LIKE %s
            ORDER BY cvss_score DESC
            LIMIT 5
        """
        tasks.append(asyncio.to_thread(run_query, sql_cves, (like_pattern, like_pattern)))
    else:
        tasks.append(asyncio.to_thread(lambda: []))

    # 3. Versions query
    if type in ("all", "version"):
        sql_versions = f"""
            SELECT tool_name, version, release_date, 'version' as result_type,
                   CONCAT(tool_name, ' ', version) as display_title,
                   CAST(release_date AS VARCHAR) as display_subtitle
            FROM {_SILVER_RELEASES}
            WHERE version LIKE %s OR tool_name LIKE %s
            ORDER BY release_date DESC
            LIMIT 5
        """
        tasks.append(asyncio.to_thread(run_query, sql_versions, (like_pattern, like_pattern)))
    else:
        tasks.append(asyncio.to_thread(lambda: []))

    # Chạy song song 3 query
    results_tools, results_cves, results_versions = await asyncio.gather(*tasks)

    # Gộp kết quả theo thứ tự ưu tiên: CVE -> Tool -> Version
    all_results = []
    all_results.extend(results_cves)
    all_results.extend(results_tools)
    all_results.extend(results_versions)

    return BaseResponse(
        data={
            "results": all_results,
            "total": len(all_results),
            "query": q,
        },
        meta={"type_filter": type},
    )
