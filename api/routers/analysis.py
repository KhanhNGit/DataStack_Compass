"""
DataStack Compass — Analysis Router
====================================

Endpoints cho risk analysis: version gap analysis, breaking change impact,
và upgrade recommendations.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

from api.database import execute_query
from api.models.response import BaseResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_GOLD_SUMMARY = "minio_catalog.gold.gold_tool_summary"
_SILVER_RELEASES = "minio_catalog.silver.silver_releases"
_SILVER_CVES = "minio_catalog.silver.silver_cves"


@router.get(
    "/risk-matrix",
    summary="Risk matrix — tổng hợp rủi ro tất cả tools",
    response_model=BaseResponse,
)
async def risk_matrix():
    """Ma trận rủi ro: tool × severity. Dùng cho dashboard tổng quan."""
    sql = f"""
        SELECT
            g.tool_name,
            g.latest_version,
            g.total_cve_critical,
            g.total_cve_high,
            g.eol_date,
            CASE
                WHEN g.total_cve_critical > 0 THEN 'critical'
                WHEN g.total_cve_high > 3 THEN 'high'
                WHEN g.total_cve_high > 0 THEN 'medium'
                ELSE 'low'
            END AS risk_level
        FROM {_GOLD_SUMMARY} g
        ORDER BY g.total_cve_critical DESC, g.total_cve_high DESC
    """
    rows = execute_query(sql)

    return BaseResponse(
        data=rows,
        meta={"total_tools": len(rows)},
    )


@router.get(
    "/breaking-changes",
    summary="Breaking changes gần đây",
    response_model=BaseResponse,
)
async def recent_breaking_changes(
    tool_name: Optional[str] = Query(None, description="Filter theo tool"),
    limit: int = Query(20, ge=1, le=100),
):
    """Liệt kê releases có breaking changes, mới nhất trước."""
    where = "WHERE breaking_changes IS NOT NULL"
    params = []

    if tool_name:
        where += " AND tool_name = %s"
        params.append(tool_name)

    sql = f"""
        SELECT tool_name, version, release_date, breaking_changes
        FROM {_SILVER_RELEASES}
        {where}
        ORDER BY release_date DESC
        LIMIT %s
    """
    params.append(limit)
    rows = execute_query(sql, tuple(params))

    return BaseResponse(
        data=rows,
        meta={"total": len(rows), "filter_tool": tool_name},
    )


@router.get(
    "/upgrade-check/{tool_name}",
    summary="Kiểm tra rủi ro khi upgrade",
    response_model=BaseResponse,
)
async def upgrade_check(
    tool_name: str,
    from_version: str = Query(..., description="Version hiện tại"),
    to_version: str = Query(..., description="Version muốn upgrade tới"),
):
    """Phân tích rủi ro upgrade: CVEs, breaking changes giữa 2 versions."""
    # Breaking changes between versions
    breaking_sql = f"""
        SELECT version, breaking_changes, deprecated_apis
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s
          AND version > %s AND version <= %s
        ORDER BY version ASC
    """
    breaking_rows = execute_query(breaking_sql, (tool_name, from_version, to_version))

    # CVEs affecting the target version range
    cve_sql = f"""
        SELECT cve_id, severity, cvss_score, description, fixed_in_version
        FROM {_SILVER_CVES}
        WHERE tool_name = %s
          AND severity IN ('Critical', 'High')
        ORDER BY cvss_score DESC
        LIMIT 20
    """
    cve_rows = execute_query(cve_sql, (tool_name,))

    return BaseResponse(
        data={
            "tool_name": tool_name,
            "from_version": from_version,
            "to_version": to_version,
            "breaking_changes_by_version": breaking_rows,
            "relevant_cves": cve_rows,
            "total_breaking_versions": len(breaking_rows),
        },
    )
