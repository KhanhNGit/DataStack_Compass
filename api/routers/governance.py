import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pymysql.connections import Connection

from api.database import get_db
from api.models.response import BaseResponse

logger = logging.getLogger(__name__)

# BUG-06 fix: prefix is set in main.py include_router(), not here
router = APIRouter()

_GOLD_SUMMARY = "minio_delta_catalog.gold.gold_tool_summary"
_SILVER_CVES = "minio_delta_catalog.silver.silver_cves"
_SILVER_BLOGS = "minio_delta_catalog.silver.silver_blogs"


@router.get("/bulletins", response_model=BaseResponse)
async def get_bulletins(
    page: int = Query(1, ge=1), 
    severity: Optional[str] = None,
    db: Connection = Depends(get_db)
):
    per_page = 10
    offset = (page - 1) * per_page
    
    where_clause = ""
    params = []
    
    if severity and severity != "All":
        where_clause = "WHERE severity = %s"
        params.append(severity)
        
    sql = f"""
        SELECT cve_id, tool_name, severity, cvss_score, description, published_at, affected_versions, fixed_in_version
        FROM {_SILVER_CVES}
        {where_clause}
        ORDER BY published_at DESC, cvss_score DESC
        LIMIT %s OFFSET %s
    """
    
    count_sql = f"SELECT COUNT(*) as count FROM {_SILVER_CVES} {where_clause}"
    
    with db.cursor() as cursor:
        cursor.execute(count_sql, tuple(params))
        total_count = cursor.fetchone()["count"]
        
        cursor.execute(sql, tuple(params + [per_page, offset]))
        rows = cursor.fetchall()
        
    return BaseResponse(
        data=rows,
        meta={
            "page": page,
            "total_count": total_count,
            "source": "starrocks"
        }
    )


@router.get("/eol-status", response_model=BaseResponse)
async def get_eol_status(db: Connection = Depends(get_db)):
    """Tools sorted by EOL date — used by Dashboard EOL Timeline."""
    sql = f"""
        SELECT
            tool_name,
            latest_version,
            eol_date,
            CASE
                WHEN eol_date IS NOT NULL AND eol_date < CURRENT_DATE()
                    THEN 'EOL'
                WHEN eol_date IS NOT NULL AND eol_date < DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY)
                    THEN 'Maintenance'
                ELSE 'Active'
            END AS lifecycle_status
        FROM {_GOLD_SUMMARY}
        WHERE eol_date IS NOT NULL
        ORDER BY eol_date ASC
    """

    with db.cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()

    return BaseResponse(
        data=rows,
        meta={"total_count": len(rows), "source": "starrocks"}
    )


@router.get("/blogs", response_model=BaseResponse)
async def get_blogs(
    tool: Optional[str] = None, 
    tag: Optional[str] = None,
    db: Connection = Depends(get_db)
):
    where_clauses = []
    params = []
    
    if tool and tool != "All":
        where_clauses.append("tool_name = %s")
        params.append(tool)
        
    if tag and tag != "All":
        where_clauses.append("array_contains(tags, %s)")
        params.append(tag)
        
    where_stmt = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""
    
    sql = f"""
        SELECT tool_name, title, url, published_date, summary, tags, source_feed
        FROM {_SILVER_BLOGS}
        {where_stmt}
        ORDER BY published_date DESC
    """
    
    with db.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()
        
    return BaseResponse(
        data=rows,
        meta={
            "total_count": len(rows),
            "source": "starrocks"
        }
    )
