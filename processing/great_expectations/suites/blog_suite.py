"""
DataStack Compass — Silver Blogs Data Quality Suite
===================================================

Great Expectations suite cho bảng ``silver_blogs``.
"""

from __future__ import annotations

import logging
import os

from processing.great_expectations.suites.silver_releases_suite import _ExpectationRunner, ValidationResult
from processing.exceptions import DataQualityError
from pyspark.sql import SparkSession

logger = logging.getLogger(__name__)

class SilverBlogsSuite:
    """Data Quality suite cho bảng ``silver_blogs``."""
    
    def __init__(self, raise_on_failure: bool = True) -> None:
        self.raise_on_failure = raise_on_failure

    def run(self, spark: SparkSession, tool_name: str) -> ValidationResult:
        bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
        table_path = f"s3a://{bucket}/silver_blogs/"

        logger.info(
            "═══ Silver Blogs DQ Suite ═══\n"
            "  Tool  : %s\n"
            "  Path  : %s",
            tool_name,
            table_path,
        )

        runner = _ExpectationRunner(spark, table_path, tool_name)
        runner.load()

        row_count = runner.row_count
        logger.info("  Rows loaded: %d", row_count)

        # 1. Column existence
        for col in ["tool_name", "title", "url", "published_date", "source_feed"]:
            runner.expect_column_to_exist(col)

        # 2. Not null
        runner.expect_column_values_to_not_be_null("url", mostly=1.0)
        runner.expect_column_values_to_not_be_null("published_date", mostly=1.0)
        runner.expect_column_values_to_not_be_null("tool_name", mostly=1.0)
        runner.expect_column_values_to_not_be_null("title", mostly=1.0)

        # 3. Row count >= 1
        runner.expect_table_row_count_to_be_between(min_value=1)

        # Build result
        all_results = runner.results
        passed = [r for r in all_results if r["success"]]
        failed = [r for r in all_results if not r["success"]]

        validation_result = ValidationResult(
            success=len(failed) == 0,
            tool_name=tool_name,
            total_expectations=len(all_results),
            successful_expectations=len(passed),
            failed_expectations=len(failed),
            results=all_results,
            statistics={"row_count": row_count}
        )

        if validation_result.success:
            logger.info("✅ Data quality OK for %s blogs", tool_name)
        else:
            logger.error("❌ Data quality FAILED for %s blogs", tool_name)
            if self.raise_on_failure:
                raise DataQualityError(
                    f"Data quality validation failed for {tool_name} blogs",
                    failed_expectations=failed,
                    tool_name=tool_name,
                )

        return validation_result
