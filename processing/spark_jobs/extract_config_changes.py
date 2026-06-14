"""
DataStack Compass — Extract Config Changes
==========================================

Job Spark đọc raw_json từ bronze_raw_releases, trích xuất config changes thông qua 
regex patterns trên Markdown text. Hỗ trợ ghi đè qua `configs/config_changes_manual/`.
"""

import argparse
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import List, Dict, Any

from pyspark.sql import SparkSession, Row
from pyspark.sql.types import StructType

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from processing.spark_utils.session import get_spark_session
from storage.delta.schemas import SCHEMAS

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("extract_config_changes")

# Patterns
# Pattern 1: "The default value of {param} has changed from {old} to {new}"
P1 = re.compile(r"The default value of `?([^`\s]+)`? has changed from `?([^`\s]+)`? to `?([^`\s]+)`?", re.IGNORECASE)

# Pattern 2: "New configuration: {param} (default: {value})"
P2 = re.compile(r"New configuration:\s*`?([^`\s]+)`?\s*\(default:\s*`?([^`\s\)]+)`?\)", re.IGNORECASE)

# Pattern 3: "Deprecated: {param} will be removed"
P3 = re.compile(r"Deprecated:\s*`?([^`\s]+)`?\s*will be removed", re.IGNORECASE)

def _load_manual_overrides(tool_name: str) -> List[Dict[str, Any]]:
    path = os.path.join(_PROJECT_ROOT, "configs", "config_changes_manual", f"{tool_name}.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load manual overrides for {tool_name}: {e}")
    return []

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool-name", required=True)
    args = parser.parse_args()
    
    tool = args.tool_name
    spark = get_spark_session("extract_config_changes")
    
    # 1. Read Bronze raw releases
    bronze_bucket = os.environ.get("MINIO_BUCKET_BRONZE", "bronze")
    bronze_path = f"s3a://{bronze_bucket}/bronze_raw_releases/"
    
    try:
        df_raw = spark.read.format("delta").load(bronze_path).filter(f"tool_name = '{tool}'").collect()
    except Exception as e:
        logger.error(f"Cannot read bronze_raw_releases: {e}")
        return
        
    # Sort versions
    def version_tuple(v):
        import re
        m = re.match(r"^\D*(\d+)\.(\d+)(\.(\d+))?", v)
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(4) or 0))
        return (0, 0, 0)
        
    df_raw = sorted(df_raw, key=lambda x: version_tuple(x.version))
    
    extracted_changes = []
    
    # Manual overrides
    manual_changes = _load_manual_overrides(tool)
    for mc in manual_changes:
        extracted_changes.append({
            "tool_name": tool,
            "from_version": mc["from_version"],
            "to_version": mc["to_version"],
            "param_name": mc["param_name"],
            "old_default": mc.get("old_default"),
            "new_default": mc.get("new_default"),
            "change_type": mc["change_type"],
            "impact_level": mc.get("impact_level", "Low"),
            "source_url": mc.get("source_url", ""),
            "processed_at": datetime.now(timezone.utc)
        })

    prev_version = "unknown"
    for row in df_raw:
        ver = row.version
        raw_json_str = row.raw_json
        
        try:
            raw_json = json.loads(raw_json_str)
            body = raw_json.get("body", "")
            
            # P1
            for m in P1.finditer(body):
                extracted_changes.append({
                    "tool_name": tool,
                    "from_version": prev_version,
                    "to_version": ver,
                    "param_name": m.group(1),
                    "old_default": m.group(2),
                    "new_default": m.group(3),
                    "change_type": "changed_default",
                    "impact_level": "High" if "security" in m.group(1).lower() or "auth" in m.group(1).lower() else "Medium",
                    "source_url": row.source_url,
                    "processed_at": datetime.now(timezone.utc)
                })
                
            # P2
            for m in P2.finditer(body):
                extracted_changes.append({
                    "tool_name": tool,
                    "from_version": prev_version,
                    "to_version": ver,
                    "param_name": m.group(1),
                    "old_default": None,
                    "new_default": m.group(2),
                    "change_type": "new_param",
                    "impact_level": "High" if "security" in m.group(1).lower() else "Low",
                    "source_url": row.source_url,
                    "processed_at": datetime.now(timezone.utc)
                })
                
            # P3
            for m in P3.finditer(body):
                extracted_changes.append({
                    "tool_name": tool,
                    "from_version": prev_version,
                    "to_version": ver,
                    "param_name": m.group(1),
                    "old_default": None,
                    "new_default": None,
                    "change_type": "deprecated",
                    "impact_level": "Low",
                    "source_url": row.source_url,
                    "processed_at": datetime.now(timezone.utc)
                })
        except Exception:
            pass
            
        prev_version = ver
        
    if not extracted_changes:
        logger.info(f"No config changes found for {tool}.")
        spark.stop()
        return
        
    schema = SCHEMAS["silver_config_changes"]
    df_changes = spark.createDataFrame(extracted_changes, schema=schema)
    
    # Delta Merge
    silver_bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
    table_path = f"s3a://{silver_bucket}/silver_config_changes/"
    
    try:
        from delta.tables import DeltaTable
        if DeltaTable.isDeltaTable(spark, table_path):
            dt = DeltaTable.forPath(spark, table_path)
            (
                dt.alias("t").merge(
                    df_changes.alias("s"),
                    "t.tool_name = s.tool_name AND t.from_version = s.from_version AND t.to_version = s.to_version AND t.param_name = s.param_name"
                )
                .whenMatchedUpdateAll()
                .whenNotMatchedInsertAll()
                .execute()
            )
        else:
            df_changes.write.format("delta").mode("overwrite").save(table_path)
        logger.info(f"Successfully upserted {df_changes.count()} config changes for {tool}.")
    except Exception as e:
        logger.error(f"Merge failed: {e}")
        
    spark.stop()

if __name__ == "__main__":
    main()
