"""
DataStack Compass — CVEs Router
================================

Endpoints cho CVE search, filtering, và statistics.
Query StarRocks External Catalog (minio_iceberg_catalog.silver.silver_cves).
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pymysql.connections import Connection

from api.database import get_db
from api.models.response import BaseResponse, PaginatedResponse

logger = logging.getLogger(__name__)

router = APIRouter()

_SILVER_CVES = "minio_iceberg_catalog.silver.silver_cves"
_ASSET_INVENTORY = "compass_internal.asset_inventory"


@router.get(
    "",
    summary="Tìm kiếm CVEs",
    response_model=PaginatedResponse,
)
async def list_cves(
    tool_name: Optional[str] = Query(None, description="Filter theo tool"),
    severity: str = Query("All", description="Filter severity: Critical, High, Medium, Low, All"),
    days: int = Query(30, description="Số ngày gần đây"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Connection = Depends(get_db)
):
    """Lấy danh sách CVEs với filter và pagination."""
    conditions = ["published_at >= DATE_SUB(NOW(), INTERVAL %s DAY)"]
    params = [days]

    if severity and severity.lower() != "all":
        conditions.append("severity = %s")
        params.append(severity)
        
    if tool_name:
        conditions.append("tool_name = %s")
        params.append(tool_name)

    where = "WHERE " + " AND ".join(conditions)

    count_sql = f"SELECT COUNT(*) AS cnt FROM {_SILVER_CVES} {where}"
    
    offset = (page - 1) * page_size
    sql = f"""
        SELECT cve_id, tool_name, affected_versions, fixed_in_version,
               cvss_score, severity, description, published_at
        FROM {_SILVER_CVES}
        {where}
        ORDER BY cvss_score DESC, published_at DESC
        LIMIT %s OFFSET %s
    """
    
    with db.cursor() as cursor:
        cursor.execute(count_sql, tuple(params))
        total_row = cursor.fetchone()
        total = total_row["cnt"] if total_row else 0
        
        cursor.execute(sql, tuple(params) + (page_size, offset))
        rows = cursor.fetchall()

    return PaginatedResponse.create(
        data=rows,
        total=total,
        page=page,
        page_size=page_size,
        extra_meta={"filters": {"tool_name": tool_name, "severity": severity, "days": days}},
    )


@router.get(
    "/stats/summary",
    summary="CVE statistics tổng hợp",
    response_model=BaseResponse,
)
async def cve_stats_summary(db: Connection = Depends(get_db)):
    """Thống kê CVE cho Dashboard Stats Row."""
    sql_severity = f"""
        SELECT severity, COUNT(*) as cnt
        FROM {_SILVER_CVES}
        GROUP BY severity
    """
    
    sql_time = f"""
        SELECT 
            COUNT(CASE WHEN published_at >= DATE_SUB(NOW(), INTERVAL 7 DAY) THEN 1 END) as new_7d,
            COUNT(CASE WHEN published_at >= DATE_SUB(NOW(), INTERVAL 30 DAY) THEN 1 END) as new_30d,
            MAX(cvss_score) as max_cvss
        FROM {_SILVER_CVES}
    """
    
    sql_tool = f"""
        SELECT tool_name, COUNT(*) as cnt
        FROM {_SILVER_CVES}
        GROUP BY tool_name
        ORDER BY cnt DESC
        LIMIT 1
    """
    
    with db.cursor() as cursor:
        cursor.execute(sql_severity)
        sev_rows = cursor.fetchall()
        
        cursor.execute(sql_time)
        time_row = cursor.fetchone()
        
        cursor.execute(sql_tool)
        tool_row = cursor.fetchone()
        
    stats = {
        "total_critical": 0,
        "total_high": 0,
        "total_medium": 0,
        "total_low": 0,
    }
    
    for row in sev_rows:
        sev = row["severity"].lower()
        if sev == "critical": stats["total_critical"] = row["cnt"]
        elif sev == "high": stats["total_high"] = row["cnt"]
        elif sev == "medium": stats["total_medium"] = row["cnt"]
        elif sev == "low": stats["total_low"] = row["cnt"]
        
    stats["new_last_7_days"] = time_row["new_7d"] if time_row and time_row["new_7d"] else 0
    stats["new_last_30_days"] = time_row["new_30d"] if time_row and time_row["new_30d"] else 0
    stats["highest_cvss"] = float(time_row["max_cvss"]) if time_row and time_row["max_cvss"] else 0.0
    stats["most_affected_tool"] = tool_row["tool_name"] if tool_row else None

    # Trả về format đúng như yêu cầu
    return BaseResponse(data=stats)


@router.get(
    "/affected/{tool_name}/{version}",
    summary="CVEs ảnh hưởng đến một version",
    response_model=BaseResponse,
)
async def affected_cves(tool_name: str, version: str, db: Connection = Depends(get_db)):
    """Lấy tất cả CVEs ảnh hưởng đến version cụ thể của tool."""
    sql = f"""
        SELECT cve_id, tool_name, affected_versions, fixed_in_version,
               cvss_score, severity, description, published_at
        FROM {_SILVER_CVES}
        WHERE tool_name = %s AND array_contains(affected_versions, %s)
        ORDER BY cvss_score DESC
    """
    
    with db.cursor() as cursor:
        cursor.execute(sql, (tool_name, version))
        rows = cursor.fetchall()
        
    return BaseResponse(data=rows)


@router.get(
    "/{cve_id}",
    summary="Chi tiết một CVE",
    response_model=BaseResponse,
)
async def get_cve(cve_id: str, db: Connection = Depends(get_db)):
    """Lấy chi tiết một CVE theo ID, kèm theo tài sản bị ảnh hưởng."""
    sql = f"""
        SELECT c.cve_id, c.tool_name, c.affected_versions, c.fixed_in_version,
               c.cvss_score, c.severity, c.description, c.published_at,
               a.team_name, a.owner_email, a.environment, a.version_in_use
        FROM {_SILVER_CVES} c
        LEFT JOIN {_ASSET_INVENTORY} a 
          ON c.tool_name = a.tool_name 
         AND array_contains(c.affected_versions, a.version_in_use)
        WHERE c.cve_id = %s
    """
    
    with db.cursor() as cursor:
        cursor.execute(sql, (cve_id,))
        rows = cursor.fetchall()
        
    if not rows:
        raise HTTPException(status_code=404, detail=f"CVE '{cve_id}' not found")
        
    cve_data = {
        "cve_id": rows[0]["cve_id"],
        "tool_name": rows[0]["tool_name"],
        "affected_versions": rows[0]["affected_versions"],
        "fixed_in_version": rows[0]["fixed_in_version"],
        "cvss_score": rows[0]["cvss_score"],
        "severity": rows[0]["severity"],
        "description": rows[0]["description"],
        "published_at": rows[0]["published_at"],
        "affected_assets": []
    }
    
    for r in rows:
        if r["team_name"] or r["version_in_use"]: 
            cve_data["affected_assets"].append({
                "team_name": r["team_name"],
                "owner_email": r["owner_email"],
                "environment": r["environment"],
                "version_in_use": r["version_in_use"]
            })
            
    return BaseResponse(
        data=cve_data,
        meta={"nvd_url": f"https://nvd.nist.gov/vuln/detail/{cve_id}"},
    )
