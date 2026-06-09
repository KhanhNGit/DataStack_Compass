"""
DataStack Compass — Spark Session Factory
==========================================

Tạo SparkSession đã cấu hình sẵn kết nối MinIO (S3A) và Delta Lake.
Mọi config đọc từ environment variables → portable giữa local và production.

Usage
-----
    from processing.spark_utils.session import get_spark_session

    spark = get_spark_session("my-etl-job")
    df = spark.read.format("delta").load("s3a://bronze/release_notes")
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

# ── Defaults ─────────────────────────────────────────────────────────────────
_DEFAULTS = {
    "SPARK_MASTER": "local[*]",
    "SPARK_DRIVER_MEMORY": "2g",
    "MINIO_ENDPOINT": "http://localhost:9000",
    "MINIO_ACCESS_KEY": "minioadmin",
    "MINIO_SECRET_KEY": "minioadmin",
}


def _env(key: str, default: Optional[str] = None) -> str:
    """Đọc environment variable, fallback về default nếu không set."""
    return os.environ.get(key, default or _DEFAULTS.get(key, ""))


def get_spark_session(app_name: str) -> SparkSession:
    """Tạo (hoặc lấy lại) SparkSession đã cấu hình MinIO + Delta Lake.

    Parameters
    ----------
    app_name : str
        Tên application hiển thị trên Spark UI.

    Returns
    -------
    SparkSession
        Session đã sẵn sàng đọc/ghi s3a:// paths với Delta Lake format.

    Notes
    -----
    - Local dev:  SPARK_MASTER=local[*]  (default)
    - Production: SPARK_MASTER=yarn hoặc k8s://...
    - Chỉ khác giá trị SPARK_MASTER, toàn bộ logic còn lại giữ nguyên.
    """
    spark_master = _env("SPARK_MASTER")
    minio_endpoint = _env("MINIO_ENDPOINT")
    driver_memory = _env("SPARK_DRIVER_MEMORY")

    logger.info(
        "Initializing SparkSession '%s' | master=%s | endpoint=%s | driver_mem=%s",
        app_name,
        spark_master,
        minio_endpoint,
        driver_memory,
    )

    builder = (
        SparkSession.builder
        .appName(app_name)
        .master(spark_master)
        # ── Driver resources ─────────────────────────────────────────────
        .config("spark.driver.memory", driver_memory)
        # ── S3A / MinIO ──────────────────────────────────────────────────
        .config("spark.hadoop.fs.s3a.endpoint", minio_endpoint)
        .config("spark.hadoop.fs.s3a.access.key", _env("MINIO_ACCESS_KEY"))
        .config("spark.hadoop.fs.s3a.secret.key", _env("MINIO_SECRET_KEY"))
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config(
            "spark.hadoop.fs.s3a.impl",
            "org.apache.hadoop.fs.s3a.S3AFileSystem",
        )
        # Tắt SSL cho local MinIO; production có thể override qua env
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        # ── Delta Lake ───────────────────────────────────────────────────
        .config(
            "spark.sql.extensions",
            "io.delta.sql.DeltaSparkSessionExtension",
        )
        .config(
            "spark.sql.catalog.spark_catalog",
            "org.apache.spark.sql.delta.catalog.DeltaCatalog",
        )
        # ── Performance defaults ─────────────────────────────────────────
        .config("spark.sql.shuffle.partitions", "8")
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
    )

    spark = builder.getOrCreate()

    # Log để xác nhận session đã active
    sc = spark.sparkContext
    logger.info(
        "SparkSession ready — version=%s, master=%s, app_id=%s",
        sc.version,
        sc.master,
        sc.applicationId,
    )

    return spark
