"""
DataStack Compass — Delta Lake Table Schemas
=============================================

Định nghĩa StructType schema cho toàn bộ Lakehouse (Bronze → Silver → Gold)
và function tạo bảng Delta nếu chưa tồn tại trên MinIO.

Bucket paths đọc từ environment variables:
    MINIO_BUCKET_BRONZE  (default: "bronze")
    MINIO_BUCKET_SILVER  (default: "silver")
    MINIO_BUCKET_GOLD    (default: "gold")

Path format: s3a://{bucket}/{table_name}/

Usage
-----
    from storage.delta.schemas import SCHEMAS, create_delta_tables
    from processing.spark_utils import get_spark_session

    spark = get_spark_session("schema-init")
    create_delta_tables(spark)

    # Truy cập schema riêng lẻ
    schema = SCHEMAS["silver_releases"]
"""

from __future__ import annotations

import logging
import os
from typing import Dict

from pyspark.sql import SparkSession
from pyspark.sql.types import (
    ArrayType,
    DateType,
    FloatType,
    IntegerType,
    MapType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

logger = logging.getLogger(__name__)

# =============================================================================
# 1. Bronze Layer — Raw ingested data
# =============================================================================

bronze_raw_releases = StructType([
    StructField("tool_name", StringType(), nullable=False),
    StructField("version", StringType(), nullable=False),
    StructField("raw_json", StringType(), nullable=False),
    StructField("source_url", StringType(), nullable=True),
    StructField("crawled_at", TimestampType(), nullable=False),
    StructField("source_type", StringType(), nullable=False),
    # source_type ∈ {"github", "jira", "official_docs"}
])

# =============================================================================
# 2. Silver Layer — Cleaned & structured
# =============================================================================

_issue_struct = StructType([
    StructField("id", StringType(), nullable=False),
    StructField("type", StringType(), nullable=False),
    # type ∈ {"Bug", "Feature", "Improvement"}
    StructField("title", StringType(), nullable=False),
    StructField("url", StringType(), nullable=True),
])

silver_releases = StructType([
    StructField("tool_name", StringType(), nullable=False),
    StructField("version", StringType(), nullable=False),
    # version follows Semantic Versioning (MAJOR.MINOR.PATCH)
    StructField("release_date", DateType(), nullable=True),
    StructField("issues", ArrayType(_issue_struct), nullable=True),
    StructField("breaking_changes", ArrayType(StringType()), nullable=True),
    StructField("deprecated_apis", ArrayType(StringType()), nullable=True),
    StructField("processed_at", TimestampType(), nullable=False),
])

silver_cves = StructType([
    StructField("cve_id", StringType(), nullable=False),
    StructField("tool_name", StringType(), nullable=False),
    StructField("affected_versions", ArrayType(StringType()), nullable=False),
    StructField("fixed_in_version", StringType(), nullable=True),
    StructField("cvss_score", FloatType(), nullable=True),
    StructField("severity", StringType(), nullable=False),
    # severity ∈ {"Critical", "High", "Medium", "Low"}
    StructField("description", StringType(), nullable=True),
    StructField("published_at", TimestampType(), nullable=True),
])

silver_compatibility = StructType([
    StructField("tool_name", StringType(), nullable=False),
    StructField("version", StringType(), nullable=False),
    StructField(
        "dependencies",
        MapType(StringType(), StringType(), valueContainsNull=False),
        nullable=True,
    ),
    # dependencies: {"hadoop": "3.3.6", "java": "11", ...}
    StructField("processed_at", TimestampType(), nullable=False),
])

silver_license_changes = StructType([
    StructField("tool_name", StringType(), nullable=False),
    StructField("from_version", StringType(), nullable=False),
    StructField("to_version", StringType(), nullable=False),
    StructField("old_license", StringType(), nullable=False),
    StructField("new_license", StringType(), nullable=False),
    StructField("changed_at", DateType(), nullable=True),
])

silver_blogs = StructType([
    StructField("tool_name", StringType(), nullable=False),
    StructField("title", StringType(), nullable=False),
    StructField("url", StringType(), nullable=False),
    StructField("published_date", TimestampType(), nullable=True),
    StructField("summary", StringType(), nullable=True),
    StructField("tags", ArrayType(StringType()), nullable=True),
    StructField("source_feed", StringType(), nullable=True),
])

silver_config_changes = StructType([
    StructField("tool_name", StringType(), nullable=False),
    StructField("from_version", StringType(), nullable=False),
    StructField("to_version", StringType(), nullable=False),
    StructField("param_name", StringType(), nullable=False),
    StructField("old_default", StringType(), nullable=True),
    StructField("new_default", StringType(), nullable=True),
    StructField("change_type", StringType(), nullable=False),
    StructField("impact_level", StringType(), nullable=False),
    StructField("source_url", StringType(), nullable=True),
    StructField("processed_at", TimestampType(), nullable=False),
])

# =============================================================================
# 3. Gold Layer — Aggregated / business-ready
# =============================================================================

gold_tool_summary = StructType([
    StructField("tool_name", StringType(), nullable=False),
    StructField("latest_version", StringType(), nullable=True),
    StructField("eol_date", DateType(), nullable=True),
    StructField("eos_date", DateType(), nullable=True),
    StructField("total_cve_critical", IntegerType(), nullable=False),
    StructField("total_cve_high", IntegerType(), nullable=False),
    StructField("last_updated", TimestampType(), nullable=False),
])

# =============================================================================
# Registry — tên bảng → (layer, schema)
# =============================================================================

_TABLE_REGISTRY: Dict[str, tuple[str, StructType]] = {
    "bronze_raw_releases":      ("bronze", bronze_raw_releases),
    "silver_releases":          ("silver", silver_releases),
    "silver_cves":              ("silver", silver_cves),
    "silver_compatibility":     ("silver", silver_compatibility),
    "silver_license_changes":   ("silver", silver_license_changes),
    "silver_blogs":             ("silver", silver_blogs),
    "silver_config_changes":    ("silver", silver_config_changes),
    "gold_tool_summary":        ("gold",   gold_tool_summary),
}

#: Public schema dict — truy cập nhanh: ``SCHEMAS["silver_cves"]``
SCHEMAS: Dict[str, StructType] = {
    name: schema for name, (_, schema) in _TABLE_REGISTRY.items()
}


# =============================================================================
# Table creation
# =============================================================================

def _get_bucket(layer: str) -> str:
    """Đọc bucket name từ env, fallback về tên layer."""
    env_map = {
        "bronze": "MINIO_BUCKET_BRONZE",
        "silver": "MINIO_BUCKET_SILVER",
        "gold":   "MINIO_BUCKET_GOLD",
    }
    return os.environ.get(env_map[layer], layer)


def _table_path(layer: str, table_name: str) -> str:
    """Tạo s3a:// path cho bảng Delta. KHÔNG hardcode filesystem path."""
    bucket = _get_bucket(layer)
    return f"s3a://{bucket}/{table_name}/"


def create_delta_tables(spark: SparkSession) -> Dict[str, str]:
    """Tạo tất cả Delta tables nếu chưa tồn tại trên MinIO.

    Parameters
    ----------
    spark : SparkSession
        Session đã cấu hình S3A (xem ``processing.spark_utils.session``).

    Returns
    -------
    dict[str, str]
        Mapping ``{table_name: s3a_path}`` cho các bảng đã được tạo/xác nhận.

    Notes
    -----
    - Idempotent: gọi nhiều lần không lỗi (dùng mode ``ignore``).
    - Chỉ tạo bảng trống với schema đúng; KHÔNG ghi đè dữ liệu có sẵn.
    """
    created: Dict[str, str] = {}

    for table_name, (layer, schema) in _TABLE_REGISTRY.items():
        path = _table_path(layer, table_name)
        logger.info("Ensuring Delta table: %s → %s", table_name, path)

        try:
            # Tạo DataFrame rỗng với schema đúng, ghi mode=ignore
            # → bỏ qua nếu path đã có dữ liệu Delta
            empty_df = spark.createDataFrame([], schema)
            (
                empty_df.write
                .format("delta")
                .mode("ignore")          # skip nếu đã tồn tại
                .option("mergeSchema", "true")
                .save(path)
            )
            created[table_name] = path
            logger.info("  ✓ %s ready", table_name)

        except Exception:
            logger.exception("  ✗ Failed to create %s at %s", table_name, path)
            raise

    logger.info(
        "Delta table init complete: %d/%d tables ready",
        len(created),
        len(_TABLE_REGISTRY),
    )
    return created
