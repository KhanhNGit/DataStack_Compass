"""
DataStack Compass — Init StarRocks Schema
===========================================

Khởi tạo External Catalog và Internal Database cho StarRocks.
Đọc từ file setup_starrocks.sql và thay thế các biến môi trường.
"""

from __future__ import annotations

import logging
import os
import sys

import pymysql

# ─── Đảm bảo project root nằm trên sys.path (để run từ thư mục nào cũng được) ──
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("init_starrocks")

def main():
    logger.info("Starting StarRocks initialization...")

    # 1. Đọc file SQL
    sql_path = os.path.join(os.path.dirname(__file__), "..", "ddl", "setup_starrocks.sql")
    if not os.path.exists(sql_path):
        logger.error("FAIL: File not found: %s", sql_path)
        sys.exit(1)
        
    with open(sql_path, "r", encoding="utf-8") as f:
        sql_content = f.read()

    # 2. Thay thế environment variables
    minio_ak = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    minio_sk = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    
    # Đối với StarRocks (chạy trong Docker container), endpoint phải trỏ tới container minio
    minio_ep = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
    if minio_ep == "http://localhost:9000":
        logger.info("Auto-correcting MINIO_ENDPOINT from localhost to minio for StarRocks")
        minio_ep = "http://minio:9000"

    sql_content = sql_content.replace("${MINIO_ACCESS_KEY}", minio_ak)
    sql_content = sql_content.replace("${MINIO_SECRET_KEY}", minio_sk)
    sql_content = sql_content.replace("${MINIO_ENDPOINT}", minio_ep)

    # Chia các statements bằng dấu ';'
    statements = []
    for stmt in sql_content.split(";"):
        stmt = stmt.strip()
        if stmt:
            statements.append(stmt)

    # 3. Kết nối StarRocks
    host = os.environ.get("STARROCKS_HOST", "127.0.0.1")
    port = int(os.environ.get("STARROCKS_PORT", "9030"))
    user = os.environ.get("STARROCKS_USER", "root")
    password = os.environ.get("STARROCKS_PASSWORD", "")

    logger.info("Connecting to StarRocks at %s:%d as %s", host, port, user)
    
    try:
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            connect_timeout=10,
            autocommit=True,
        )
    except Exception as exc:
        logger.error("FAIL: Could not connect to StarRocks: %s", exc)
        sys.exit(1)

    logger.info("PASS: Connected to StarRocks")

    # 4. Thực thi từng statement
    with conn.cursor() as cursor:
        for i, stmt in enumerate(statements, 1):
            # Lấy 50 ký tự đầu làm log preview
            preview = stmt[:50].replace("\n", " ") + "..."
            logger.info("Executing statement %d: %s", i, preview)
            try:
                cursor.execute(stmt)
                logger.info("PASS: Statement %d executed successfully", i)
            except Exception as exc:
                logger.error("FAIL: Statement %d failed: %s", i, exc)
                sys.exit(1)

        # 5. Verify kết quả
        logger.info("Verifying catalogs and databases...")
        
        cursor.execute("SHOW CATALOGS")
        catalogs = [row[0] for row in cursor.fetchall()]
        if "minio_delta_catalog" in catalogs:
            logger.info("PASS: Catalog 'minio_delta_catalog' exists")
        else:
            logger.error("FAIL: Catalog 'minio_delta_catalog' not found")
            sys.exit(1)

        cursor.execute("SHOW DATABASES")
        dbs = [row[0] for row in cursor.fetchall()]
        if "compass_internal" in dbs:
            logger.info("PASS: Database 'compass_internal' exists")
        else:
            logger.error("FAIL: Database 'compass_internal' not found")
            sys.exit(1)

    conn.close()
    logger.info("PASS: StarRocks initialization complete. All checks passed.")

if __name__ == "__main__":
    main()
