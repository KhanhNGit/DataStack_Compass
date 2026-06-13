-- 1. Tạo External Catalog trỏ vào MinIO (Delta Lake format)
CREATE EXTERNAL CATALOG IF NOT EXISTS minio_delta_catalog
PROPERTIES (
    "type" = "deltalake",
    "aws.s3.use_instance_profile" = "false",
    "aws.s3.access_key" = "${MINIO_ACCESS_KEY}",
    "aws.s3.secret_key" = "${MINIO_SECRET_KEY}",
    "aws.s3.endpoint" = "${MINIO_ENDPOINT}",
    "aws.s3.enable_path_style_access" = "true"
);

-- 2. Tạo internal database cho asset inventory và audit logs
CREATE DATABASE IF NOT EXISTS compass_internal;
USE compass_internal;

-- 3. Bảng asset_inventory (internal, NOT external)
CREATE TABLE IF NOT EXISTS asset_inventory (
    id BIGINT AUTO_INCREMENT,
    tool_name VARCHAR(100) NOT NULL,
    version_in_use VARCHAR(50) NOT NULL,
    owner_email VARCHAR(200),
    team_name VARCHAR(100),
    environment VARCHAR(50) DEFAULT 'production',
    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=OLAP
DUPLICATE KEY(id)
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
