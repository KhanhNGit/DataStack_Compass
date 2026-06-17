"""
DataStack Compass — Tools Router (Tech Catalog)
=================================================

Endpoints cho Tech Catalog feature: tool summary, version history,
release details, compatibility, và full-text search.

Prefix: /api/v1/tools

Query StarRocks External Catalog:
    - minio_delta_catalog.gold.gold_tool_summary
    - minio_delta_catalog.silver.silver_releases
    - minio_delta_catalog.silver.silver_cves
    - minio_delta_catalog.silver.silver_compatibility

SQL syntax: StarRocks (MySQL-compatible).
    - %s placeholders (KHÔNG dùng $1 PostgreSQL)
    - LIMIT/OFFSET cho pagination
    - LIKE '%query%' cho full-text search
    - CASE WHEN cho computed columns
    - DATE_ADD / CURRENT_DATE() cho date arithmetic
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import get_db
from api.models.response import (
    BaseResponse,
    PaginatedResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# =============================================================================
# StarRocks External Catalog table references
# =============================================================================

_GOLD_SUMMARY = "minio_delta_catalog.gold.gold_tool_summary"
_SILVER_RELEASES = "minio_delta_catalog.silver.silver_releases"
_SILVER_CVES = "minio_delta_catalog.silver.silver_cves"
_SILVER_COMPAT = "minio_delta_catalog.silver.silver_compatibility"


# =============================================================================
# 1. GET /api/v1/tools — Paginated tool catalog
# =============================================================================


@router.get(
    "/",
    summary="Danh sách tất cả tools (Tech Catalog)",
    response_model=PaginatedResponse,
)
async def list_tools(
    page: int = Query(1, ge=1, description="Trang hiện tại (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items mỗi trang"),
    search: Optional[str] = Query(
        None, min_length=1, max_length=100,
        description="Tìm kiếm theo tool_name (LIKE)",
    ),
    lifecycle_status: Optional[str] = Query(
        None,
        description="Filter lifecycle: Active, Maintenance, EOL",
        pattern="^(Active|Maintenance|EOL)$",
    ),
    db=Depends(get_db),
):
    """Lấy danh sách tools từ Gold layer, kèm lifecycle status.

    Lifecycle logic:
    - **EOL**: ``eol_date < CURRENT_DATE()``
    - **Maintenance**: ``eol_date < CURRENT_DATE() + 90 ngày``
    - **Active**: còn lại (eol_date xa hoặc NULL)
    """
    # ── Build dynamic WHERE ──────────────────────────────────────────────
    conditions = []
    params = []

    if search:
        # SEC-03: sanitize LIKE meta-characters
        sanitized_search = search.replace("%", "").replace("_", " ").replace(";", "").strip()
        if sanitized_search:
            conditions.append("g.tool_name LIKE %s")
            params.append(f"%{sanitized_search}%")

    # Lifecycle filter được áp dụng bằng HAVING trên computed column
    # vì StarRocks không cho phép dùng alias trong WHERE
    lifecycle_having = ""
    if lifecycle_status:
        lifecycle_having = "HAVING lifecycle_status = %s"
        params.append(lifecycle_status)

    where = "WHERE " + " AND ".join(conditions) if conditions else ""

    # ── Count total ──────────────────────────────────────────────────────
    # Wrap trong subquery để count sau filter
    count_sql = f"""
        SELECT COUNT(*) AS cnt FROM (
            SELECT
                g.tool_name,
                CASE
                    WHEN g.eol_date IS NOT NULL AND g.eol_date < CURRENT_DATE()
                        THEN 'EOL'
                    WHEN g.eol_date IS NOT NULL AND g.eol_date < DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY)
                        THEN 'Maintenance'
                    ELSE 'Active'
                END AS lifecycle_status
            FROM {_GOLD_SUMMARY} g
            {where}
            {lifecycle_having}
        ) sub
    """

    with db.cursor() as cursor:
        cursor.execute(count_sql, tuple(params))
        count_row = cursor.fetchone()
    total = int(count_row["cnt"]) if count_row else 0

    # ── Paginated data ───────────────────────────────────────────────────
    offset = (page - 1) * page_size

    # Duplicate params: lần 1 cho subquery, lần 2 cho main query
    data_params = list(params) + [page_size, offset]

    data_sql = f"""
        SELECT
            g.tool_name,
            g.latest_version,
            g.eol_date,
            g.eos_date,
            g.total_cve_critical,
            g.total_cve_high,
            g.last_updated,
            CASE
                WHEN g.eol_date IS NOT NULL AND g.eol_date < CURRENT_DATE()
                    THEN 'EOL'
                WHEN g.eol_date IS NOT NULL AND g.eol_date < DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY)
                    THEN 'Maintenance'
                ELSE 'Active'
            END AS lifecycle_status,
            CASE
                WHEN g.total_cve_critical > 0 THEN 'critical'
                WHEN g.total_cve_high > 3 THEN 'high'
                WHEN g.total_cve_high > 0 THEN 'medium'
                ELSE 'low'
            END AS risk_level
        FROM {_GOLD_SUMMARY} g
        {where}
        {lifecycle_having}
        ORDER BY
            FIELD(
                CASE
                    WHEN g.total_cve_critical > 0 THEN 'critical'
                    WHEN g.total_cve_high > 3 THEN 'high'
                    WHEN g.total_cve_high > 0 THEN 'medium'
                    ELSE 'low'
                END,
                'critical', 'high', 'medium', 'low'
            ),
            g.tool_name ASC
        LIMIT %s OFFSET %s
    """

    with db.cursor() as cursor:
        cursor.execute(data_sql, tuple(data_params))
        rows = cursor.fetchall()

    return PaginatedResponse.create(
        data=rows,
        total=total,
        page=page,
        page_size=page_size,
        extra_meta={
            "filters": {
                "search": search,
                "lifecycle_status": lifecycle_status,
            },
        },
    )




# =============================================================================
# 2. GET /api/v1/tools/{tool_name} — Tool full detail
# =============================================================================


@router.get(
    "/{tool_name}",
    summary="Chi tiết đầy đủ một tool",
    response_model=BaseResponse,
)
async def get_tool_detail(tool_name: str, db=Depends(get_db)):
    """Lấy thông tin tổng hợp: summary, CVE breakdown, recent breaking changes.

    Trả 404 nếu tool không tồn tại.
    """
    # ── Gold summary ─────────────────────────────────────────────────────
    summary_sql = f"""
        SELECT
            g.tool_name,
            g.latest_version,
            g.eol_date,
            g.eos_date,
            g.total_cve_critical,
            g.total_cve_high,
            g.last_updated,
            CASE
                WHEN g.eol_date IS NOT NULL AND g.eol_date < CURRENT_DATE()
                    THEN 'EOL'
                WHEN g.eol_date IS NOT NULL AND g.eol_date < DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY)
                    THEN 'Maintenance'
                ELSE 'Active'
            END AS lifecycle_status,
            CASE
                WHEN g.total_cve_critical > 0 THEN 'critical'
                WHEN g.total_cve_high > 3 THEN 'high'
                WHEN g.total_cve_high > 0 THEN 'medium'
                ELSE 'low'
            END AS risk_level
        FROM {_GOLD_SUMMARY} g
        WHERE g.tool_name = %s
    """

    with db.cursor() as cursor:
        cursor.execute(summary_sql, (tool_name,))
        summary_row = cursor.fetchone()

    if summary_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tool '{tool_name}' not found",
        )

    # ── CVE severity breakdown ───────────────────────────────────────────
    cve_breakdown_sql = f"""
        SELECT
            severity,
            COUNT(*) AS count
        FROM {_SILVER_CVES}
        WHERE tool_name = %s
        GROUP BY severity
        ORDER BY FIELD(severity, 'Critical', 'High', 'Medium', 'Low')
    """

    with db.cursor() as cursor:
        cursor.execute(cve_breakdown_sql, (tool_name,))
        cve_breakdown = cursor.fetchall()

    # ── Total version count ──────────────────────────────────────────────
    version_count_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s
    """

    with db.cursor() as cursor:
        cursor.execute(version_count_sql, (tool_name,))
        version_row = cursor.fetchone()
    total_versions = int(version_row["cnt"]) if version_row else 0

    # ── Recent breaking changes (5 mới nhất) ─────────────────────────────
    breaking_sql = f"""
        SELECT version, release_date, breaking_changes, breaking_changes_enriched
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s
          AND breaking_changes IS NOT NULL
        ORDER BY release_date DESC
        LIMIT 5
    """

    with db.cursor() as cursor:
        cursor.execute(breaking_sql, (tool_name,))
        recent_breaking = cursor.fetchall()

    return BaseResponse(
        data={
            "summary": summary_row,
            "cve_breakdown": cve_breakdown,
            "total_versions": total_versions,
            "recent_breaking_changes": recent_breaking,
        },
        meta={
            "tool_name": tool_name,
            "risk_level": summary_row.get("risk_level"),
            "lifecycle_status": summary_row.get("lifecycle_status"),
        },
    )


# =============================================================================
# 3. GET /api/v1/tools/{tool_name}/versions — Version list
# =============================================================================


@router.get(
    "/{tool_name}/versions",
    summary="Tất cả versions của một tool",
    response_model=PaginatedResponse,
)
async def list_versions(
    tool_name: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db=Depends(get_db),
):
    """List tất cả versions, kèm cve_count và has_breaking_changes.

    Sort theo semantic version descending (dùng version string sort —
    chấp nhận được cho hiển thị, semver chính xác nằm ở Spark layer).
    """
    # Verify tool exists
    exists_sql = f"SELECT 1 FROM {_GOLD_SUMMARY} WHERE tool_name = %s LIMIT 1"
    with db.cursor() as cursor:
        cursor.execute(exists_sql, (tool_name,))
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Tool '{tool_name}' not found")

    # ── Count ────────────────────────────────────────────────────────────
    count_sql = f"""
        SELECT COUNT(*) AS cnt
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s
    """
    with db.cursor() as cursor:
        cursor.execute(count_sql, (tool_name,))
        count_row = cursor.fetchone()
    total = int(count_row["cnt"]) if count_row else 0

    # ── Paginated version list with CVE count + breaking change flag ─────
    offset = (page - 1) * page_size

    sql = f"""
        SELECT
            r.tool_name,
            r.version,
            r.release_date,
            r.breaking_changes,
            r.breaking_changes_enriched,
            r.deprecated_apis,
            CASE
                WHEN r.breaking_changes IS NOT NULL
                     AND JSON_LENGTH(r.breaking_changes) > 0
                THEN TRUE
                ELSE FALSE
            END AS has_breaking_changes,
            (
                SELECT COUNT(*)
                FROM {_SILVER_CVES} c
                WHERE c.tool_name = r.tool_name
                  AND JSON_CONTAINS(c.affected_versions, JSON_QUOTE(r.version))
            ) AS cve_count
        FROM {_SILVER_RELEASES} r
        WHERE r.tool_name = %s
        ORDER BY r.release_date DESC
        LIMIT %s OFFSET %s
    """
    # Note: cve_count uses JSON_CONTAINS for exact version matching.
    # CVEs with range specs like "<= 3.5.0" require Python post-processing
    # and may result in conservative (lower) counts here.

    with db.cursor() as cursor:
        cursor.execute(sql, (tool_name, page_size, offset))
        rows = cursor.fetchall()

    return PaginatedResponse.create(
        data=rows,
        total=total,
        page=page,
        page_size=page_size,
        extra_meta={"tool_name": tool_name},
    )


# =============================================================================
# 4. GET /api/v1/tools/{tool_name}/versions/{version} — Version detail
# =============================================================================


@router.get(
    "/{tool_name}/versions/{version}",
    summary="Chi tiết một version cụ thể",
    response_model=BaseResponse,
)
async def get_version_detail(
    tool_name: str,
    version: str,
    db=Depends(get_db),
):
    """Full detail cho một version: release info, CVEs, compatibility."""
    # ── Release detail ───────────────────────────────────────────────────
    release_sql = f"""
        SELECT tool_name, version, release_date,
               breaking_changes, breaking_changes_enriched, deprecated_apis, processed_at
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s AND version = %s
    """

    with db.cursor() as cursor:
        cursor.execute(release_sql, (tool_name, version))
        release_row = cursor.fetchone()

    if release_row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Version '{version}' not found for tool '{tool_name}'",
        )

    # ── CVEs affecting this version ──────────────────────────────────────
    # A-1: Hard cap at 200 rows to avoid full table scan for tools with many CVEs.
    # Long-term fix: use StarRocks JSON_CONTAINS for SQL-level version filtering
    # once affected_versions schema is standardized across all tools.
    cve_sql = f"""
        SELECT cve_id, tool_name, affected_versions, fixed_in_version,
               cvss_score, severity, description, published_at
        FROM {_SILVER_CVES}
        WHERE tool_name = %s
        ORDER BY cvss_score DESC
        LIMIT 200
    """

    with db.cursor() as cursor:
        cursor.execute(cve_sql, (tool_name,))
        all_cves = cursor.fetchall()

    # Filter CVEs using proper semver range comparison
    from processing.spark_utils.semver import is_version_affected
    import json as _json

    relevant_cves = []
    for cve in all_cves:
        affected = cve.get("affected_versions")
        if affected:
            if isinstance(affected, str):
                try:
                    affected = _json.loads(affected)
                except (ValueError, TypeError):
                    affected = [affected]
            if isinstance(affected, list):
                if any(is_version_affected(version, spec) for spec in affected if spec):
                    relevant_cves.append(cve)

    # ── Compatibility / dependencies ─────────────────────────────────────
    compat_sql = f"""
        SELECT tool_name, version, dependencies, processed_at
        FROM {_SILVER_COMPAT}
        WHERE tool_name = %s AND version = %s
    """

    try:
        with db.cursor() as cursor:
            cursor.execute(compat_sql, (tool_name, version))
            compat_row = cursor.fetchone()
    except Exception:
        # silver_compatibility có thể chưa tồn tại
        logger.debug("silver_compatibility not accessible for %s@%s", tool_name, version)
        compat_row = None

    return BaseResponse(
        data={
            "release": release_row,
            "cves": relevant_cves,
            "cve_count": len(relevant_cves),
            "compatibility": compat_row,
        },
        meta={
            "tool_name": tool_name,
            "version": version,
            "has_breaking_changes": release_row.get("breaking_changes") is not None,
        },
    )
