"""
DataStack Compass — Universal Search Router
============================================

API /api/v1/search?q={query}&type={all|tool|cve|version}
Chạy 3 queries tuần tự trên cùng một pool connection,
tổng hợp và sắp xếp theo: CVE (critical lên đầu) -> Tools -> Versions.
"""

from __future__ import annotations

import logging
from typing import List

from fastapi import APIRouter, Depends, Query
from pymysql.connections import Connection

from api.database import get_db
from api.models.response import BaseResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# =============================================================================
# StarRocks External Catalog table references
# =============================================================================

_GOLD_SUMMARY = "minio_iceberg_catalog.gold.gold_tool_summary"
_SILVER_RELEASES = "minio_iceberg_catalog.silver.silver_releases"
_SILVER_CVES = "minio_iceberg_catalog.silver.silver_cves"


def _sanitize_like_input(value: str) -> str:
    """Remove LIKE special characters to prevent pattern injection."""
    return value.replace("%", "").replace("_", " ").replace(";", "").strip()


def _run_query(db: Connection, sql: str, params: tuple) -> List[dict]:
    """Run a single query on the shared connection."""
    with db.cursor() as cursor:
        cursor.execute(sql, params)
        return cursor.fetchall()


@router.get(
    "/",
    summary="Universal Search",
    response_model=BaseResponse,
)
async def universal_search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query"),
    type: str = Query("all", pattern="^(all|tool|cve|version)$", description="Filter by result type"),
    db: Connection = Depends(get_db),
):
    """
    Tìm kiếm universal kết hợp Tools, CVEs, Versions.
    Runs sequentially on a single pool connection to avoid pool exhaustion.
    """
    sanitized_q = _sanitize_like_input(q)
    if not sanitized_q:
        return BaseResponse(
            data={"results": [], "total": 0, "query": q},
            meta={"type_filter": type},
        )
    like_pattern = f"%{sanitized_q}%"

    all_results = []

    # 1. CVEs query (highest priority in results)
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
        all_results.extend(_run_query(db, sql_cves, (like_pattern, like_pattern)))

    # 2. Tools query
    if type in ("all", "tool"):
        sql_tools = f"""
            SELECT tool_name, latest_version, 'tool' as result_type,
                   tool_name as display_title,
                   CONCAT('Latest: ', IFNULL(latest_version, 'N/A')) as display_subtitle
            FROM {_GOLD_SUMMARY}
            WHERE tool_name LIKE %s
            LIMIT 5
        """
        all_results.extend(_run_query(db, sql_tools, (like_pattern,)))

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
        all_results.extend(_run_query(db, sql_versions, (like_pattern, like_pattern)))

    return BaseResponse(
        data={
            "results": all_results,
            "total": len(all_results),
            "query": q,
        },
        meta={"type_filter": type},
    )

