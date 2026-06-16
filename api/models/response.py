"""
DataStack Compass — Pydantic Response Models
=============================================

Tất cả API responses tuân thủ format chuẩn:
    {
        "data": ...,
        "meta": { ... },
        "errors": [ ... ]
    }

Models
------
- BaseResponse       — Generic wrapper (data + meta + errors)
- PaginatedResponse  — Paginated list (data + total + page + page_size)
- ToolSummary        — Gold layer tool overview
- ReleaseDetail      — Silver release record
- CVEItem            — Silver CVE record
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, List, Optional, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


# =============================================================================
# Base response wrappers
# =============================================================================


class BaseResponse(BaseModel):
    """Response chuẩn cho tất cả API endpoints.

    Format: ``{data, meta, errors}`` — theo GEMINI.md spec.
    """

    data: Any = None
    meta: dict = Field(default_factory=dict)
    errors: List[str] = Field(default_factory=list)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "data": {"tool_name": "apache-kafka"},
                    "meta": {"request_id": "abc-123"},
                    "errors": [],
                }
            ]
        }
    }


class PaginatedResponse(BaseResponse):
    """Response cho paginated list endpoints.

    Pagination info is inside ``meta`` to conform to {data, meta, errors} contract.
    Usage: PaginatedResponse(data=items, meta={"total": 100, "page": 1, "page_size": 20})
    """

    @staticmethod
    def create(
        data: list,
        total: int,
        page: int,
        page_size: int,
        extra_meta: Optional[dict] = None,
    ) -> "PaginatedResponse":
        """Factory method to build paginated response with meta."""
        meta = {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 0,
            "has_next": page < ((total + page_size - 1) // page_size if page_size > 0 else 0),
            "has_prev": page > 1,
        }
        if extra_meta:
            meta.update(extra_meta)
        return PaginatedResponse(data=data, meta=meta)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "data": [{"tool_name": "apache-kafka"}],
                    "meta": {"total": 5, "page": 1, "page_size": 20, "total_pages": 1},
                    "errors": [],
                }
            ]
        }
    }


# =============================================================================
# Domain models
# =============================================================================


class ToolSummary(BaseModel):
    """Gold layer: tổng hợp thông tin một tool.

    Mapping từ bảng ``gold_tool_summary``.
    """

    tool_name: str = Field(
        ..., description="Tên tool (e.g. apache-kafka)", examples=["apache-kafka"]
    )
    latest_version: Optional[str] = Field(
        None, description="Version mới nhất (semantic versioning)", examples=["3.7.1"]
    )
    eol_date: Optional[date] = Field(
        None, description="End-of-Life date"
    )
    eos_date: Optional[date] = Field(
        None, description="End-of-Sale date"
    )
    total_cve_critical: int = Field(
        0, description="Tổng CVE severity Critical", ge=0
    )
    total_cve_high: int = Field(
        0, description="Tổng CVE severity High", ge=0
    )
    last_updated: Optional[datetime] = Field(
        None, description="Thời điểm cập nhật cuối"
    )

    @property
    def risk_level(self) -> str:
        """Tính risk level dựa trên CVE counts."""
        if self.total_cve_critical > 0:
            return "critical"
        if self.total_cve_high > 3:
            return "high"
        if self.total_cve_high > 0:
            return "medium"
        return "low"


class IssueItem(BaseModel):
    """Một issue trong release (Bug/Feature/Improvement)."""

    id: str = Field(..., description="Issue ID")
    type: str = Field(
        ..., description="Loại issue", examples=["Bug", "Feature", "Improvement"]
    )
    title: str = Field(..., description="Tiêu đề issue")
    url: Optional[str] = Field(None, description="Link tới issue tracker")


class BreakingChangeEnriched(BaseModel):
    text: str
    category: str
    impact: str
    action_required: bool

class ReleaseDetail(BaseModel):
    """Silver layer: chi tiết một release version.

    Mapping từ bảng ``silver_releases``.
    """

    tool_name: str = Field(
        ..., description="Tên tool", examples=["apache-kafka"]
    )
    version: str = Field(
        ..., description="Version (semantic versioning)", examples=["3.7.1"]
    )
    release_date: Optional[date] = Field(
        None, description="Ngày phát hành"
    )
    issues: Optional[List[IssueItem]] = Field(
        None, description="Danh sách issues"
    )
    breaking_changes: Optional[List[str]] = Field(
        None, description="Danh sách breaking changes"
    )
    breaking_changes_enriched: Optional[List[BreakingChangeEnriched]] = Field(
        None, description="Danh sách breaking changes đã được phân loại"
    )
    deprecated_apis: Optional[List[str]] = Field(
        None, description="Danh sách deprecated APIs"
    )
    processed_at: Optional[datetime] = Field(
        None, description="Thời điểm xử lý"
    )

    @property
    def has_breaking_changes(self) -> bool:
        """Release có breaking changes không."""
        return bool(self.breaking_changes)


class CVEItem(BaseModel):
    """Silver layer: một CVE record.

    Mapping từ bảng ``silver_cves``.
    """

    cve_id: str = Field(
        ..., description="CVE identifier", examples=["CVE-2024-12345"]
    )
    tool_name: str = Field(
        ..., description="Tool bị ảnh hưởng", examples=["apache-kafka"]
    )
    affected_versions: List[str] = Field(
        default_factory=list, description="Các versions bị ảnh hưởng"
    )
    fixed_in_version: Optional[str] = Field(
        None, description="Version đã fix"
    )
    cvss_score: Optional[float] = Field(
        None, description="CVSS v3.1 base score (0.0–10.0)", ge=0.0, le=10.0
    )
    severity: str = Field(
        ..., description="Mức độ nghiêm trọng",
        examples=["Critical", "High", "Medium", "Low"],
    )
    description: Optional[str] = Field(
        None, description="Mô tả CVE"
    )
    published_at: Optional[datetime] = Field(
        None, description="Ngày công bố CVE"
    )

    @property
    def nvd_url(self) -> str:
        """URL tới trang NVD chi tiết."""
        return f"https://nvd.nist.gov/vuln/detail/{self.cve_id}"


class CVEStats(BaseModel):
    """Thống kê tổng quan CVE."""

    total_critical: int = Field(0, description="Tổng số CVE Critical")
    total_high: int = Field(0, description="Tổng số CVE High")
    total_medium: int = Field(0, description="Tổng số CVE Medium")
    total_low: int = Field(0, description="Tổng số CVE Low")
    new_last_7_days: int = Field(0, description="CVE mới trong 7 ngày qua")
    new_last_30_days: int = Field(0, description="CVE mới trong 30 ngày qua")
    most_affected_tool: Optional[str] = Field(None, description="Tool bị ảnh hưởng nhiều nhất")
    highest_cvss: Optional[float] = Field(None, description="Điểm CVSS cao nhất")

