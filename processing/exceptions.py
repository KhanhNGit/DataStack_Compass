"""
DataStack Compass — Processing Exceptions
==========================================

Custom exceptions cho processing layer (Spark jobs, data quality, etc.).
"""

from __future__ import annotations

from typing import Any, Dict, List


class DataQualityError(Exception):
    """Raised when data quality validation fails.

    Attributes
    ----------
    failed_expectations : list[dict]
        List các expectation results that failed. Mỗi dict chứa:
        - ``expectation_type`` (str): Tên expectation.
        - ``kwargs`` (dict): Parameters đã truyền.
        - ``result`` (dict): Chi tiết kết quả (observed values, etc.).
        - ``success`` (bool): Luôn là False.
    tool_name : str
        Tên tool đang validate.
    """

    def __init__(
        self,
        message: str,
        *,
        failed_expectations: List[Dict[str, Any]],
        tool_name: str = "",
    ) -> None:
        self.failed_expectations = failed_expectations
        self.tool_name = tool_name
        super().__init__(message)

    def __str__(self) -> str:
        lines = [super().__str__()]
        lines.append(f"Tool: {self.tool_name}")
        lines.append(f"Failed expectations: {len(self.failed_expectations)}")
        for i, exp in enumerate(self.failed_expectations, 1):
            exp_type = exp.get("expectation_type", "unknown")
            kwargs = exp.get("kwargs", {})
            lines.append(f"  {i}. {exp_type} — {kwargs}")
        return "\n".join(lines)

    @property
    def summary(self) -> str:
        """One-line summary for logging."""
        count = len(self.failed_expectations)
        types = [e.get("expectation_type", "?") for e in self.failed_expectations]
        return f"{count} failed: {', '.join(types)}"
