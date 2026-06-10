"""
DataStack Compass — Tools Router
=================================

Endpoints cho tool summary, release history, và version details.
Query StarRocks External Catalog (minio_catalog.gold / minio_catalog.silver).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query

from api.database import execute_count, execute_query, execute_query_one
from api.models.response import (
    BaseResponse,
    PaginatedResponse,
    ReleaseDetail,
    ToolSummary,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# =============================================================================
# StarRocks catalog/table paths — đọc từ External Catalog
# Syntax: minio_catalog.{database}.{table}
# Fallback: truy cập trực tiếp nếu catalog chưa cấu hình
# =============================================================================

_GOLD_SUMMARY = "minio_catalog.gold.gold_tool_summary"
_SILVER_RELEASES = "minio_catalog.silver.silver_releases"


@router.get(
    "/",
    summary="Danh sách tất cả tools",
    response_model=PaginatedResponse,
)
async def list_tools(
    page: int = Query(1, ge=1, description="Trang hiện tại"),
    page_size: int = Query(20, ge=1, le=100, description="Items mỗi trang"),
    severity: Optional[str] = Query(
        None, description="Filter theo risk level: critical, high, medium, low"
    ),
):
    """Lấy danh sách tools với summary từ Gold layer."""
    # Count total
    count_sql = f"SELECT COUNT(*) AS cnt FROM {_GOLD_SUMMARY}"
    total = execute_count(count_sql)

    # Paginated query — StarRocks supports LIMIT/OFFSET
    offset = (page - 1) * page_size
    sql = f"""
        SELECT tool_name, latest_version, eol_date, eos_date,
               total_cve_critical, total_cve_high, last_updated
        FROM {_GOLD_SUMMARY}
        ORDER BY total_cve_critical DESC, total_cve_high DESC, tool_name ASC
        LIMIT %s OFFSET %s
    """
    rows = execute_query(sql, (page_size, offset))

    tools = [ToolSummary(**row) for row in rows]

    # Filter by severity nếu cần (in-memory vì số lượng nhỏ)
    if severity:
        tools = [t for t in tools if t.risk_level == severity.lower()]

    return PaginatedResponse(
        data=[t.model_dump() for t in tools],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{tool_name}",
    summary="Chi tiết một tool",
    response_model=BaseResponse,
)
async def get_tool(tool_name: str):
    """Lấy thông tin tổng hợp của một tool từ Gold layer."""
    sql = f"""
        SELECT tool_name, latest_version, eol_date, eos_date,
               total_cve_critical, total_cve_high, last_updated
        FROM {_GOLD_SUMMARY}
        WHERE tool_name = %s
    """
    row = execute_query_one(sql, (tool_name,))

    if row is None:
        return BaseResponse(
            data=None,
            meta={"tool_name": tool_name},
            errors=[f"Tool '{tool_name}' not found"],
        )

    tool = ToolSummary(**row)
    return BaseResponse(
        data=tool.model_dump(),
        meta={"risk_level": tool.risk_level},
    )


@router.get(
    "/{tool_name}/releases",
    summary="Release history của một tool",
    response_model=PaginatedResponse,
)
async def list_releases(
    tool_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Lấy lịch sử releases từ Silver layer, sorted by version (mới nhất trước)."""
    count_sql = f"""
        SELECT COUNT(*) AS cnt FROM {_SILVER_RELEASES}
        WHERE tool_name = %s
    """
    total = execute_count(count_sql, (tool_name,))

    offset = (page - 1) * page_size
    sql = f"""
        SELECT tool_name, version, release_date,
               breaking_changes, deprecated_apis, processed_at
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s
        ORDER BY release_date DESC
        LIMIT %s OFFSET %s
    """
    rows = execute_query(sql, (tool_name, page_size, offset))

    return PaginatedResponse(
        data=rows,
        total=total,
        page=page,
        page_size=page_size,
        meta={"tool_name": tool_name},
    )


@router.get(
    "/{tool_name}/releases/{version}",
    summary="Chi tiết một release version",
    response_model=BaseResponse,
)
async def get_release(tool_name: str, version: str):
    """Lấy chi tiết một release cụ thể."""
    sql = f"""
        SELECT tool_name, version, release_date,
               breaking_changes, deprecated_apis, processed_at
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s AND version = %s
    """
    row = execute_query_one(sql, (tool_name, version))

    if row is None:
        return BaseResponse(
            data=None,
            errors=[f"Release {tool_name}@{version} not found"],
        )

    return BaseResponse(data=row)
