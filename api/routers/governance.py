import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pymysql.connections import Connection

from api.database import get_db
from api.models.response import BaseResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/governance", tags=["governance"])

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
        FROM minio_delta_catalog.silver.silver_cves
        {where_clause}
        ORDER BY published_at DESC, cvss_score DESC
        LIMIT %s OFFSET %s
    """
    
    count_sql = f"SELECT COUNT(*) as count FROM minio_delta_catalog.silver.silver_cves {where_clause}"
    
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
        FROM minio_delta_catalog.silver.silver_blogs
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
