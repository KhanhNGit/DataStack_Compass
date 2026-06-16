"""
DataStack Compass — StarRocks Database Layer
=============================================

Connection pooling và query execution cho StarRocks (MySQL-compatible protocol).
Tất cả SQL syntax PHẢI tương thích StarRocks — KHÔNG dùng PostgreSQL syntax.

StarRocks specifics:
- MySQL protocol trên port 9030
- Hỗ trợ: LIMIT/OFFSET, GROUP BY, HAVING, window functions
- External Catalog: ``minio_delta_catalog.gold.gold_tool_summary``
- KHÔNG hỗ trợ: RETURNING, ON CONFLICT, CTE recursive
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, Tuple, Union

import pymysql
from dbutils.pooled_db import PooledDB

logger = logging.getLogger(__name__)

# =============================================================================
# Config từ environment variables
# =============================================================================

_STARROCKS_HOST = os.environ.get("STARROCKS_HOST", "127.0.0.1")
_STARROCKS_PORT = int(os.environ.get("STARROCKS_PORT", "9030"))
_STARROCKS_USER = os.environ.get("STARROCKS_USER", "root")
_STARROCKS_PASSWORD = os.environ.get("STARROCKS_PASSWORD", "")
_STARROCKS_DATABASE = os.environ.get("STARROCKS_DATABASE", "")
_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))

if not _STARROCKS_PASSWORD:
    import warnings
    warnings.warn(
        "STARROCKS_PASSWORD is empty — root access without password is insecure. "
        "Set STARROCKS_PASSWORD in your environment.",
        RuntimeWarning,
        stacklevel=2
    )

# =============================================================================
# Connection pool (module-level singleton)
# =============================================================================

_pool: Optional[PooledDB] = None


def _get_pool() -> PooledDB:
    """Lazy-init connection pool."""
    global _pool

    if _pool is None:
        logger.info(
            "Creating StarRocks connection pool: %s@%s:%d (pool_size=%d)",
            _STARROCKS_USER,
            _STARROCKS_HOST,
            _STARROCKS_PORT,
            _POOL_SIZE,
        )
        _pool = PooledDB(
            creator=pymysql,
            maxconnections=_POOL_SIZE,
            mincached=1,
            maxcached=_POOL_SIZE,
            blocking=True,
            host=_STARROCKS_HOST,
            port=_STARROCKS_PORT,
            user=_STARROCKS_USER,
            password=_STARROCKS_PASSWORD,
            database=_STARROCKS_DATABASE or None,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=10,
            read_timeout=30,
        )

    return _pool


def close_pool() -> None:
    """Close connection pool (gọi khi shutdown)."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
        logger.info("StarRocks connection pool closed")


# =============================================================================
# Connection dependency (FastAPI / contextmanager)
# =============================================================================


@contextmanager
def get_db() -> Generator[pymysql.connections.Connection, None, None]:
    """Get a database connection from pool.

    Usage as FastAPI dependency:
        @app.get("/items")
        def read_items(db=Depends(get_db)):
            ...

    Usage standalone:
        with get_db() as conn:
            ...
    """
    pool = _get_pool()
    conn = pool.connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()  # Returns to pool, doesn't actually close


# =============================================================================
# Query execution
# =============================================================================


def execute_query(
    sql: str,
    params: Union[Tuple, Dict[str, Any], None] = None,
) -> List[Dict[str, Any]]:
    """Execute a SELECT query và trả về list of dicts.

    Parameters
    ----------
    sql : str
        SQL query (StarRocks/MySQL-compatible syntax).
        QUAN TRỌNG: dùng %s placeholder, KHÔNG dùng $1 (PostgreSQL style).
    params : tuple | dict | None
        Query parameters cho prepared statement.

    Returns
    -------
    list[dict]
        Mỗi dict là một row, keys = column names.

    Examples
    --------
    >>> execute_query(
    ...     "SELECT * FROM gold.gold_tool_summary WHERE tool_name = %s LIMIT %s",
    ...     ("apache-kafka", 10),
    ... )
    [{"tool_name": "apache-kafka", "latest_version": "3.7.1", ...}]
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            results = cursor.fetchall()

    return results


def execute_query_one(
    sql: str,
    params: Union[Tuple, Dict[str, Any], None] = None,
) -> Optional[Dict[str, Any]]:
    """Execute query và trả về một row duy nhất (hoặc None).

    Parameters
    ----------
    sql : str
        SQL query.
    params : tuple | dict | None
        Query parameters.

    Returns
    -------
    dict | None
        Row đầu tiên hoặc None nếu không có kết quả.
    """
    with get_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            return cursor.fetchone()


def execute_count(
    sql: str,
    params: Union[Tuple, Dict[str, Any], None] = None,
) -> int:
    """Execute COUNT query và trả về số lượng.

    Parameters
    ----------
    sql : str
        SQL query dạng ``SELECT COUNT(*) AS cnt FROM ...``
    params : tuple | dict | None
        Query parameters.

    Returns
    -------
    int
        Giá trị count.
    """
    result = execute_query_one(sql, params)
    if result is None:
        return 0

    # Lấy giá trị đầu tiên trong dict (column name có thể khác nhau)
    return int(next(iter(result.values())))


# =============================================================================
# Health check
# =============================================================================


def check_db_connection() -> bool:
    """Kiểm tra kết nối StarRocks.

    Returns
    -------
    bool
        True nếu kết nối thành công.
    """
    try:
        result = execute_query_one("SELECT 1 AS ok")
        return result is not None and result.get("ok") == 1
    except Exception as exc:
        logger.warning("StarRocks health check failed: %s", exc)
        return False
