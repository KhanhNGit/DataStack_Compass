-- 1. Tạo External Catalog trỏ vào MinIO (Iceberg format)
-- Schema auto-detection: "type"="iceberg" tells StarRocks to read column schemas
-- directly from Iceberg / Parquet metadata. No explicit column DDL is needed for
-- external tables (silver_releases, silver_cves, gold_tool_summary, etc.).
-- Columns like issues, breaking_changes_enriched, deprecated_apis are detected
-- automatically from the Parquet files written by PySpark.
CREATE EXTERNAL CATALOG IF NOT EXISTS minio_iceberg_catalog
PROPERTIES (
    "type" = "iceberg",
    "iceberg.catalog.type" = "hadoop",
    "iceberg.catalog.warehouse" = "s3a://",
    "aws.s3.use_instance_profile" = "false",
    "aws.s3.access_key" = "${MINIO_ACCESS_KEY}",
    "aws.s3.secret_key" = "${MINIO_SECRET_KEY}",
    "aws.s3.endpoint" = "${MINIO_ENDPOINT}",
    "aws.s3.enable_path_style_access" = "true"
);

-- After running this script, verify schema auto-detection with:
-- DESCRIBE minio_iceberg_catalog.silver.silver_releases
-- Expected columns: tool_name, version, release_date, issues, breaking_changes,
--                   breaking_changes_enriched, deprecated_apis, processed_at
-- If columns are missing, check that Iceberg tables were written with the
-- correct schema from storage/delta/schemas.py before this script was run.
--
-- DESCRIBE minio_iceberg_catalog.silver.silver_cves
-- DESCRIBE minio_iceberg_catalog.gold.gold_tool_summary

-- 2. Tạo internal database cho asset inventory và audit logs
CREATE DATABASE IF NOT EXISTS compass_internal;
USE compass_internal;

-- 3. Bảng asset_inventory (internal, NOT external)
CREATE TABLE IF NOT EXISTS asset_inventory (
    tool_name VARCHAR(100) NOT NULL,
    project_name VARCHAR(100) NOT NULL,
    environment VARCHAR(50) DEFAULT 'production',
    department VARCHAR(100),
    team_name VARCHAR(100),
    version_in_use VARCHAR(50) NOT NULL,
    owner_email VARCHAR(200),
    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=OLAP
PRIMARY KEY(tool_name, project_name, environment)
DISTRIBUTED BY HASH(tool_name) BUCKETS 4
PROPERTIES ("replication_num" = "1");

-- 4. Bảng alert_history (lưu lịch sử alerts đã gửi)
CREATE TABLE IF NOT EXISTS alert_history (
    id BIGINT AUTO_INCREMENT,
    alert_type VARCHAR(50),
    tool_name VARCHAR(100),
    cve_ids VARCHAR(2000),
    severity VARCHAR(20),
    recipients VARCHAR(1000),
    sent_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'sent'
) ENGINE=OLAP
DUPLICATE KEY(id)
DISTRIBUTED BY HASH(tool_name) BUCKETS 4
PROPERTIES ("replication_num" = "1");
