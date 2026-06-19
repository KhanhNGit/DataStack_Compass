#!/usr/bin/env python3
"""
DataStack Compass — Spark Job: Transform CVEs
=================================================

Đọc raw JSON từ Bronze (cvelistV5), parse thông tin và ghi vào Silver.
"""

import logging
import os
import sys
import json
from datetime import datetime

from pyspark.sql import SparkSession, Row
from pyspark.sql.types import *
import pyspark.sql.functions as F

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from storage.delta.schemas import SCHEMAS
from processing.spark_utils.session import get_spark_session
from packaging.version import parse as parse_version, InvalidVersion

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("transform_cves")

def load_products_catalog() -> list:
    catalog_path = os.path.join(_PROJECT_ROOT, "configs", "products_catalog.json")
    with open(catalog_path, "r", encoding="utf-8") as f:
        return json.load(f)

def is_version_in_range(v_str: str, from_v: str, to_v: str, from_incl: bool, to_incl: bool) -> bool:
    try:
        v = parse_version(v_str)
        
        if from_v:
            f = parse_version(from_v)
            if from_incl and v < f: return False
            if not from_incl and v <= f: return False
            
        if to_v:
            t = parse_version(to_v)
            if to_incl and v > t: return False
            if not to_incl and v >= t: return False
            
        return True
    except InvalidVersion:
        # Fallback to string comparison if not semver
        if from_v and v_str < from_v: return False
        if to_v and v_str > to_v: return False
        return True

def parse_cve_json(raw_json: str, catalog: list, tool_releases: dict):
    try:
        data = json.loads(raw_json)
        cve_id = data.get("cveMetadata", {}).get("cveId")
        if not cve_id:
            return []
            
        cna = data.get("containers", {}).get("cna", {})
        adps = data.get("containers", {}).get("adp", [])
        
        # Determine CVSS and Severity from CNA or ADP
        cvss_score = None
        severity = "Low"
        
        # Check CNA metrics
        metrics = cna.get("metrics", [])
        for adp in adps:
            metrics.extend(adp.get("metrics", []))
            
        for m in metrics:
            for cvss_key in ["cvssV3_1", "cvssV3_0", "cvssV2", "cvssV4_0"]:
                if cvss_key in m:
                    cvss_score = m[cvss_key].get("baseScore")
                    severity = m[cvss_key].get("baseSeverity", "Low").capitalize()
                    break
            if cvss_score: break
            
        # Parse descriptions
        desc = ""
        for d in cna.get("descriptions", []):
            if d.get("lang") == "en":
                desc = d.get("value", "")
                break
                
        # Parse affected products
        affected = cna.get("affected", [])
        
        results = []
        for product in catalog:
            tool_name = product["product_id"]
            aliases = [a.lower() for a in product.get("aliases", [])]
            vendor_expected = product.get("vendor", "").lower()
            
            is_match = False
            matched_versions = []
            matched_ranges = []
            
            for aff in affected:
                v_name = aff.get("vendor", "").lower()
                p_name = aff.get("product", "").lower()
                
                # Rule 2: CNA Match
                if p_name in aliases or p_name == tool_name:
                    is_match = True
                elif any(a in desc.lower() for a in aliases):
                    # Rule 3: Description Match (fallback)
                    is_match = True
                    
                if is_match:
                    for v_info in aff.get("versions", []):
                        v_status = v_info.get("status", "affected")
                        if v_status != "affected":
                            continue
                            
                        v_start = v_info.get("version")
                        if v_start == "n/a" or v_start == "unspecified":
                            v_start = None
                            
                        v_end = None
                        to_inclusive = False
                        
                        if "lessThan" in v_info:
                            v_end = v_info["lessThan"]
                            to_inclusive = False
                        elif "lessThanOrEqual" in v_info:
                            v_end = v_info["lessThanOrEqual"]
                            to_inclusive = True
                            
                        matched_ranges.append({
                            "from_version": v_start,
                            "to_version": v_end,
                            "from_inclusive": True,
                            "to_inclusive": to_inclusive
                        })
            
            if is_match:
                # Map ranges to concrete versions from silver_releases
                known_versions = tool_releases.get(tool_name, [])
                for r in matched_ranges:
                    for kv in known_versions:
                        if is_version_in_range(kv, r["from_version"], r["to_version"], r["from_inclusive"], r["to_inclusive"]):
                            if kv not in matched_versions:
                                matched_versions.append(kv)
                                
                results.append(Row(
                    cve_id=cve_id,
                    tool_name=tool_name,
                    description=desc[:4000],
                    severity=severity,
                    cvss_score=float(cvss_score) if cvss_score else None,
                    cwe=[p.get("cweId") for prob in cna.get("problemTypes", []) for p in prob.get("descriptions", []) if "cweId" in p],
                    affected_ranges=matched_ranges,
                    affected_versions=matched_versions,
                    references=[ref.get("url") for ref in cna.get("references", [])],
                    published_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                ))
                
        return results
    except Exception as e:
        logger.error(f"Error parsing JSON: {e}")
        return []

def main():
    logger.info("Starting transform_cves job")
    spark = get_spark_session("transform_cves")
    
    catalog = load_products_catalog()
    
    # Load known tool releases
    tool_releases = {}
    try:
        df_rels = spark.read.table("local.silver.silver_releases")
        rows = df_rels.select("tool_name", "version").distinct().collect()
        for r in rows:
            tool_releases.setdefault(r.tool_name, []).append(r.version)
    except Exception as e:
        logger.warning(f"Could not load silver_releases: {e}")

    # Load JSONL
    bucket = os.environ.get("MINIO_BUCKET_BRONZE", "compass-lake")
    raw_path = f"s3a://{bucket}/bronze/bronze_cves/cvelistV5.jsonl"
    
    try:
        raw_df = spark.read.text(raw_path)
    except Exception as e:
        logger.error(f"Failed to read {raw_path}: {e}")
        spark.stop()
        sys.exit(1)
        
    logger.info(f"Loaded {raw_df.count()} raw CVEs")
    
    # Process
    all_rows = []
    catalog_b = spark.sparkContext.broadcast(catalog)
    tool_rels_b = spark.sparkContext.broadcast(tool_releases)
    
    def process_partition(iterator):
        cat = catalog_b.value
        rels = tool_rels_b.value
        res = []
        for row in iterator:
            res.extend(parse_cve_json(row.value, cat, rels))
        return iter(res)
        
    rdd = raw_df.rdd.mapPartitions(process_partition)
    
    schema = SCHEMAS["silver_cves"]
    if rdd.isEmpty():
        logger.info("No matching CVEs found.")
        spark.stop()
        return
        
    silver_df = spark.createDataFrame(rdd, schema)
    
    table_id = "local.silver.silver_cves"
    table_exists = False
    try:
        spark.read.table(table_id)
        table_exists = True
    except Exception:
        pass
        
    if table_exists:
        silver_df.createOrReplaceTempView("source")
        spark.sql(f"""
            MERGE INTO {table_id} target
            USING source
            ON target.cve_id = source.cve_id AND target.tool_name = source.tool_name
            WHEN MATCHED THEN UPDATE SET *
            WHEN NOT MATCHED THEN INSERT *
        """)
    else:
        silver_df.writeTo(table_id).createOrReplace()
        
    logger.info(f"Successfully upserted {silver_df.count()} CVEs.")
    spark.stop()

if __name__ == "__main__":
    main()
