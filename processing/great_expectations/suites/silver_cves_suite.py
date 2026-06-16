"""
DataStack Compass — Silver CVEs Data Quality Suite
=======================================================

Great Expectations suite chạy trên Spark backend (local, không cần GE Cloud).
Validate bảng ``silver_cves`` sau khi transform từ Bronze (NVD API).

Usage
-----
    from processing.great_expectations.suites.silver_cves_suite import (
        SilverCvesSuite,
    )
    from processing.spark_utils.session import get_spark_session

    spark = get_spark_session("dq-silver-cves")
    suite = SilverCvesSuite()
    result = suite.run(spark, tool_name="apache-kafka")

Expectations
------------
1. Columns tồn tại: cve_id, tool_name, affected_versions, cvss_score, severity
2. Not null: cve_id, tool_name, severity (0% null)
3. Regex match: cve_id ~ ``^CVE-\d{4}-\d{4,}$``
4. Value range: cvss_score between 0.0 and 10.0
5. Unique composite key: (cve_id, tool_name)
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

# ─── Project root trên sys.path ─────────────────────────────────────────────
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from processing.exceptions import DataQualityError

logger = logging.getLogger(__name__)


# =============================================================================
# Validation result dataclass
# =============================================================================

@dataclass
class ValidationResult:
    success: bool
    tool_name: str
    total_expectations: int = 0
    successful_expectations: int = 0
    failed_expectations: int = 0
    results: List[Dict[str, Any]] = field(default_factory=list)
    statistics: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# Expectation runner (GE-compatible, Spark-native)
# =============================================================================

class _ExpectationRunner:
    def __init__(self, spark: SparkSession, table_path: str, tool_name: str) -> None:
        self.spark = spark
        self.table_path = table_path
        self.tool_name = tool_name
        self._results: List[Dict[str, Any]] = []
        self._df = None

    def load(self) -> None:
        self._df = (
            self.spark.read.format("delta").load(self.table_path)
            .filter(F.col("tool_name") == self.tool_name)
        )

    @property
    def row_count(self) -> int:
        if self._df is None:
            return 0
        return self._df.count()

    def _record_result(
        self,
        expectation_type: str,
        success: bool,
        kwargs: Dict[str, Any],
        result: Optional[Dict[str, Any]] = None,
    ) -> bool:
        self._results.append({
            "expectation_type": expectation_type,
            "success": success,
            "kwargs": kwargs,
            "result": result or {},
        })
        status = "✓" if success else "✗"
        logger.info("  %s %s — %s", status, expectation_type, kwargs)
        return success

    def expect_column_to_exist(self, column: str) -> bool:
        exists = column in self._df.columns
        return self._record_result(
            "expect_column_to_exist",
            exists,
            {"column": column},
            {"observed_columns": self._df.columns if not exists else []},
        )

    def expect_column_values_to_not_be_null(self, column: str, mostly: float = 1.0) -> bool:
        total = self._df.count()
        if total == 0:
            return self._record_result("expect_column_values_to_not_be_null", False, {"column": column}, {})
        null_count = self._df.filter(F.col(column).isNull()).count()
        ratio = (total - null_count) / total
        return self._record_result(
            "expect_column_values_to_not_be_null",
            ratio >= mostly,
            {"column": column, "mostly": mostly},
            {"non_null_ratio": ratio},
        )

    def expect_column_values_to_match_regex(self, column: str, regex: str, mostly: float = 1.0) -> bool:
        total = self._df.filter(F.col(column).isNotNull()).count()
        if total == 0:
            return self._record_result("expect_column_values_to_match_regex", False, {"column": column}, {})
        match_count = self._df.filter(F.col(column).rlike(regex)).count()
        ratio = match_count / total
        return self._record_result(
            "expect_column_values_to_match_regex",
            ratio >= mostly,
            {"column": column, "regex": regex},
            {"match_ratio": ratio},
        )
        
    def expect_column_values_to_be_between(self, column: str, min_value: float, max_value: float, mostly: float = 1.0) -> bool:
        total = self._df.filter(F.col(column).isNotNull()).count()
        if total == 0:
            return self._record_result("expect_column_values_to_be_between", False, {"column": column}, {})
        in_range_count = self._df.filter((F.col(column) >= min_value) & (F.col(column) <= max_value)).count()
        ratio = in_range_count / total
        return self._record_result(
            "expect_column_values_to_be_between",
            ratio >= mostly,
            {"column": column, "min": min_value, "max": max_value},
            {"ratio": ratio},
        )

    def expect_compound_columns_to_be_unique(self, column_list: List[str]) -> bool:
        total = self._df.count()
        if total == 0:
            return self._record_result("expect_compound_columns_to_be_unique", False, {"column_list": column_list}, {})
        distinct_count = self._df.select(column_list).distinct().count()
        success = (total == distinct_count)
        return self._record_result(
            "expect_compound_columns_to_be_unique",
            success,
            {"column_list": column_list},
            {"total": total, "distinct": distinct_count},
        )

    @property
    def results(self) -> List[Dict[str, Any]]:
        return self._results


# =============================================================================
# Suite class
# =============================================================================

class SilverCvesSuite:
    def __init__(self, raise_on_failure: bool = True) -> None:
        self.raise_on_failure = raise_on_failure

    def run(self, spark: SparkSession, tool_name: str) -> ValidationResult:
        bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
        table_path = f"s3a://{bucket}/silver_cves/"

        logger.info("═══ Silver CVEs DQ Suite ═══\n  Tool  : %s\n  Path  : %s", tool_name, table_path)

        runner = _ExpectationRunner(spark, table_path, tool_name)
        runner.load()

        row_count = runner.row_count
        logger.info("  Rows loaded: %d", row_count)

        if row_count == 0:
            return ValidationResult(success=True, tool_name=tool_name, total_expectations=0, successful_expectations=0, failed_expectations=0)

        # 1. Column existence
        for col in ["cve_id", "tool_name", "affected_versions", "cvss_score", "severity"]:
            runner.expect_column_to_exist(col)

        # 2. Not null
        for col in ["cve_id", "tool_name", "severity"]:
            runner.expect_column_values_to_not_be_null(col, mostly=1.0)

        # 3. Regex match CVE
        runner.expect_column_values_to_match_regex("cve_id", regex=r"^CVE-\d{4}-\d{4,}$", mostly=1.0)

        # 4. CVSS range
        runner.expect_column_values_to_be_between("cvss_score", min_value=0.0, max_value=10.0, mostly=1.0)

        # 5. Uniqueness
        runner.expect_compound_columns_to_be_unique(["cve_id", "tool_name"])

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
            logger.info("✅ Data quality OK for %s", tool_name)
        else:
            logger.error("❌ Data quality FAILED for %s", tool_name)
            if self.raise_on_failure:
                raise DataQualityError(
                    f"Data quality validation failed for {tool_name}",
                    failed_expectations=failed,
                    tool_name=tool_name,
                )

        return validation_result
