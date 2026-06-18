"""
DataStack Compass — Data Ingestion Connectors
==============================================

Abstract base class + concrete connectors cho việc thu thập dữ liệu
Release Notes, CVE, Breaking Changes từ các nguồn bên ngoài.

Architecture
------------
    BaseConnector (ABC)
    ├── GitHubReleaseConnector  — GitHub Releases API
    └── HttpConnector           — Generic HTTP (Jira, official docs, …)

Usage
-----
    from ingestion.connectors import GitHubReleaseConnector
    from processing.spark_utils import get_spark_session

    spark = get_spark_session("github-ingest")
    gh = GitHubReleaseConnector(owner="apache", repo="kafka")

    data = gh.fetch_with_retry(tool_name="kafka", version="3.7.0")
    gh.save_to_bronze(spark, data, tool_name="kafka", source_type="github")
"""

from __future__ import annotations

import abc
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests
from pyspark.sql import Row, SparkSession

from storage.delta.schemas import SCHEMAS

logger = logging.getLogger(__name__)

_PROJECT_NAME = "DataStack-Compass"
_PROJECT_URL = "https://github.com/datastack-compass"


# =============================================================================
# Custom Exception
# =============================================================================

class ConnectorError(Exception):
    """Raised when a connector HTTP request fails.

    Attributes
    ----------
    status_code : int | None
        HTTP status code (None nếu lỗi trước khi nhận response).
    url : str
        URL đã request.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        url: str = "",
    ) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(message)

    def __str__(self) -> str:
        parts = [super().__str__()]
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.url:
            parts.append(f"url={self.url}")
        return " | ".join(parts)


# =============================================================================
# Abstract Base Connector
# =============================================================================

class BaseConnector(abc.ABC):
    """Abstract base class cho tất cả DataStack Compass data connectors.

    Subclass CHỈ cần implement ``fetch()`` — retry logic và Delta Lake
    persistence đã có sẵn.
    """

    # ── Abstract ─────────────────────────────────────────────────────────────

    @abc.abstractmethod
    def fetch(self, tool_name: str, version: str) -> dict:
        """Thu thập raw data từ nguồn bên ngoài.

        Parameters
        ----------
        tool_name : str
            Tên tool (e.g. ``"kafka"``, ``"flink"``).
        version : str
            Version cần lấy (e.g. ``"3.7.0"``), hoặc ``"latest"``.

        Returns
        -------
        dict
            Raw data dưới dạng dict. Cấu trúc tùy thuộc connector.

        Raises
        ------
        ConnectorError
            Nếu request thất bại.
        """

    # ── HTTP Headers ─────────────────────────────────────────────────────────

    @property
    def headers(self) -> Dict[str, str]:
        """HTTP headers mặc định kèm User-Agent cho mọi request."""
        return {
            "User-Agent": f"{_PROJECT_NAME}/1.0 ({_PROJECT_URL})",
            "Accept": "application/json",
        }

    # ── Retry Logic ──────────────────────────────────────────────────────────

    def fetch_with_retry(
        self,
        tool_name: str,
        version: str,
        max_retries: int = 3,
        backoff_factor: float = 2.0,
    ) -> dict:
        """Gọi ``fetch()`` với Exponential Backoff.

        Parameters
        ----------
        tool_name : str
            Tên tool.
        version : str
            Version cần lấy.
        max_retries : int
            Số lần retry tối đa (default 3).
        backoff_factor : float
            Hệ số nhân cho thời gian chờ (default 2.0).
            Delay = backoff_factor ** attempt  →  2s, 4s, 8s, …

        Returns
        -------
        dict
            Raw data từ ``fetch()``.

        Raises
        ------
        ConnectorError
            Nếu tất cả retries đều thất bại.
        """
        last_error: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                return self.fetch(tool_name, version)

            except (ConnectorError, requests.RequestException) as exc:
                last_error = exc
                if attempt < max_retries:
                    delay = backoff_factor ** attempt
                    logger.warning(
                        "Attempt %d/%d failed for %s/%s — retrying in %.1fs: %s",
                        attempt + 1,
                        max_retries + 1,
                        tool_name,
                        version,
                        delay,
                        exc,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "All %d attempts failed for %s/%s",
                        max_retries + 1,
                        tool_name,
                        version,
                    )

        # Wrap non-ConnectorError exceptions
        if isinstance(last_error, ConnectorError):
            raise last_error
        raise ConnectorError(
            f"Max retries ({max_retries}) exceeded for {tool_name}/{version}: "
            f"{last_error}",
            url="",
        ) from last_error

    # ── Delta Lake Persistence ───────────────────────────────────────────────

    def save_to_bronze(
        self,
        spark: SparkSession,
        data: dict,
        tool_name: str,
        source_type: str,
    ) -> str:
        """Lưu raw data vào Delta Lake bronze layer.

        Parameters
        ----------
        spark : SparkSession
            Session đã cấu hình S3A.
        data : dict
            Raw data từ ``fetch()`` — sẽ được serialize thành JSON string.
        tool_name : str
            Tên tool (e.g. ``"kafka"``).
        source_type : str
            Nguồn dữ liệu: ``"github"`` | ``"jira"`` | ``"official_docs"``.

        Returns
        -------
        str
            S3A path đã ghi.
        """
        bucket = os.environ.get("MINIO_BUCKET_BRONZE", "bronze")
        table_path = f"s3a://{bucket}/bronze_raw_releases/"

        schema = SCHEMAS["bronze_raw_releases"]

        # Xác định version từ data nếu có
        version = (
            data.get("tag_name")
            or data.get("version")
            or "unknown"
        )

        row = Row(
            tool_name=tool_name,
            version=str(version),
            raw_json=json.dumps(data, ensure_ascii=False, default=str),
            source_url=data.get("html_url") or data.get("source_url") or "",
            crawled_at=datetime.now(timezone.utc),
            source_type=source_type,
            processed=False,
        )

        df = spark.createDataFrame([row], schema)

        df.write.format("iceberg").mode("append").save(table_path)

        logger.info(
            "Saved to bronze: tool=%s version=%s path=%s",
            tool_name,
            version,
            table_path,
        )
        return table_path


# =============================================================================
# GitHub Release Connector
# =============================================================================

class GitHubReleaseConnector(BaseConnector):
    """Connector cho GitHub Releases API.

    Parameters
    ----------
    owner : str
        GitHub org / user (e.g. ``"apache"``).
    repo : str
        Repository name (e.g. ``"kafka"``).

    Environment
    -----------
    GITHUB_TOKEN : str, optional
        Personal access token → tăng rate limit từ 60 → 5000 req/h.
    """

    _API_BASE = "https://api.github.com"

    def __init__(self, owner: str, repo: str) -> None:
        self.owner = owner
        self.repo = repo

    @property
    def headers(self) -> Dict[str, str]:
        """Headers kèm GitHub token nếu có."""
        h = super().headers.copy()
        h["Accept"] = "application/vnd.github+json"
        h["X-GitHub-Api-Version"] = "2022-11-28"

        token = os.environ.get("GITHUB_TOKEN")
        if token:
            h["Authorization"] = f"Bearer {token}"

        return h

    def fetch(self, tool_name: str, version: str) -> dict:
        """Lấy releases từ GitHub API.

        Parameters
        ----------
        tool_name : str
            Dùng cho logging (giá trị thực lấy từ ``self.owner/self.repo``).
        version : str
            ``"latest"`` → lấy release mới nhất.
            Chuỗi cụ thể → tìm release có tag_name khớp.

        Returns
        -------
        dict
            Chứa keys: ``tag_name``, ``body``, ``published_at``, ``html_url``.
            Nếu ``version="latest"``, trả thêm key ``releases`` (list tất cả).
        """
        url = f"{self._API_BASE}/repos/{self.owner}/{self.repo}/releases"

        logger.info(
            "Fetching GitHub releases: %s/%s (tool=%s, version=%s)",
            self.owner,
            self.repo,
            tool_name,
            version,
        )

        resp = requests.get(url, headers=self.headers, timeout=30)

        if resp.status_code >= 400:
            raise ConnectorError(
                f"GitHub API error: {resp.status_code} {resp.reason}",
                status_code=resp.status_code,
                url=url,
            )

        releases: List[Dict[str, Any]] = resp.json()

        if not releases:
            raise ConnectorError(
                f"No releases found for {self.owner}/{self.repo}",
                url=url,
            )

        # Normalize mỗi release về các fields cần thiết
        def _normalize(r: dict) -> dict:
            return {
                "tag_name": r.get("tag_name", ""),
                "body": r.get("body", ""),
                "published_at": r.get("published_at", ""),
                "html_url": r.get("html_url", ""),
            }

        if version == "latest":
            target = _normalize(releases[0])
            target["releases"] = [_normalize(r) for r in releases]
            return target

        # Tìm release khớp version
        for release in releases:
            tag = release.get("tag_name", "")
            # So sánh cả "v3.7.0" và "3.7.0"
            if tag == version or tag.lstrip("v") == version.lstrip("v"):
                return _normalize(release)

        raise ConnectorError(
            f"Version {version} not found in {self.owner}/{self.repo} releases "
            f"(available: {[r.get('tag_name') for r in releases[:10]]})",
            url=url,
        )


# =============================================================================
# Generic HTTP Connector
# =============================================================================

class HttpConnector(BaseConnector):
    """Generic HTTP connector cho Jira, official docs, và bất kỳ URL nào.

    Parameters
    ----------
    base_url : str
        Base URL, e.g. ``"https://issues.apache.org/jira"``.
    timeout : float
        Request timeout (seconds). Default 30.

    Usage
    -----
        jira = HttpConnector(base_url="https://issues.apache.org/jira")
        data = jira.fetch("kafka", version="3.7.0")
    """

    def __init__(
        self,
        base_url: str,
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def fetch(self, tool_name: str, version: str) -> dict:
        """Gọi URL và trả về response.

        Parameters
        ----------
        tool_name : str
            Tên tool (dùng cho logging).
        version : str
            Version — sẽ được append vào ``base_url`` nếu không rỗng.

        Returns
        -------
        dict
            - JSON response → trả về dict gốc.
            - HTML response → ``{"content": "<html>…", "content_type": "text/html"}``.
        """
        url = f"{self.base_url}/{version}" if version else self.base_url

        logger.info("HTTP fetch: %s (tool=%s)", url, tool_name)

        try:
            resp = requests.get(
                url,
                headers=self.headers,
                timeout=self.timeout,
            )
        except requests.ConnectionError as exc:
            raise ConnectorError(
                f"Connection failed: {exc}",
                url=url,
            ) from exc
        except requests.Timeout as exc:
            raise ConnectorError(
                f"Request timed out after {self.timeout}s",
                url=url,
            ) from exc

        if resp.status_code >= 400:
            raise ConnectorError(
                f"HTTP {resp.status_code}: {resp.reason}",
                status_code=resp.status_code,
                url=url,
            )

        content_type = resp.headers.get("Content-Type", "")

        # JSON response
        if "application/json" in content_type:
            data = resp.json()
            # Đảm bảo trả về dict (wrap list nếu cần)
            if isinstance(data, list):
                return {"items": data, "source_url": url}
            data.setdefault("source_url", url)
            return data

        # HTML / text response
        return {
            "content": resp.text,
            "content_type": content_type,
            "source_url": url,
        }
