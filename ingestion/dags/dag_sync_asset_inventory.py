"""
DataStack Compass — DAG: Sync Asset Inventory
=============================================

Đồng bộ Asset Inventory từ file seed JSON trên MinIO vào StarRocks.
Hỗ trợ Bootstrap: tự động copy file cấu hình local lên MinIO lần đầu.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timedelta
from typing import Any, Dict

from airflow.decorators import dag, task

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

logger = logging.getLogger(__name__)

# Constants
_STARROCKS_HOST = os.environ.get("STARROCKS_HOST", "127.0.0.1")
_STARROCKS_PORT = int(os.environ.get("STARROCKS_PORT", "9030"))
_STARROCKS_USER = os.environ.get("STARROCKS_USER", "root")
_STARROCKS_PASSWORD = os.environ.get("STARROCKS_PASSWORD", "")

if not _STARROCKS_PASSWORD:
    import warnings
    warnings.warn(
        "STARROCKS_PASSWORD is empty — root access without password is insecure. "
        "Set STARROCKS_PASSWORD in your environment.",
        RuntimeWarning,
        stacklevel=2
    )

_MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
_MINIO_ACCESS_KEY = os.environ.get("MINIO_ACCESS_KEY", "")
_MINIO_SECRET_KEY = os.environ.get("MINIO_SECRET_KEY", "")

if not _MINIO_ACCESS_KEY or not _MINIO_SECRET_KEY:
    raise EnvironmentError(
        "MINIO_ACCESS_KEY and MINIO_SECRET_KEY are required but not set."
    )

_BUCKET_NAME = "configs"
_SEED_FILE_KEY = "asset_inventory_seed.json"

_DEFAULT_ARGS: Dict[str, Any] = {
    "owner": "datastack-compass",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 1,
    "retry_delay": timedelta(minutes=1),
}

def get_s3_client():
    import boto3
    from botocore.client import Config
    return boto3.client(
        "s3",
        endpoint_url=_MINIO_ENDPOINT,
        aws_access_key_id=_MINIO_ACCESS_KEY,
        aws_secret_access_key=_MINIO_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1"
    )

@dag(
    dag_id="sync_asset_inventory",
    description="Đồng bộ Asset Inventory từ MinIO vào StarRocks (UPSERT)",
    schedule="0 0 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ingestion", "asset-inventory", "governance"],
    default_args=_DEFAULT_ARGS,
    doc_md=__doc__,
)
def sync_asset_inventory():

    @task(task_id="bootstrap_seed_file")
    def bootstrap_seed_file() -> None:
        """Kiểm tra và copy file seed local lên MinIO nếu chưa có."""
        s3 = get_s3_client()
        import botocore.exceptions
        
        # Create bucket if not exists
        try:
            s3.head_bucket(Bucket=_BUCKET_NAME)
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.info(f"Bucket {_BUCKET_NAME} does not exist, creating it.")
                s3.create_bucket(Bucket=_BUCKET_NAME)
            else:
                raise e
                
        # Check if file exists
        local_seed_path = os.path.join(_PROJECT_ROOT, "configs", "asset_inventory_seed.json")
        try:
            s3.head_object(Bucket=_BUCKET_NAME, Key=_SEED_FILE_KEY)
            logger.info("Seed file already exists on MinIO. Skipping bootstrap.")
        except botocore.exceptions.ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                logger.info(f"Uploading local seed file {local_seed_path} to s3a://{_BUCKET_NAME}/{_SEED_FILE_KEY}")
                s3.upload_file(local_seed_path, _BUCKET_NAME, _SEED_FILE_KEY)
            else:
                raise e

    @task(task_id="sync_to_starrocks")
    def sync_to_starrocks() -> dict:
        """Tải JSON từ MinIO, validate tool_name, sau đó UPSERT vào StarRocks."""
        import pymysql
        s3 = get_s3_client()
        
        logger.info(f"Downloading s3a://{_BUCKET_NAME}/{_SEED_FILE_KEY}")
        response = s3.get_object(Bucket=_BUCKET_NAME, Key=_SEED_FILE_KEY)
        json_content = response['Body'].read().decode('utf-8')
        assets = json.loads(json_content)
        
        if not isinstance(assets, list):
            raise ValueError("Seed file must contain a JSON array.")
            
        logger.info(f"Found {len(assets)} records in seed file.")
        
        conn = pymysql.connect(
            host=_STARROCKS_HOST,
            port=_STARROCKS_PORT,
            user=_STARROCKS_USER,
            password=_STARROCKS_PASSWORD,
            connect_timeout=10,
            autocommit=True  # for validation queries
        )
        
        with conn.cursor() as cursor:
            # Lấy list tool_name hợp lệ để validate
            cursor.execute("SELECT DISTINCT tool_name FROM minio_iceberg_catalog.silver.silver_releases")
            valid_tools = set([row[0] for row in cursor.fetchall()])
            
            if not valid_tools:
                logger.warning("No tools found in silver_releases! We will still allow insertion if this is a fresh setup or we bypass validation for fallback.")
            
            valid_assets = []
            asset_keys = []
            
            for asset in assets:
                t_name = asset.get("tool_name")
                proj = asset.get("project_name")
                env = asset.get("environment", "production")
                
                if valid_tools and t_name not in valid_tools:
                    logger.warning(f"Skipping invalid tool_name: {t_name}")
                    continue

                # SCHEMA-02 fix: validate version_in_use is non-null before insert
                version = asset.get("version_in_use")
                if not version or not isinstance(version, str) or not version.strip():
                    logger.warning(f"Skipping asset '{t_name}/{proj}' — missing version_in_use")
                    continue
                    
                valid_assets.append((
                    t_name, proj, env,
                    asset.get("department"),
                    asset.get("team_name"),
                    version.strip(),
                    asset.get("owner_email")
                ))
                asset_keys.append((t_name, proj, env))
                
            logger.info(f"Valid assets to UPSERT: {len(valid_assets)}")

            # FLOW-03 fix: empty seed file should never wipe the inventory
            if not valid_assets:
                logger.warning(
                    "No valid assets found after parsing seed file — "
                    "skipping DELETE to prevent data loss."
                )
                conn.close()
                return {"total_in_seed": len(assets), "valid_assets_synced": 0}

            # A-3: Wrap UPSERT + orphan DELETE in explicit transaction
            # so a crash between them cannot leave data inconsistent.
            conn.autocommit = False
            try:
                # Upsert cho bảng Primary Key (INSERT = upsert in StarRocks PK table)
                insert_sql = """
                    INSERT INTO compass_internal.asset_inventory
                    (tool_name, project_name, environment, department, team_name, version_in_use, owner_email, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """
                cursor.executemany(insert_sql, valid_assets)

                # Delete orphans
                key_strings = [f"{t}|||{p}|||{e}" for t, p, e in asset_keys]
                format_strings = ','.join(['%s'] * len(key_strings))

                delete_sql = f"""
                    DELETE FROM compass_internal.asset_inventory
                    WHERE CONCAT(tool_name, '|||', project_name, '|||', environment) NOT IN ({format_strings})
                """
                cursor.execute(delete_sql, tuple(key_strings))
                deleted_rows = cursor.rowcount

                conn.commit()
                logger.info(
                    f"Asset sync committed: {len(valid_assets)} upserted, "
                    f"{deleted_rows} orphans removed"
                )
            except Exception as e:
                conn.rollback()
                logger.error(f"Asset sync transaction failed, rolled back: {e}")
                raise  # re-raise so Airflow marks task FAILED
            finally:
                conn.autocommit = True
                
        conn.close()
        
        return {
            "total_in_seed": len(assets),
            "valid_assets_synced": len(valid_assets),
        }

    bootstrap_seed_file() >> sync_to_starrocks()

sync_asset_inventory()
