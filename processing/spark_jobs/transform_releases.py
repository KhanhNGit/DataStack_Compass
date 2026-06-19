"""
DataStack Compass — Transform Bronze → Silver (Releases)
=========================================================

PySpark job đọc raw release data từ Bronze layer, chuẩn hóa, extract
breaking changes, và ghi vào Silver layer theo Delta Lake format.

Được gọi bởi Airflow DAG ``process_releases`` hoặc chạy standalone:

    spark-submit processing/spark_jobs/transform_releases.py \\
        --tool-name apache-kafka \\
        --date 2024-06-01

Idempotent: Dùng Delta MERGE (upsert) theo key (tool_name, version).
Portable:   Dùng s3a:// paths + env vars — chạy được trên local[*] và YARN/K8s.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import sys
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from pyspark.sql import Row, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    StringType,
    StructField,
    StructType,
)

# ─── Project root trên sys.path ─────────────────────────────────────────────
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from processing.spark_utils.session import get_spark_session
from processing.spark_jobs.classify_breaking_changes import classify_breaking_change_udf
from storage.delta.schemas import SCHEMAS

# =============================================================================
# Logging
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("transform_releases")

# =============================================================================
# Constants
# =============================================================================

# Semantic versioning regex: MAJOR.MINOR[.PATCH][-prerelease]
_SEMVER_REGEX = re.compile(
    r"^\d+\.\d+(\.\d+)?(-[a-zA-Z0-9.]+)?$"
)

# Regex patterns cho breaking changes sections trong Markdown
_BREAKING_CHANGE_PATTERNS = [
    re.compile(
        r"#+\s*(?:breaking\s+changes?|incompatible\s+changes?|migration\s+guide"
        r"|backward[s]?\s*incompatible|api\s+changes?)",
        re.IGNORECASE,
    ),
]

# Regex cho deprecated APIs trong Markdown
_DEPRECATED_PATTERNS = [
    re.compile(
        r"#+\s*(?:deprecated?\s*(?:apis?|features?|methods?)?|deprecations?)",
        re.IGNORECASE,
    ),
]

# Schema cho parsing raw_json từ các nguồn khác nhau (GitHub, Jira, Custom)
_RAW_JSON_SCHEMA = StructType([
    # -- GitHub fields --
    StructField("tag_name", StringType(), nullable=True),
    StructField("body", StringType(), nullable=True),
    StructField("published_at", StringType(), nullable=True),
    StructField("html_url", StringType(), nullable=True),
    # Nested "releases" list khi fetch_with_retry returns version="latest"
    StructField("releases", ArrayType(StructType([
        StructField("tag_name", StringType(), nullable=True),
        StructField("body", StringType(), nullable=True),
        StructField("published_at", StringType(), nullable=True),
        StructField("html_url", StringType(), nullable=True),
    ])), nullable=True),
    
    # -- Jira fields --
    StructField("version", StringType(), nullable=True),
    
    # -- Jira fields --
    StructField("issues", ArrayType(StructType([
        StructField("id", StringType(), nullable=True),
        StructField("type", StringType(), nullable=True),
        StructField("summary", StringType(), nullable=True),
        StructField("status", StringType(), nullable=True),
        StructField("url", StringType(), nullable=True),
    ])), nullable=True),
])


# =============================================================================
# S3A path helpers
# =============================================================================

def _bronze_path() -> str:
    bucket = os.environ.get("MINIO_BUCKET_BRONZE", "bronze")
    return f"s3a://{bucket}/bronze_raw_releases/"


def _silver_path() -> str:
    bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
    return f"s3a://{bucket}/silver_releases/"


def _rejected_path() -> str:
    bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
    return f"s3a://{bucket}/silver_rejected/"


# =============================================================================
# Parsing & extraction helpers
# =============================================================================

def normalize_version(raw_version: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """Chuẩn hóa version string theo semantic versioning.

    Parameters
    ----------
    raw_version : str | None
        Raw version (e.g. ``"v1.2.3"``, ``"1.2.3-rc1"``).

    Returns
    -------
    tuple[str | None, str | None]
        ``(normalized_version, rejection_reason)``
        - Hợp lệ: ``("1.2.3", None)``
        - Không hợp lệ: ``(None, "Invalid semver: ...")``
    """
    if not raw_version:
        return None, "Empty version string"

    # Xóa prefix "v" hoặc "V"
    cleaned = raw_version.strip().lstrip("vV").strip()

    if not cleaned:
        return None, f"Version is only prefix: {raw_version!r}"

    if _SEMVER_REGEX.match(cleaned):
        return cleaned, None

    return None, f"Invalid semver format: {raw_version!r} → {cleaned!r}"


def extract_markdown_section(body: str, patterns: List[re.Pattern]) -> List[str]:
    """Extract nội dung từ Markdown section matching patterns.

    Tìm heading (# / ## / ###) khớp pattern, lấy toàn bộ content cho đến
    heading cùng level hoặc cao hơn.

    Parameters
    ----------
    body : str
        Markdown body text.
    patterns : list[re.Pattern]
        Regex patterns để match heading.

    Returns
    -------
    list[str]
        List các items (mỗi bullet point là 1 item).
    """
    if not body:
        return []

    lines = body.split("\n")
    items: List[str] = []
    in_section = False
    section_level = 0

    for line in lines:
        # Kiểm tra nếu đây là heading
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)

        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2)

            if in_section and level <= section_level:
                # Heading cùng level hoặc cao hơn → kết thúc section
                in_section = False

            if not in_section:
                # Kiểm tra heading có khớp pattern không
                for pattern in patterns:
                    if pattern.search(heading_text):
                        in_section = True
                        section_level = level
                        break
            continue

        if in_section:
            # Extract bullet points và content
            stripped = line.strip()
            if stripped.startswith(("- ", "* ", "+ ")):
                item = stripped.lstrip("-*+ ").strip()
                if item:
                    items.append(item)
            elif stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                item = re.sub(r"^\d+\.\s*", "", stripped).strip()
                if item:
                    items.append(item)
            elif stripped and not stripped.startswith("#"):
                # Non-empty line trong section (paragraph text)
                # Nối vào item cuối nếu có, hoặc tạo item mới
                if items:
                    items[-1] = items[-1] + " " + stripped
                elif stripped:
                    items.append(stripped)

    return items


def extract_breaking_changes(body: Optional[str]) -> List[str]:
    """Extract breaking changes từ release body (Markdown)."""
    if not body:
        return []
    return extract_markdown_section(body, _BREAKING_CHANGE_PATTERNS)


def extract_deprecated_apis(body: Optional[str]) -> List[str]:
    """Extract deprecated APIs từ release body (Markdown)."""
    if not body:
        return []
    return extract_markdown_section(body, _DEPRECATED_PATTERNS)


def parse_release_date(date_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 date string từ GitHub API."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


# =============================================================================
# Core transform function
# =============================================================================

def transform_releases(
    spark: SparkSession,
    tool_name: str,
    run_date: Optional[str] = None,
    reprocess: bool = False,
) -> Dict[str, int]:
    """Transform raw releases từ Bronze → structured Silver.

    Parameters
    ----------
    spark : SparkSession
        Session đã cấu hình S3A + Delta Lake.
    tool_name : str
        Tên tool cần transform (e.g. ``"apache-kafka"``).
    run_date : str | None
        Ngày chạy (YYYY-MM-DD). Dùng để filter bronze records.
        Default: today.
    reprocess : bool
        If True, reprocess ALL bronze records (including already-processed).
        Useful for schema changes or enrichment upgrades.
        Default: False.

    Returns
    -------
    dict[str, int]
        Statistics: ``{total_read, valid, rejected, upserted}``.
    """

    bronze_uri = _bronze_path()
    silver_uri = _silver_path()
    rejected_uri = _rejected_path()

    logger.info(
        "═══ Transform Releases: %s ═══\n"
        "  Bronze : %s\n"
        "  Silver : %s\n"
        "  Date   : %s\n"
        "  Reprocess: %s",
        tool_name,
        bronze_uri,
        silver_uri,
        run_date or "all",
        reprocess,
    )

    # ─── Step 1: Read Bronze ─────────────────────────────────────────────
    logger.info("Step 1/6 — Reading bronze data")

    try:
        bronze_df = (
            spark.read.table("local.bronze.bronze_raw_releases")
            .filter(F.col("tool_name") == tool_name)
        )
        # B-10: Skip processed filter when reprocessing
        if not reprocess:
            bronze_df = bronze_df.filter(~F.col("processed"))
    except Exception as exc:
        logger.error("Failed to read bronze table at %s: %s", bronze_uri, exc)
        raise

    # Filter theo date nếu được chỉ định
    if run_date:
        bronze_df = bronze_df.filter(
            F.to_date(F.col("crawled_at")) == run_date
        )

    total_read = bronze_df.count()
    logger.info("  Read %d bronze records for %s", total_read, tool_name)

    if total_read == 0:
        logger.info("  No records to process — exiting")
        return {"total_read": 0, "valid": 0, "rejected": 0, "upserted": 0}

    # ─── Step 2: Parse raw_json ──────────────────────────────────────────
    logger.info("Step 2/6 — Parsing raw JSON")

    parsed_df = bronze_df.withColumn(
        "_parsed",
        F.from_json(F.col("raw_json"), _RAW_JSON_SCHEMA),
    ).withColumn(
        "_parse_error",
        F.when(F.col("_parsed").isNull(), F.lit("Malformed JSON"))
         .otherwise(F.lit(None).cast(StringType())),
    )

    # Tách records có lỗi parse
    parse_errors_df = parsed_df.filter(F.col("_parse_error").isNotNull())
    parsed_ok_df = parsed_df.filter(F.col("_parse_error").isNull())

    error_count = parse_errors_df.count()
    if error_count > 0:
        logger.warning("  %d records had JSON parse errors", error_count)

    # ─── Phân tách xử lý theo source_type (GitHub vs Jira) ────────────────
    github_df = parsed_ok_df.filter(F.col("source_type") == "github")
    jira_df = parsed_ok_df.filter(F.col("source_type") == "jira")

    # 1. Xử lý GitHub (Explode releases list nếu có)
    has_releases_list = github_df.filter(F.col("_parsed.releases").isNotNull())
    has_single_release = github_df.filter(F.col("_parsed.releases").isNull())

    if has_releases_list.count() > 0:
        exploded_df = (
            has_releases_list
            .withColumn("_release", F.explode(F.col("_parsed.releases")))
            .select(
                F.col("tool_name"),
                F.col("source_url"),
                F.col("crawled_at"),
                F.col("source_type"),
                F.col("_release.tag_name").alias("_raw_version"),
                F.col("_release.body").alias("_body"),
                F.col("_release.published_at").alias("_published_at"),
                F.col("_release.html_url").alias("_html_url"),
                F.lit(None).alias("_jira_issues")
            )
        )
    else:
        exploded_df = None

    single_df = has_single_release.select(
        F.col("tool_name"),
        F.col("source_url"),
        F.col("crawled_at"),
        F.col("source_type"),
        F.col("_parsed.tag_name").alias("_raw_version"),
        F.col("_parsed.body").alias("_body"),
        F.col("_parsed.published_at").alias("_published_at"),
        F.col("_parsed.html_url").alias("_html_url"),
        F.lit(None).alias("_jira_issues")
    )

    all_github_df = single_df
    if exploded_df is not None:
        all_github_df = all_github_df.unionByName(exploded_df, allowMissingColumns=True)

    # 2. Xử lý Jira
    parsed_jira_df = jira_df.select(
        F.col("tool_name"),
        F.col("source_url"),
        F.col("crawled_at"),
        F.col("source_type"),
        F.col("_parsed.version").alias("_raw_version"),
        F.lit("").alias("_body"),
        F.lit(None).cast(StringType()).alias("_published_at"),
        F.col("source_url").alias("_html_url"),
        F.expr("""
            transform(_parsed.issues, x -> named_struct(
                'id', x.id,
                'type', x.type,
                'title', x.summary,
                'url', x.url
            ))
        """).alias("_jira_issues")
    )

    # Union tất cả releases
    all_releases_df = all_github_df.unionByName(parsed_jira_df, allowMissingColumns=True)
    # Deduplicate theo raw version
    all_releases_df = all_releases_df.dropDuplicates(["tool_name", "_raw_version"])

    # B-7: Removed .count() here — was logging-only, triggered expensive Spark job
    logger.info("  Explode + dedup complete")

    # ─── Step 3: Chuẩn hóa semantic versioning ───────────────────────────
    logger.info("Step 3/6 — Normalizing semantic versions")

    # UDF cho normalize_version
    @F.udf(
        StructType([
            StructField("version", StringType()),
            StructField("rejection_reason", StringType()),
        ])
    )
    def udf_normalize_version(raw_ver):
        ver, reason = normalize_version(raw_ver)
        return Row(version=ver, rejection_reason=reason)

    versioned_df = all_releases_df.withColumn(
        "_version_info",
        udf_normalize_version(F.col("_raw_version")),
    ).withColumn(
        "version",
        F.col("_version_info.version"),
    ).withColumn(
        "_rejection_reason",
        F.col("_version_info.rejection_reason"),
    )

    # Tách valid vs rejected
    valid_df = versioned_df.filter(F.col("version").isNotNull())
    rejected_df = versioned_df.filter(F.col("version").isNull())

    valid_count = valid_df.count()
    rejected_count = rejected_df.count()

    logger.info("  Valid versions: %d, Rejected: %d", valid_count, rejected_count)

    # ─── Step 3b: Ghi rejected records ───────────────────────────────────
    if rejected_count > 0:
        logger.info("  Writing %d rejected records to %s", rejected_count, rejected_uri)
        rejected_output = rejected_df.select(
            F.col("tool_name"),
            F.col("_raw_version").alias("raw_version"),
            F.col("_rejection_reason").alias("rejection_reason"),
            F.col("source_url"),
            F.current_timestamp().alias("rejected_at"),
        )
        rejected_table_id = "local.silver.silver_rejected"
        try:
            spark.read.table(rejected_table_id)
            rejected_output.writeTo(rejected_table_id).append()
        except Exception as e:
            if "TABLE_OR_VIEW_NOT_FOUND" in str(e) or "not found" in str(e).lower():
                rejected_output.writeTo(rejected_table_id).create()
            else:
                raise

    if valid_count == 0:
        logger.info("  No valid releases to process — exiting")
        return {
            "total_read": total_read,
            "valid": 0,
            "rejected": rejected_count,
            "upserted": 0,
        }

    # ─── Step 4: Extract breaking changes & deprecated APIs ──────────────
    logger.info("Step 4/6 — Extracting breaking changes & deprecated APIs")

    @F.udf(ArrayType(StringType()))
    def udf_extract_breaking(body):
        # LOGIC-02 fix: never convert [] to None — keep empty arrays distinct from null
        result = extract_breaking_changes(body)
        return result if result is not None else []

    @F.udf(ArrayType(StringType()))
    def udf_extract_deprecated(body):
        result = extract_deprecated_apis(body)
        return result if result is not None else []

    @F.udf(ArrayType(StructType([
        StructField("id", StringType(), nullable=False),
        StructField("type", StringType(), nullable=False),
        StructField("title", StringType(), nullable=False),
        StructField("url", StringType(), nullable=True),
    ])))
    def udf_extract_github_issues(body):
        if not body: return []
        issues = []
        current_category = "General"
        lines = body.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue
            if line.startswith('#'):
                import re
                current_category = re.sub(r'^#+\s*', '', line)
            elif line.startswith('- ') or line.startswith('* '):
                title = line[2:].strip()
                if title:
                    issues.append({"id": "", "type": current_category[:50], "title": title[:255], "url": None})
        return issues

    enriched_df = (
        valid_df
        .withColumn("breaking_changes", udf_extract_breaking(F.col("_body")))
        .withColumn("deprecated_apis", udf_extract_deprecated(F.col("_body")))
        .withColumn(
            "release_date",
            F.to_date(F.to_timestamp(F.col("_published_at"))),
        )
        .withColumn(
            "_parsed_github_issues",
            udf_extract_github_issues(F.col("_body"))
        )
    )

    # ERR-04 fix: F.transform doesn't accept a UDF — use explode + classify + collect_list
    from processing.spark_jobs.classify_breaking_changes import classify_breaking_change_udf

    # Only process rows that have breaking changes
    df_with_bc = enriched_df.filter(F.size(F.col("breaking_changes")) > 0)
    df_without_bc = enriched_df.filter(F.size(F.col("breaking_changes")) == 0)

    if df_with_bc.rdd.isEmpty():
        enriched_df = enriched_df.withColumn(
            "breaking_changes_enriched", 
            F.lit(None).cast(SCHEMAS["silver_releases"]["breaking_changes_enriched"].dataType)
        )
    else:
        # Preserve original columns for groupBy
        _group_cols = [c for c in enriched_df.columns]
        df_exploded = df_with_bc.withColumn("_bc_item", F.explode(F.col("breaking_changes")))
        df_classified = df_exploded.withColumn("_bc_enriched", classify_breaking_change_udf(F.col("_bc_item")))
        df_reagg = (
            df_classified
            .groupBy(*_group_cols)
            .agg(F.collect_list("_bc_enriched").alias("breaking_changes_enriched"))
        )
        df_without_bc = df_without_bc.withColumn(
            "breaking_changes_enriched", 
            F.lit(None).cast(SCHEMAS["silver_releases"]["breaking_changes_enriched"].dataType)
        )
        enriched_df = df_reagg.unionByName(df_without_bc, allowMissingColumns=True)

    # ─── Step 5: Build silver DataFrame ──────────────────────────────────
    logger.info("Step 5/6 — Building silver DataFrame")

    now = datetime.now(timezone.utc)

    silver_df = enriched_df.select(
        F.col("tool_name"),
        F.col("version"),
        F.col("release_date"),
        F.when(F.col("source_type") == "jira", F.col("_jira_issues"))
         .otherwise(F.col("_parsed_github_issues"))
         .cast(SCHEMAS["silver_releases"]["issues"].dataType).alias("issues"),
        F.col("breaking_changes"),
        F.col("breaking_changes_enriched"),
        F.col("deprecated_apis"),
        F.lit(now).cast("timestamp").alias("processed_at"),
    )

    # ─── Step 6: Delta MERGE upsert ─────────────────────────────────────
    logger.info("Step 6/6 — Upserting into silver_releases at %s", silver_uri)

    # B-7: Cache silver_df before MERGE to avoid re-computation
    silver_df.cache()
    upserted = silver_df.count()

    silver_table_id = "local.silver.silver_releases"
    table_exists = False
    try:
        spark.read.table(silver_table_id)
        table_exists = True
    except Exception:
        pass

    if table_exists:
        silver_df.createOrReplaceTempView("source_silver")
        spark.sql(f"""
            MERGE INTO {silver_table_id} target
            USING source_silver source
            ON target.tool_name = source.tool_name AND target.version = source.version
            WHEN MATCHED THEN UPDATE SET
                target.release_date = source.release_date,
                target.issues = source.issues,
                target.breaking_changes = source.breaking_changes,
                target.breaking_changes_enriched = source.breaking_changes_enriched,
                target.deprecated_apis = source.deprecated_apis,
                target.processed_at = source.processed_at
            WHEN NOT MATCHED THEN INSERT *
        """)
        logger.info("  ✓ Merged %d records into existing silver_releases", upserted)
    else:
        # Bảng chưa tồn tại → tạo mới
        silver_df.writeTo(silver_table_id).createOrReplace()
        logger.info("  ✓ Created silver_releases with %d records", upserted)

    # ─── Step 7: Update bronze records as processed ───────────────────────
    logger.info("Step 7/7 — Updating bronze records as processed")
    bronze_table_id = "local.bronze.bronze_raw_releases"
    update_cond = f"tool_name = '{tool_name}' AND NOT processed"
    if run_date:
        update_cond += f" AND DATE(crawled_at) = '{run_date}'"
        
    try:
        spark.sql(f"UPDATE {bronze_table_id} SET processed = true WHERE {update_cond}")
        logger.info("  ✓ Updated processed=True in bronze_raw_releases")
    except Exception as e:
        logger.error(f"  ✗ Failed to update bronze table: {e}")

    # ─── Summary ─────────────────────────────────────────────────────────
    stats = {
        "total_read": total_read,
        "valid": valid_count,
        "rejected": rejected_count,
        "upserted": upserted,
    }

    logger.info(
        "═══ Transform Complete ═══\n"
        "  Tool     : %s\n"
        "  Read     : %d bronze records\n"
        "  Valid    : %d\n"
        "  Rejected : %d\n"
        "  Upserted : %d into silver\n"
        "══════════════════════════",
        tool_name,
        stats["total_read"],
        stats["valid"],
        stats["rejected"],
        stats["upserted"],
    )

    return stats


# =============================================================================
# CLI entrypoint
# =============================================================================

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Parameters
    ----------
    argv : list[str] | None
        Arguments (default: sys.argv[1:]).

    Returns
    -------
    argparse.Namespace
        Parsed arguments with ``tool_name`` and ``date``.
    """
    parser = argparse.ArgumentParser(
        description="DataStack Compass — Transform Bronze → Silver (Releases)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Transform tất cả releases cho apache-kafka
  spark-submit processing/spark_jobs/transform_releases.py --tool-name apache-kafka

  # Transform chỉ releases được crawl vào ngày cụ thể
  spark-submit processing/spark_jobs/transform_releases.py \\
      --tool-name apache-kafka --date 2024-06-01
        """,
    )

    parser.add_argument(
        "--tool-name",
        required=True,
        help="Tên tool cần transform (e.g. apache-kafka, apache-flink)",
    )
    parser.add_argument(
        "--date",
        default=None,
        help="Ngày crawl cần xử lý (YYYY-MM-DD). Default: tất cả ngày.",
    )
    parser.add_argument(
        "--reprocess",
        action="store_true",
        default=False,
        help="Reprocess ALL bronze records, including already-processed ones. "
             "Useful after schema changes or enrichment upgrades.",
    )

    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> Dict[str, int]:
    """Entrypoint chính — parse args, tạo Spark session, chạy transform.

    Parameters
    ----------
    argv : list[str] | None
        CLI arguments.

    Returns
    -------
    dict[str, int]
        Transform statistics.
    """
    args = parse_args(argv)

    logger.info(
        "Starting transform_releases: tool=%s, date=%s",
        args.tool_name,
        args.date or "all",
    )

    spark = get_spark_session(f"transform-releases-{args.tool_name}")

    try:
        stats = transform_releases(
            spark=spark,
            tool_name=args.tool_name,
            run_date=args.date,
            reprocess=args.reprocess,
        )
        return stats
    finally:
        spark.stop()
        logger.info("SparkSession stopped")


if __name__ == "__main__":
    main()
