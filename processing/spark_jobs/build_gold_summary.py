"""
DataStack Compass — Build Gold Tool Summary
============================================

PySpark job tổng hợp dữ liệu từ Silver → Gold layer.
Join silver_releases + silver_cves, tính CVE counts, xác định latest version
theo semantic versioning, enrich với EOL/EOS dates, ghi vào gold_tool_summary.

Chạy sau khi tất cả silver data đã được cập nhật (thường cuối pipeline).

Usage
-----
    # Standalone
    spark-submit processing/spark_jobs/build_gold_summary.py

    # Từ Python / Airflow
    from processing.spark_jobs.build_gold_summary import build_gold_tool_summary
    build_gold_tool_summary(spark)

Output
------
    s3a://gold/gold_tool_summary/  (Delta Lake format)

    StarRocks có thể query trực tiếp qua External Catalog mà KHÔNG cần
    ETL thêm — xem ``print_starrocks_catalog_sql()`` ở cuối file.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Dict, List, Optional, Tuple

import argparse
from pyspark.sql import DataFrame, Row, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DateType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

# ─── Project root ────────────────────────────────────────────────────────────
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from processing.spark_utils.session import get_spark_session
from storage.delta.schemas import SCHEMAS

# =============================================================================
# Logging
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("build_gold_summary")


# =============================================================================
# S3A paths
# =============================================================================

def _silver_releases_path() -> str:
    bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
    return f"s3a://{bucket}/silver_releases/"


def _silver_cves_path() -> str:
    bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
    return f"s3a://{bucket}/silver_cves/"


def _gold_summary_path() -> str:
    bucket = os.environ.get("MINIO_BUCKET_GOLD", "gold")
    return f"s3a://{bucket}/gold_tool_summary/"


def _eol_database_path() -> str:
    """Path tới file EOL database JSON. Đọc từ env hoặc default."""
    return os.environ.get(
        "EOL_DATABASE_PATH",
        os.path.join(_PROJECT_ROOT, "configs", "eol_database.json"),
    )


# =============================================================================
# Semantic version sorting
# =============================================================================

def parse_semver_tuple(version: Optional[str]) -> Tuple[int, ...]:
    """Parse version string thành tuple of ints cho comparison.

    Examples
    --------
    >>> parse_semver_tuple("3.7.1")
    (3, 7, 1)
    >>> parse_semver_tuple("3.7")
    (3, 7, 0)
    >>> parse_semver_tuple("3.7.1-rc1")
    (3, 7, 1)
    >>> parse_semver_tuple(None)
    (0, 0, 0)
    """
    if not version:
        return (0, 0, 0)

    # Strip prefix "v" và prerelease suffix
    cleaned = version.strip().lstrip("vV")
    # Lấy phần trước dấu "-" (loại bỏ prerelease tag)
    base = cleaned.split("-")[0]

    parts = base.split(".")
    result: List[int] = []

    for part in parts[:3]:  # Chỉ lấy MAJOR.MINOR.PATCH
        try:
            result.append(int(part))
        except ValueError:
            result.append(0)

    # Pad to 3 elements
    while len(result) < 3:
        result.append(0)

    return tuple(result)


def semver_sort_key(version: Optional[str]) -> str:
    """Tạo sort key string cho semantic version ordering.

    Trả về zero-padded string để Spark có thể sort alphabetically
    mà vẫn đúng thứ tự semantic version.

    Examples
    --------
    >>> semver_sort_key("3.7.1")
    '00003.00007.00001'
    >>> semver_sort_key("10.0.0")
    '00010.00000.00000'
    """
    parts = parse_semver_tuple(version)
    return ".".join(f"{p:05d}" for p in parts)


# Register UDF
_udf_semver_sort_key = F.udf(semver_sort_key, StringType())


# =============================================================================
# EOL database loader
# =============================================================================

def load_eol_database(spark: SparkSession) -> DataFrame:
    """Load EOL/EOS dates từ file JSON tĩnh vào DataFrame.

    Returns
    -------
    DataFrame
        Columns: tool_name, eol_date, eos_date
    """
    eol_path = _eol_database_path()
    logger.info("Loading EOL database from %s", eol_path)

    try:
        with open(eol_path, "r", encoding="utf-8") as f:
            eol_data = json.load(f)
    except FileNotFoundError:
        logger.warning("EOL database not found at %s — using empty defaults", eol_path)
        return spark.createDataFrame(
            [],
            StructType([
                StructField("tool_name", StringType(), nullable=False),
                StructField("eol_date", DateType(), nullable=True),
                StructField("eos_date", DateType(), nullable=True),
            ]),
        )

    tools = eol_data.get("tools", {})
    rows = []
    for tool_name, info in tools.items():
        rows.append(Row(
            tool_name=tool_name,
            eol_date=info.get("eol_date"),
            eos_date=info.get("eos_date"),
        ))

    if not rows:
        return spark.createDataFrame(
            [],
            StructType([
                StructField("tool_name", StringType()),
                StructField("eol_date", StringType()),
                StructField("eos_date", StringType()),
            ]),
        )

    eol_df = spark.createDataFrame(rows)

    # Cast string dates → DateType
    eol_df = (
        eol_df
        .withColumn("eol_date", F.to_date(F.col("eol_date"), "yyyy-MM-dd"))
        .withColumn("eos_date", F.to_date(F.col("eos_date"), "yyyy-MM-dd"))
    )

    logger.info("  Loaded EOL data for %d tools", len(rows))
    return eol_df


# =============================================================================
# Core function
# =============================================================================

def build_gold_tool_summary(spark: SparkSession) -> Dict[str, int]:
    """Tổng hợp Silver → Gold tool summary.

    Steps
    -----
    1. Read silver_releases + silver_cves
    2. Tính latest_version dùng semantic version ordering
    3. Count CVEs by severity
    4. Join EOL/EOS dates
    5. Delta MERGE upsert vào gold_tool_summary

    Parameters
    ----------
    spark : SparkSession
        Session đã cấu hình S3A + Delta Lake.

    Returns
    -------
    dict[str, int]
        Statistics: ``{tools_processed, cves_counted}``.
    """
    from delta.tables import DeltaTable

    silver_rel_path = _silver_releases_path()
    silver_cve_path = _silver_cves_path()
    gold_path = _gold_summary_path()

    logger.info(
        "═══ Build Gold Tool Summary ═══\n"
        "  Silver releases : %s\n"
        "  Silver CVEs     : %s\n"
        "  Gold output     : %s",
        silver_rel_path,
        silver_cve_path,
        gold_path,
    )

    # ─── Step 1: Read Silver tables ──────────────────────────────────────
    logger.info("Step 1/5 — Reading silver tables")

    try:
        releases_df = spark.read.format("delta").load(silver_rel_path)
        logger.info("  silver_releases: %d rows", releases_df.count())
    except Exception as exc:
        logger.error("Cannot read silver_releases at %s: %s", silver_rel_path, exc)
        raise

    # silver_cves có thể chưa tồn tại nếu chưa có CVE data
    try:
        cves_df = spark.read.format("delta").load(silver_cve_path)
        cve_count = cves_df.count()
        logger.info("  silver_cves: %d rows", cve_count)
    except Exception:
        logger.warning("  silver_cves not found — proceeding with zero CVE counts")
        cves_df = spark.createDataFrame([], SCHEMAS["silver_cves"])
        cve_count = 0

    # ─── Step 2: Tính latest_version bằng semantic version sort ──────────
    logger.info("Step 2/5 — Computing latest version per tool (semantic sort)")

    # Thêm sort key column, tìm MAX theo sort key
    releases_with_key = releases_df.withColumn(
        "_semver_key",
        _udf_semver_sort_key(F.col("version")),
    )

    # Window function: lấy version có sort key cao nhất per tool
    from pyspark.sql.window import Window

    w = Window.partitionBy("tool_name").orderBy(F.col("_semver_key").desc())

    latest_versions_df = (
        releases_with_key
        .withColumn("_rank", F.row_number().over(w))
        .filter(F.col("_rank") == 1)
        .select(
            F.col("tool_name"),
            F.col("version").alias("latest_version"),
        )
    )

    logger.info("  Computed latest versions for %d tools", latest_versions_df.count())

    # ─── Step 3: Count CVEs by severity ──────────────────────────────────
    logger.info("Step 3/5 — Counting CVEs by severity")

    if cve_count > 0:
        cve_counts_df = (
            cves_df.groupBy("tool_name")
            .agg(
                F.count(
                    F.when(F.col("severity") == "Critical", 1)
                ).alias("total_cve_critical"),
                F.count(
                    F.when(F.col("severity") == "High", 1)
                ).alias("total_cve_high"),
            )
        )
    else:
        cve_counts_df = spark.createDataFrame(
            [],
            StructType([
                StructField("tool_name", StringType()),
                StructField("total_cve_critical", IntegerType()),
                StructField("total_cve_high", IntegerType()),
            ]),
        )

    # ─── Step 4: Join latest versions + CVE counts + EOL dates ───────────
    logger.info("Step 4/5 — Joining datasets")

    # Join releases ← CVE counts
    summary_df = (
        latest_versions_df
        .join(cve_counts_df, on="tool_name", how="left")
        .fillna(0, subset=["total_cve_critical", "total_cve_high"])
    )

    # Join ← EOL database
    eol_df = load_eol_database(spark)

    if eol_df.count() > 0:
        summary_df = summary_df.join(eol_df, on="tool_name", how="left")
    else:
        summary_df = (
            summary_df
            .withColumn("eol_date", F.lit(None).cast(DateType()))
            .withColumn("eos_date", F.lit(None).cast(DateType()))
        )

    # Add last_updated timestamp
    summary_df = summary_df.withColumn(
        "last_updated",
        F.current_timestamp(),
    )

    # Ensure column order matches gold schema
    gold_df = summary_df.select(
        F.col("tool_name"),
        F.col("latest_version"),
        F.col("eol_date"),
        F.col("eos_date"),
        F.col("total_cve_critical").cast(IntegerType()),
        F.col("total_cve_high").cast(IntegerType()),
        F.col("last_updated"),
    )

    tools_processed = gold_df.count()
    logger.info("  Gold summary: %d tools", tools_processed)

    # ─── Step 5: Delta MERGE upsert ─────────────────────────────────────
    logger.info("Step 5/5 — Upserting into gold_tool_summary at %s", gold_path)

    if DeltaTable.isDeltaTable(spark, gold_path):
        delta_table = DeltaTable.forPath(spark, gold_path)

        (
            delta_table.alias("target")
            .merge(
                gold_df.alias("source"),
                "target.tool_name = source.tool_name",
            )
            .whenMatchedUpdate(set={
                "latest_version": "source.latest_version",
                "eol_date": "source.eol_date",
                "eos_date": "source.eos_date",
                "total_cve_critical": "source.total_cve_critical",
                "total_cve_high": "source.total_cve_high",
                "last_updated": "source.last_updated",
            })
            .whenNotMatchedInsertAll()
            .execute()
        )
        logger.info("  ✓ Merged %d tools into existing gold_tool_summary", tools_processed)
    else:
        gold_df.write.format("delta").mode("overwrite").save(gold_path)
        logger.info("  ✓ Created gold_tool_summary with %d tools", tools_processed)

    stats = {
        "tools_processed": tools_processed,
        "cves_counted": cve_count,
    }

    logger.info(
        "═══ Gold Summary Complete ═══\n"
        "  Tools processed : %d\n"
        "  CVEs counted    : %d\n"
        "═════════════════════════════",
        stats["tools_processed"],
        stats["cves_counted"],
    )

    return stats


# =============================================================================
# StarRocks External Catalog SQL
# =============================================================================

def print_starrocks_catalog_sql() -> str:
    """In ra SQL statements để tạo StarRocks External Catalog cho Delta Lake.

    Tại sao External Catalog?
    ─────────────────────────
    StarRocks External Catalog cho phép query trực tiếp Delta Lake files trên
    MinIO mà KHÔNG cần ETL thêm. Nghĩa là:

    1. FastAPI backend chỉ cần query StarRocks bằng SQL thông thường:
       ``SELECT * FROM minio_catalog.gold.tool_summary WHERE tool_name = 'kafka'``

    2. Không cần pipeline riêng để sync dữ liệu từ Delta Lake → StarRocks.
       StarRocks đọc Delta Lake metadata (transaction log) trực tiếp và
       trả về kết quả realtime.

    3. Giảm data duplication: chỉ có 1 bản dữ liệu duy nhất trên MinIO,
       cả Spark lẫn StarRocks đều đọc cùng nguồn.

    4. Schema evolution tự động: khi Spark thay đổi schema (thêm cột),
       StarRocks External Catalog tự nhận diện schema mới.

    Trong production, approach này giúp FastAPI query với latency thấp (~ms)
    mà vẫn giữ Delta Lake làm single source of truth cho toàn bộ Lakehouse.
    """
    minio_endpoint = os.environ.get("MINIO_ENDPOINT", "http://localhost:9000")
    minio_access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    gold_bucket = os.environ.get("MINIO_BUCKET_GOLD", "gold")

    sql_statements = f"""
-- =============================================================================
-- StarRocks External Catalog — Delta Lake trên MinIO
-- =============================================================================
-- Chạy các lệnh SQL này trên StarRocks (mysql -h 127.0.0.1 -P 9030 -u root)
--
-- External Catalog cho phép StarRocks query trực tiếp Delta Lake files
-- mà KHÔNG cần ETL thêm. FastAPI backend chỉ cần:
--   SELECT * FROM minio_catalog.gold.gold_tool_summary WHERE tool_name = 'kafka'
-- =============================================================================

-- 1. Tạo External Catalog kết nối MinIO
CREATE EXTERNAL CATALOG IF NOT EXISTS minio_catalog
PROPERTIES (
    "type"                          = "deltalake",
    "hive.metastore.type"           = "glue",
    "aws.s3.enable_path_style_access" = "true",
    "aws.s3.endpoint"               = "{minio_endpoint}",
    "aws.s3.access_key"             = "{minio_access_key}",
    "aws.s3.secret_key"             = "{minio_secret_key}",
    "aws.s3.enable_ssl"             = "false"
);

-- 2. Tạo database trong catalog (mapping tới bucket)
CREATE DATABASE IF NOT EXISTS minio_catalog.gold;

-- 3. Tạo external table trỏ tới gold_tool_summary Delta Lake
CREATE EXTERNAL TABLE IF NOT EXISTS minio_catalog.gold.gold_tool_summary (
    tool_name           VARCHAR(100)    NOT NULL    COMMENT 'Tên tool (e.g. apache-kafka)',
    latest_version      VARCHAR(50)                 COMMENT 'Version mới nhất (semantic versioning)',
    eol_date            DATE                        COMMENT 'End-of-Life date',
    eos_date            DATE                        COMMENT 'End-of-Sale date',
    total_cve_critical  INT             NOT NULL    COMMENT 'Tổng CVE severity Critical',
    total_cve_high      INT             NOT NULL    COMMENT 'Tổng CVE severity High',
    last_updated        DATETIME        NOT NULL    COMMENT 'Thời điểm cập nhật cuối'
)
ENGINE = deltalake
PROPERTIES (
    "location" = "s3a://{gold_bucket}/gold_tool_summary/"
);

-- 4. Verify
SELECT * FROM minio_catalog.gold.gold_tool_summary ORDER BY total_cve_critical DESC;

-- =============================================================================
-- Silver layer tables (optional — nếu FastAPI cần query chi tiết)
-- =============================================================================

CREATE DATABASE IF NOT EXISTS minio_catalog.silver;

CREATE EXTERNAL TABLE IF NOT EXISTS minio_catalog.silver.silver_releases (
    tool_name           VARCHAR(100)    NOT NULL,
    version             VARCHAR(50)     NOT NULL,
    release_date        DATE,
    breaking_changes    JSON,
    deprecated_apis     JSON,
    processed_at        DATETIME        NOT NULL
)
ENGINE = deltalake
PROPERTIES (
    "location" = "s3a://silver/silver_releases/"
);

CREATE EXTERNAL TABLE IF NOT EXISTS minio_catalog.silver.silver_cves (
    cve_id              VARCHAR(30)     NOT NULL,
    tool_name           VARCHAR(100)    NOT NULL,
    affected_versions   JSON            NOT NULL,
    fixed_in_version    VARCHAR(50),
    cvss_score          FLOAT,
    severity            VARCHAR(10)     NOT NULL,
    description         VARCHAR(4000),
    published_at        DATETIME
)
ENGINE = deltalake
PROPERTIES (
    "location" = "s3a://silver/silver_cves/"
);
"""

    logger.info("StarRocks External Catalog SQL:\n%s", sql_statements)
    return sql_statements


# =============================================================================
# CLI entrypoint
# =============================================================================

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Gold Tool Summary")
    parser.add_argument("--date", default=None, help="Filter run by date (YYYY-MM-DD)")
    parser.add_argument("--tool", default=None, help="Specific tool to update")
    return parser.parse_args(argv)

def main(argv: Optional[List[str]] = None) -> Dict[str, int]:
    """Entrypoint: tạo Spark session, build gold summary, print StarRocks SQL."""
    args = parse_args(argv)
    logger.info(f"Starting build_gold_tool_summary with args: {args}")

    spark = get_spark_session("build-gold-summary")

    try:
        stats = build_gold_tool_summary(spark)

        # Print StarRocks SQL sau khi gold table đã sẵn sàng
        print_starrocks_catalog_sql()

        return stats
    finally:
        spark.stop()
        logger.info("SparkSession stopped")


if __name__ == "__main__":
    main()
