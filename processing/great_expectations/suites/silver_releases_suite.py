"""
DataStack Compass — Silver Releases Data Quality Suite
=======================================================

Great Expectations suite chạy trên Spark backend (local, không cần GE Cloud).
Validate bảng ``silver_releases`` sau khi transform từ Bronze.

Usage
-----
    from processing.great_expectations.suites.silver_releases_suite import (
        SilverReleasesSuite,
    )
    from processing.spark_utils.session import get_spark_session

    spark = get_spark_session("dq-silver-releases")
    suite = SilverReleasesSuite()
    result = suite.run(spark, tool_name="apache-kafka")
    # Raises DataQualityError nếu fail

Expectations
------------
1. Columns tồn tại: tool_name, version, release_date, issues, breaking_changes
2. Not null: tool_name, version (0% null)
3. Regex match: version ~ ``^\\d+\\.\\d+``
4. Length: tool_name 2–100 ký tự
5. Row count >= 1
6. Unique composite key: (tool_name, version)
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from pyspark.sql import SparkSession

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
    """Kết quả validation cho một suite.

    Attributes
    ----------
    success : bool
        True nếu tất cả expectations pass.
    tool_name : str
        Tool đã validate.
    total_expectations : int
        Tổng số expectations đã chạy.
    successful_expectations : int
        Số expectations pass.
    failed_expectations : int
        Số expectations fail.
    results : list[dict]
        Chi tiết từng expectation result.
    statistics : dict
        Thống kê tổng hợp (row count, etc.).
    """

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
    """Chạy GE-style expectations trên Spark DataFrame.

    Wrapper nhẹ dùng Great Expectations API với SparkDFDataset.
    Fallback về Spark-native nếu GE import fail (cho testability).
    """

    def __init__(self, spark: SparkSession, table_path: str, tool_name: str) -> None:
        self.spark = spark
        self.table_path = table_path
        self.tool_name = tool_name
        self._results: List[Dict[str, Any]] = []
        self._df = None
        self._ge_dataset = None

    def load(self) -> None:
        """Load Delta table và tạo GE dataset."""
        from pyspark.sql import functions as F

        self._df = (
            self.spark.read.table("local.silver.silver_releases")
            .filter(F.col("tool_name") == self.tool_name)
        )

        try:
            from great_expectations.dataset import SparkDFDataset
            self._ge_dataset = SparkDFDataset(self._df)
            logger.info("Using Great Expectations SparkDFDataset backend")
        except ImportError:
            logger.warning(
                "Great Expectations not available — using Spark-native validation"
            )
            self._ge_dataset = None

    @property
    def row_count(self) -> int:
        """Cached row count."""
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
        """Ghi nhận kết quả một expectation."""
        self._results.append({
            "expectation_type": expectation_type,
            "success": success,
            "kwargs": kwargs,
            "result": result or {},
        })

        status = "✓" if success else "✗"
        logger.info(
            "  %s %s — %s",
            status,
            expectation_type,
            kwargs,
        )
        return success

    # ── Expectation methods ──────────────────────────────────────────────

    def expect_column_to_exist(self, column: str) -> bool:
        """Kiểm tra column tồn tại trong DataFrame."""
        if self._ge_dataset is not None:
            res = self._ge_dataset.expect_column_to_exist(column)
            return self._record_result(
                "expect_column_to_exist",
                res["success"],
                {"column": column},
                res.get("result"),
            )

        exists = column in self._df.columns
        return self._record_result(
            "expect_column_to_exist",
            exists,
            {"column": column},
            {"observed_columns": self._df.columns if not exists else []},
        )

    def expect_column_values_to_not_be_null(
        self, column: str, mostly: float = 1.0
    ) -> bool:
        """Kiểm tra column không có null values."""
        if self._ge_dataset is not None:
            res = self._ge_dataset.expect_column_values_to_not_be_null(
                column, mostly=mostly
            )
            return self._record_result(
                "expect_column_values_to_not_be_null",
                res["success"],
                {"column": column, "mostly": mostly},
                res.get("result"),
            )

        from pyspark.sql import functions as F

        total = self._df.count()
        if total == 0:
            return self._record_result(
                "expect_column_values_to_not_be_null",
                False,
                {"column": column, "mostly": mostly},
                {"observed_value": "empty dataset"},
            )

        null_count = self._df.filter(F.col(column).isNull()).count()
        non_null_ratio = (total - null_count) / total
        success = non_null_ratio >= mostly

        return self._record_result(
            "expect_column_values_to_not_be_null",
            success,
            {"column": column, "mostly": mostly},
            {
                "element_count": total,
                "null_count": null_count,
                "non_null_ratio": round(non_null_ratio, 4),
            },
        )

    def expect_column_values_to_match_regex(
        self, column: str, regex: str, mostly: float = 1.0
    ) -> bool:
        """Kiểm tra column values khớp regex pattern."""
        if self._ge_dataset is not None:
            res = self._ge_dataset.expect_column_values_to_match_regex(
                column, regex, mostly=mostly
            )
            return self._record_result(
                "expect_column_values_to_match_regex",
                res["success"],
                {"column": column, "regex": regex, "mostly": mostly},
                res.get("result"),
            )

        from pyspark.sql import functions as F

        total = self._df.filter(F.col(column).isNotNull()).count()
        if total == 0:
            return self._record_result(
                "expect_column_values_to_match_regex",
                False,
                {"column": column, "regex": regex, "mostly": mostly},
                {"observed_value": "no non-null values"},
            )

        match_count = self._df.filter(
            F.col(column).rlike(regex)
        ).count()
        match_ratio = match_count / total
        success = match_ratio >= mostly

        return self._record_result(
            "expect_column_values_to_match_regex",
            success,
            {"column": column, "regex": regex, "mostly": mostly},
            {
                "element_count": total,
                "matching_count": match_count,
                "match_ratio": round(match_ratio, 4),
            },
        )

    def expect_column_value_lengths_to_be_between(
        self,
        column: str,
        min_value: int,
        max_value: int,
        mostly: float = 1.0,
    ) -> bool:
        """Kiểm tra string length nằm trong range."""
        if self._ge_dataset is not None:
            res = self._ge_dataset.expect_column_value_lengths_to_be_between(
                column, min_value=min_value, max_value=max_value, mostly=mostly
            )
            return self._record_result(
                "expect_column_value_lengths_to_be_between",
                res["success"],
                {
                    "column": column,
                    "min_value": min_value,
                    "max_value": max_value,
                    "mostly": mostly,
                },
                res.get("result"),
            )

        from pyspark.sql import functions as F

        total = self._df.filter(F.col(column).isNotNull()).count()
        if total == 0:
            return self._record_result(
                "expect_column_value_lengths_to_be_between",
                False,
                {"column": column, "min_value": min_value, "max_value": max_value},
                {"observed_value": "no non-null values"},
            )

        in_range = self._df.filter(
            (F.length(F.col(column)) >= min_value)
            & (F.length(F.col(column)) <= max_value)
        ).count()
        ratio = in_range / total
        success = ratio >= mostly

        return self._record_result(
            "expect_column_value_lengths_to_be_between",
            success,
            {
                "column": column,
                "min_value": min_value,
                "max_value": max_value,
                "mostly": mostly,
            },
            {
                "element_count": total,
                "in_range_count": in_range,
                "ratio": round(ratio, 4),
            },
        )

    def expect_table_row_count_to_be_between(
        self, min_value: int, max_value: Optional[int] = None
    ) -> bool:
        """Kiểm tra số rows nằm trong range."""
        if self._ge_dataset is not None:
            res = self._ge_dataset.expect_table_row_count_to_be_between(
                min_value=min_value, max_value=max_value
            )
            return self._record_result(
                "expect_table_row_count_to_be_between",
                res["success"],
                {"min_value": min_value, "max_value": max_value},
                res.get("result"),
            )

        count = self.row_count
        success = count >= min_value
        if max_value is not None:
            success = success and count <= max_value

        return self._record_result(
            "expect_table_row_count_to_be_between",
            success,
            {"min_value": min_value, "max_value": max_value},
            {"observed_value": count},
        )

    def expect_compound_columns_to_be_unique(
        self, column_list: List[str]
    ) -> bool:
        """Custom expectation: composite key uniqueness.

        Kiểm tra combination of columns là unique (không có duplicate rows).
        """
        from pyspark.sql import functions as F

        total = self._df.count()
        if total == 0:
            return self._record_result(
                "expect_compound_columns_to_be_unique",
                False,
                {"column_list": column_list},
                {"observed_value": "empty dataset"},
            )

        distinct_count = self._df.select(column_list).distinct().count()
        duplicate_count = total - distinct_count
        success = duplicate_count == 0

        result_details: Dict[str, Any] = {
            "total_rows": total,
            "distinct_combinations": distinct_count,
            "duplicate_count": duplicate_count,
        }

        # Nếu có duplicates, log một số ví dụ
        if not success:
            dups = (
                self._df.groupBy(column_list)
                .count()
                .filter(F.col("count") > 1)
                .orderBy(F.col("count").desc())
                .limit(5)
                .collect()
            )
            result_details["sample_duplicates"] = [
                {col: row[col] for col in column_list + ["count"]}
                for row in dups
            ]

        return self._record_result(
            "expect_compound_columns_to_be_unique",
            success,
            {"column_list": column_list},
            result_details,
        )

    @property
    def results(self) -> List[Dict[str, Any]]:
        return self._results


# =============================================================================
# Suite class
# =============================================================================

class SilverReleasesSuite:
    """Data Quality suite cho bảng ``silver_releases``.

    Chạy tất cả expectations và trả về ``ValidationResult``.
    Raise ``DataQualityError`` nếu bất kỳ expectation nào fail.

    Parameters
    ----------
    raise_on_failure : bool
        Nếu True (default), raise ``DataQualityError`` khi có failure.
        Nếu False, chỉ return result mà không raise.
    """

    def __init__(self, raise_on_failure: bool = True) -> None:
        self.raise_on_failure = raise_on_failure

    def run(
        self,
        spark: SparkSession,
        tool_name: str,
    ) -> ValidationResult:
        """Chạy toàn bộ suite và trả về kết quả.

        Parameters
        ----------
        spark : SparkSession
            Session đã cấu hình S3A + Delta Lake.
        tool_name : str
            Tên tool cần validate (e.g. ``"apache-kafka"``).

        Returns
        -------
        ValidationResult
            Kết quả validation chi tiết.

        Raises
        ------
        DataQualityError
            Nếu ``raise_on_failure=True`` và có expectation fail.
        """
        bucket = os.environ.get("MINIO_BUCKET_SILVER", "silver")
        table_path = f"s3a://{bucket}/silver_releases/"

        logger.info(
            "═══ Silver Releases DQ Suite ═══\n"
            "  Tool  : %s\n"
            "  Path  : %s",
            tool_name,
            table_path,
        )

        # ── Load data ────────────────────────────────────────────────────
        runner = _ExpectationRunner(spark, table_path, tool_name)
        runner.load()

        row_count = runner.row_count
        logger.info("  Rows loaded: %d", row_count)

        # ── 1. Column existence ──────────────────────────────────────────
        logger.info("▸ Column existence checks")
        required_columns = [
            "tool_name",
            "version",
            "release_date",
            "issues",
            "breaking_changes",
        ]
        for col in required_columns:
            runner.expect_column_to_exist(col)

        # ── 2. Not null (0% null allowed) ────────────────────────────────
        logger.info("▸ Not-null checks")
        runner.expect_column_values_to_not_be_null("tool_name", mostly=1.0)
        runner.expect_column_values_to_not_be_null("version", mostly=1.0)

        # ── 3. Regex match: version ~ ^\d+\.\d+ ─────────────────────────
        logger.info("▸ Regex checks")
        runner.expect_column_values_to_match_regex(
            "version",
            regex=r"^\d+\.\d+",
            mostly=1.0,
        )

        # ── 4. String length: tool_name 2–100 chars ─────────────────────
        logger.info("▸ Length checks")
        runner.expect_column_value_lengths_to_be_between(
            "tool_name",
            min_value=2,
            max_value=100,
        )

        # ── 5. Row count >= 1 ────────────────────────────────────────────
        logger.info("▸ Row count check")
        runner.expect_table_row_count_to_be_between(min_value=1)

        # ── 6. Unique composite key: (tool_name, version) ───────────────
        logger.info("▸ Composite key uniqueness")
        runner.expect_compound_columns_to_be_unique(
            column_list=["tool_name", "version"],
        )

        # ── Build result ─────────────────────────────────────────────────
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
            statistics={
                "row_count": row_count,
                "evaluated_expectations": len(all_results),
                "successful_expectations": len(passed),
                "unsuccessful_expectations": len(failed),
                "success_percent": (
                    round(len(passed) / len(all_results) * 100, 1)
                    if all_results else 0
                ),
            },
        )

        # ── Log summary ──────────────────────────────────────────────────
        if validation_result.success:
            logger.info(
                "✅ Data quality OK for %s — %d/%d expectations passed",
                tool_name,
                len(passed),
                len(all_results),
            )
        else:
            logger.error(
                "❌ Data quality FAILED for %s — %d/%d expectations failed",
                tool_name,
                len(failed),
                len(all_results),
            )
            for f in failed:
                logger.error(
                    "  ✗ %s\n"
                    "    kwargs : %s\n"
                    "    result : %s",
                    f["expectation_type"],
                    f["kwargs"],
                    f["result"],
                )

            if self.raise_on_failure:
                raise DataQualityError(
                    f"Data quality validation failed for {tool_name}: "
                    f"{len(failed)}/{len(all_results)} expectations failed",
                    failed_expectations=failed,
                    tool_name=tool_name,
                )

        return validation_result
