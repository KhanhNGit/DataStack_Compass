"""
DataStack Compass — Governance Router
======================================

Endpoints cho governance dashboards: compliance status, EOL tracking,
và license monitoring.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from api.database import execute_query
from api.models.response import BaseResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_GOLD_SUMMARY = "minio_catalog.gold.gold_tool_summary"
_SILVER_LICENSES = "minio_catalog.silver.silver_license_changes"


@router.get(
    "/eol-status",
    summary="EOL/EOS status tất cả tools",
    response_model=BaseResponse,
)
async def eol_status():
    """Danh sách tools theo trạng thái EOL/EOS cho governance dashboard."""
    sql = f"""
        SELECT tool_name, latest_version, eol_date, eos_date,
               CASE
                   WHEN eol_date IS NOT NULL AND eol_date < CURRENT_DATE()
                       THEN 'eol_reached'
                   WHEN eos_date IS NOT NULL AND eos_date < CURRENT_DATE()
                       THEN 'eos_reached'
                   WHEN eol_date IS NOT NULL
                       THEN 'eol_scheduled'
                   ELSE 'active'
               END AS lifecycle_status
        FROM {_GOLD_SUMMARY}
        ORDER BY eol_date ASC
    """
    rows = execute_query(sql)

    # Summary counts
    status_counts = {}
    for row in rows:
        status = row.get("lifecycle_status", "unknown")
        status_counts[status] = status_counts.get(status, 0) + 1

    return BaseResponse(
        data=rows,
        meta={"status_counts": status_counts},
    )


@router.get(
    "/compliance-summary",
    summary="Tổng hợp compliance",
    response_model=BaseResponse,
)
async def compliance_summary():
    """Dashboard compliance: tools với CVE chưa patch, EOL đã quá hạn."""
    sql = f"""
        SELECT
            tool_name,
            latest_version,
            total_cve_critical,
            total_cve_high,
            eol_date,
            CASE
                WHEN total_cve_critical > 0 THEN 'non_compliant'
                WHEN eol_date IS NOT NULL AND eol_date < CURRENT_DATE() THEN 'non_compliant'
                WHEN total_cve_high > 0 THEN 'at_risk'
                ELSE 'compliant'
            END AS compliance_status
        FROM {_GOLD_SUMMARY}
        ORDER BY
            FIELD(
                CASE
                    WHEN total_cve_critical > 0 THEN 'non_compliant'
                    WHEN eol_date IS NOT NULL AND eol_date < CURRENT_DATE() THEN 'non_compliant'
                    WHEN total_cve_high > 0 THEN 'at_risk'
                    ELSE 'compliant'
                END,
                'non_compliant', 'at_risk', 'compliant'
            )
    """
    rows = execute_query(sql)

    return BaseResponse(
        data=rows,
        meta={"total_tools": len(rows)},
    )


@router.get(
    "/license-changes",
    summary="License changes history",
    response_model=BaseResponse,
)
async def license_changes():
    """Lịch sử thay đổi license của tools — quan trọng cho legal compliance."""
    sql = f"""
        SELECT tool_name, from_version, to_version,
               old_license, new_license, changed_at
        FROM {_SILVER_LICENSES}
        ORDER BY changed_at DESC
        LIMIT 50
    """
    try:
        rows = execute_query(sql)
    except Exception:
        # silver_license_changes có thể chưa tồn tại
        logger.warning("silver_license_changes table not accessible")
        rows = []

    return BaseResponse(
        data=rows,
        meta={"total": len(rows)},
    )
