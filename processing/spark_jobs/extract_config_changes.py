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
from typing import List, Dict, Any

from pyspark.sql import Window
from pyspark.sql import functions as F
from pyspark.sql.types import StructType, StringType

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
        df_raw = spark.read.format("delta").load(bronze_path).filter(F.col("tool_name") == tool)
    except Exception as e:
        logger.error(f"Cannot read bronze_raw_releases: {e}")
        return

    if df_raw.rdd.isEmpty():
        logger.info(f"No releases found for tool {tool}.")
        spark.stop()
        return

    # Semantic version sorting via UDF to establish from_version
    def version_tuple(v):
        import re
        if not v:
            return (0, 0, 0)
        m = re.match(r"^\D*(\d+)\.(\d+)(\.(\d+))?", str(v))
        if m:
            return (int(m.group(1)), int(m.group(2)), int(m.group(4) or 0))
        return (0, 0, 0)
        
    def semver_sort_key(v):
        vt = version_tuple(v)
        return f"{vt[0]:05d}.{vt[1]:05d}.{vt[2]:05d}"
        
    udf_semver_key = F.udf(semver_sort_key, StringType())
    
    df_raw = df_raw.withColumn("_semver_key", udf_semver_key("version"))
    window_spec = Window.partitionBy("tool_name").orderBy("_semver_key")
    df_raw = df_raw.withColumn("from_version", F.lag("version", 1, "unknown").over(window_spec))

    # Parse JSON safely
    from pyspark.sql.types import StructField, StringType, ArrayType
    
    json_schema = StructType([StructField("body", StringType())])
    df_raw = df_raw.withColumn("parsed_json", F.from_json(F.col("raw_json"), json_schema))
    
    # Track parse errors
    df_raw = df_raw.withColumn("_parse_error", 
        F.when(F.col("parsed_json").isNull() & F.col("raw_json").isNotNull() & (F.length(F.col("raw_json")) > 0), 
               F.lit("JSON Parse Error"))
         .otherwise(F.lit(None))
    )
    
    df_raw = df_raw.withColumn("body", F.col("parsed_json.body"))
    
    # UDF to extract changes using Python regex
    def extract_regex_changes(body_text):
        if not body_text:
            return []
        
        changes = []
        try:
            for m in P1.finditer(body_text):
                param = m.group(1)
                impact = "High" if "security" in param.lower() or "auth" in param.lower() else "Medium"
                changes.append((param, m.group(2), m.group(3), "changed_default", impact))
                
            for m in P2.finditer(body_text):
                param = m.group(1)
                impact = "High" if "security" in param.lower() else "Low"
                changes.append((param, None, m.group(2), "new_param", impact))
                
            for m in P3.finditer(body_text):
                changes.append((m.group(1), None, None, "deprecated", "Low"))
        except Exception:
            pass
        return changes

    change_schema = ArrayType(StructType([
        StructField("param_name", StringType()),
        StructField("old_default", StringType()),
        StructField("new_default", StringType()),
        StructField("change_type", StringType()),
        StructField("impact_level", StringType())
    ]))
    
    udf_extract = F.udf(extract_regex_changes, change_schema)
    
    df_extracted = df_raw.withColumn("changes_array", udf_extract("body"))
    
    # Log errors (if any)
    error_count = df_raw.filter(F.col("_parse_error").isNotNull()).count()
    if error_count > 0:
        logger.warning(f"Found {error_count} records with JSON parse errors for {tool}.")

    # Explode the array
    df_exploded = df_extracted.select(
        "tool_name",
        "from_version",
        F.col("version").alias("to_version"),
        "source_url",
        F.explode_outer("changes_array").alias("change")
    ).filter(F.col("change").isNotNull())
    
    df_changes = df_exploded.select(
        "tool_name",
        "from_version",
        "to_version",
        F.col("change.param_name").alias("param_name"),
        F.col("change.old_default").alias("old_default"),
        F.col("change.new_default").alias("new_default"),
        F.col("change.change_type").alias("change_type"),
        F.col("change.impact_level").alias("impact_level"),
        "source_url"
    ).withColumn("processed_at", F.current_timestamp())

    # Add manual overrides
    manual_changes = _load_manual_overrides(tool)
    if manual_changes:
        manual_df = spark.createDataFrame(manual_changes, schema=SCHEMAS["silver_config_changes"])
        df_changes = df_changes.unionByName(manual_df, allowMissingColumns=True)

    if df_changes.rdd.isEmpty():
        logger.info(f"No config changes found for {tool}.")
        spark.stop()
        return
    
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
