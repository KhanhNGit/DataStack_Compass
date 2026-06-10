CREATE DATABASE IF NOT EXISTS datastack_compass;
USE datastack_compass;

CREATE TABLE IF NOT EXISTS asset_inventory (
    id BIGINT,
    tool_name VARCHAR(255) NOT NULL,
    version_in_use VARCHAR(50) NOT NULL,
    owner_email VARCHAR(255) NOT NULL,
    team_name VARCHAR(255) NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
) ENGINE=OLAP
PRIMARY KEY(id)
DISTRIBUTED BY HASH(id) BUCKETS 1
PROPERTIES (
    "replication_num" = "1"
);
