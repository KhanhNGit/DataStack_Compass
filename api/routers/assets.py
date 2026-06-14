"""
DataStack Compass — Assets Router
===================================

Endpoint truy xuất Asset Inventory Risk Overview
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from pymysql.connections import Connection

from api.database import get_db
from api.models.response import BaseResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/risk-overview",
    summary="Asset Risk Overview",
    response_model=BaseResponse,
)
async def asset_risk_overview(db: Connection = Depends(get_db)):
    """Lấy danh sách Asset Inventory kết hợp số liệu Risk."""
    sql = """
        SELECT 
            a.department,
            a.project_name,
            a.team_name,
            a.tool_name,
            a.version_in_use,
            a.environment,
            g.eol_date,
            COUNT(CASE WHEN c.severity = 'Critical' THEN 1 END) AS critical_cves_count,
            COUNT(CASE WHEN c.severity = 'High' THEN 1 END) AS high_cves_count
        FROM compass_internal.asset_inventory a
        LEFT JOIN minio_delta_catalog.gold.gold_tool_summary g 
            ON a.tool_name = g.tool_name
        LEFT JOIN minio_delta_catalog.silver.silver_cves c 
            ON a.tool_name = c.tool_name 
            AND array_contains(c.affected_versions, a.version_in_use)
        GROUP BY 
            a.department,
            a.project_name,
            a.team_name,
            a.tool_name,
            a.version_in_use,
            a.environment,
            g.eol_date
        ORDER BY a.department, a.project_name, a.tool_name
    """
    
    with db.cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()
        
    return BaseResponse(data=rows)
