"""
DataStack Compass — CVEs Router
================================

Endpoints cho CVE search, filtering, và statistics.
Query StarRocks External Catalog (minio_catalog.silver.silver_cves).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

from api.database import execute_count, execute_query, execute_query_one
from api.models.response import BaseResponse, CVEItem, PaginatedResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_SILVER_CVES = "minio_catalog.silver.silver_cves"


@router.get(
    "/",
    summary="Tìm kiếm CVEs",
    response_model=PaginatedResponse,
)
async def list_cves(
    tool_name: Optional[str] = Query(None, description="Filter theo tool"),
    severity: Optional[str] = Query(
        None, description="Filter severity: Critical, High, Medium, Low"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Lấy danh sách CVEs với filter và pagination."""
    # Build WHERE clause động
    conditions = []
    params = []

    if tool_name:
        conditions.append("tool_name = %s")
        params.append(tool_name)
    if severity:
        conditions.append("severity = %s")
        params.append(severity)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # Count
    count_sql = f"SELECT COUNT(*) AS cnt FROM {_SILVER_CVES} {where}"
    total = execute_count(count_sql, tuple(params))

    # Paginated data
    offset = (page - 1) * page_size
    sql = f"""
        SELECT cve_id, tool_name, affected_versions, fixed_in_version,
               cvss_score, severity, description, published_at
        FROM {_SILVER_CVES}
        {where}
        ORDER BY cvss_score DESC, published_at DESC
        LIMIT %s OFFSET %s
    """
    rows = execute_query(sql, tuple(params) + (page_size, offset))

    return PaginatedResponse(
        data=rows,
        total=total,
        page=page,
        page_size=page_size,
        meta={"filters": {"tool_name": tool_name, "severity": severity}},
    )


@router.get(
    "/stats",
    summary="CVE statistics tổng hợp",
    response_model=BaseResponse,
)
async def cve_stats():
    """Thống kê CVE theo severity và tool."""
    # Severity distribution
    severity_sql = f"""
        SELECT severity, COUNT(*) AS count
        FROM {_SILVER_CVES}
        GROUP BY severity
        ORDER BY FIELD(severity, 'Critical', 'High', 'Medium', 'Low')
    """
    severity_rows = execute_query(severity_sql)

    # Per-tool counts
    tool_sql = f"""
        SELECT tool_name, COUNT(*) AS total_cves,
               COUNT(CASE WHEN severity = 'Critical' THEN 1 END) AS critical,
               COUNT(CASE WHEN severity = 'High' THEN 1 END) AS high
        FROM {_SILVER_CVES}
        GROUP BY tool_name
        ORDER BY critical DESC, high DESC
    """
    tool_rows = execute_query(tool_sql)

    return BaseResponse(
        data={
            "by_severity": severity_rows,
            "by_tool": tool_rows,
        },
    )


@router.get(
    "/{cve_id}",
    summary="Chi tiết một CVE",
    response_model=BaseResponse,
)
async def get_cve(cve_id: str):
    """Lấy chi tiết một CVE theo ID."""
    sql = f"""
        SELECT cve_id, tool_name, affected_versions, fixed_in_version,
               cvss_score, severity, description, published_at
        FROM {_SILVER_CVES}
        WHERE cve_id = %s
    """
    row = execute_query_one(sql, (cve_id,))

    if row is None:
        return BaseResponse(
            data=None,
            errors=[f"CVE '{cve_id}' not found"],
        )

    cve = CVEItem(**row)
    return BaseResponse(
        data=cve.model_dump(),
        meta={"nvd_url": cve.nvd_url},
    )
