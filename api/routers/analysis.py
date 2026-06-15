"""
DataStack Compass — Analysis Router (Version Diff + Stack Comparator)
======================================================================

Endpoints cho Analysis Workspace: so sánh versions, so sánh tools,
và tìm đường upgrade an toàn.

Prefix: /api/v1/analysis

SQL syntax: StarRocks (MySQL-compatible).
    - %s placeholders
    - IFNULL, CASE WHEN, FIELD()
    - KHÔNG dùng PostgreSQL syntax

Caching: In-memory dict với TTL 5 phút cho các query expensive.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from api.database import execute_query, execute_query_one, get_db
from api.models.response import BaseResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# =============================================================================
# Table references
# =============================================================================

_GOLD_SUMMARY = "minio_catalog.gold.gold_tool_summary"
_SILVER_RELEASES = "minio_catalog.silver.silver_releases"
_SILVER_CVES = "minio_catalog.silver.silver_cves"
_SILVER_COMPAT = "minio_catalog.silver.silver_compatibility"
_SILVER_LICENSES = "minio_catalog.silver.silver_license_changes"
_SILVER_CONFIG = "minio_catalog.silver.silver_config_changes"

# =============================================================================
# In-memory cache with TTL
# =============================================================================

_CACHE_TTL_SECONDS = 300  # 5 phút

# {cache_key: (timestamp, data)}
_cache: Dict[str, Tuple[float, Any]] = {}


def _cache_key(*args: Any) -> str:
    """Tạo deterministic cache key từ arguments."""
    raw = json.dumps(args, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[Any]:
    """Lấy giá trị từ cache nếu chưa expired."""
    entry = _cache.get(key)
    if entry is None:
        return None

    ts, data = entry
    if time.time() - ts > _CACHE_TTL_SECONDS:
        # Expired → xóa
        del _cache[key]
        return None

    return data


def _cache_set(key: str, data: Any) -> None:
    """Lưu giá trị vào cache với timestamp hiện tại."""
    # Giới hạn cache size — evict oldest khi quá 200 entries
    if len(_cache) >= 200:
        oldest_key = min(_cache, key=lambda k: _cache[k][0])
        del _cache[oldest_key]

    _cache[key] = (time.time(), data)


# =============================================================================
# Helpers
# =============================================================================

def _parse_semver_tuple(version: Optional[str]) -> Tuple[int, ...]:
    """Parse version thành tuple of ints cho comparison.

    >>> _parse_semver_tuple("3.7.1")
    (3, 7, 1)
    >>> _parse_semver_tuple("v3.7")
    (3, 7, 0)
    """
    if not version:
        return (0, 0, 0)

    cleaned = version.strip().lstrip("vV").split("-")[0]
    parts = []
    for p in cleaned.split(".")[:3]:
        try:
            parts.append(int(p))
        except ValueError:
            parts.append(0)

    while len(parts) < 3:
        parts.append(0)
    return tuple(parts)


def _semver_between(
    version: str,
    from_version: str,
    to_version: str,
    inclusive_from: bool = False,
    inclusive_to: bool = True,
) -> bool:
    """Kiểm tra version nằm giữa from_version và to_version (semver)."""
    v = _parse_semver_tuple(version)
    v_from = _parse_semver_tuple(from_version)
    v_to = _parse_semver_tuple(to_version)

    lower_ok = v >= v_from if inclusive_from else v > v_from
    upper_ok = v <= v_to if inclusive_to else v < v_to
    return lower_ok and upper_ok


def _parse_json_field(value: Any) -> List[str]:
    """Safely parse JSON array field từ StarRocks (có thể là str hoặc list)."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            return []
    return []


# =============================================================================
# Existing endpoints (giữ lại)
# =============================================================================


@router.get(
    "/risk-matrix",
    summary="Risk matrix — tổng hợp rủi ro tất cả tools",
    response_model=BaseResponse,
)
async def risk_matrix(db=Depends(get_db)):
    """Ma trận rủi ro: tool × severity. Dùng cho dashboard tổng quan."""
    cache_key = _cache_key("risk_matrix")
    cached = _cache_get(cache_key)
    if cached is not None:
        return BaseResponse(data=cached, meta={"cached": True})

    sql = f"""
        SELECT
            g.tool_name,
            g.latest_version,
            g.total_cve_critical,
            g.total_cve_high,
            g.eol_date,
            CASE
                WHEN g.total_cve_critical > 0 THEN 'critical'
                WHEN g.total_cve_high > 3 THEN 'high'
                WHEN g.total_cve_high > 0 THEN 'medium'
                ELSE 'low'
            END AS risk_level
        FROM {_GOLD_SUMMARY} g
        ORDER BY g.total_cve_critical DESC, g.total_cve_high DESC
    """

    with db.cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall()

    _cache_set(cache_key, rows)

    return BaseResponse(
        data=rows,
        meta={"total_tools": len(rows)},
    )


@router.get(
    "/dependency-graph",
    summary="Dependency Graph data",
    response_model=BaseResponse,
)
async def dependency_graph(db=Depends(get_db)):
    cache_key = _cache_key("dependency_graph")
    cached = _cache_get(cache_key)
    if cached is not None:
        return BaseResponse(data=cached, meta={"cached": True})

    # Nodes
    nodes_sql = f"""
        SELECT
            g.tool_name AS id,
            g.latest_version AS version,
            g.total_cve_critical AS cve_critical,
            CASE
                WHEN g.eol_date IS NOT NULL AND g.eol_date < CURRENT_DATE() THEN 'EOL'
                WHEN g.eol_date IS NOT NULL AND g.eol_date < DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY) THEN 'Maintenance'
                ELSE 'Active'
            END AS lifecycle
        FROM {_GOLD_SUMMARY} g
    """
    
    # Edges
    edges_sql = f"""
        SELECT
            c.tool_name AS from_tool,
            c.dependencies
        FROM {_SILVER_COMPAT} c
        JOIN {_GOLD_SUMMARY} g ON c.tool_name = g.tool_name AND c.version = g.latest_version
    """

    with db.cursor() as cursor:
        cursor.execute(nodes_sql)
        nodes = cursor.fetchall()
        
        cursor.execute(edges_sql)
        edges_raw = cursor.fetchall()

    edges = []
    valid_nodes = {n["id"] for n in nodes}

    for row in edges_raw:
        from_tool = row["from_tool"]
        deps = row.get("dependencies")
        if not deps:
            continue
            
        if isinstance(deps, str):
            try:
                deps = json.loads(deps)
            except Exception:
                deps = {}
                
        if isinstance(deps, dict):
            for to_tool, ver_req in deps.items():
                if to_tool in valid_nodes:
                    edges.append({
                        "from": from_tool,
                        "to": to_tool,
                        "version_required": ver_req,
                        "type": "requires"
                    })

    data = {
        "nodes": nodes,
        "edges": edges
    }

    _cache_set(cache_key, data)
    return BaseResponse(data=data)


@router.get(
    "/breaking-changes",
    summary="Breaking changes gần đây",
    response_model=BaseResponse,
)
async def recent_breaking_changes(
    tool_name: Optional[str] = Query(None, description="Filter theo tool"),
    limit: int = Query(20, ge=1, le=100),
    db=Depends(get_db),
):
    """Liệt kê releases có breaking changes, mới nhất trước."""
    where = "WHERE breaking_changes IS NOT NULL"
    params: list = []

    if tool_name:
        where += " AND tool_name = %s"
        params.append(tool_name)

    sql = f"""
        SELECT tool_name, version, release_date, breaking_changes, breaking_changes_enriched
        FROM {_SILVER_RELEASES}
        {where}
        ORDER BY release_date DESC
        LIMIT %s
    """
    params.append(limit)

    with db.cursor() as cursor:
        cursor.execute(sql, tuple(params))
        rows = cursor.fetchall()

    return BaseResponse(
        data=rows,
        meta={"total": len(rows), "filter_tool": tool_name},
    )


# =============================================================================
# 1. Version Diff
# =============================================================================


@router.get(
    "/version-diff",
    summary="So sánh 2 versions của cùng một tool",
    response_model=BaseResponse,
)
async def version_diff(
    tool: str = Query(
        ..., min_length=1, description="Tên tool (e.g. apache-kafka)"
    ),
    from_version: str = Query(
        ..., min_length=1, description="Version gốc (e.g. 3.5.0)"
    ),
    to_version: str = Query(
        ..., min_length=1, description="Version đích (e.g. 3.6.0)"
    ),
    db=Depends(get_db),
):
    """So sánh 2 versions: breaking changes, CVEs resolved/new, features, bugs.

    Logic
    -----
    1. Query ``silver_releases`` cho cả 2 versions.
    2. Lấy tất cả releases nằm giữa (from_version, to_version].
    3. Tổng hợp breaking changes tích lũy.
    4. Join ``silver_cves``: resolved = CVEs affect from nhưng fixed ≤ to,
       new = CVEs affect to nhưng không affect from.
    """
    # ── Cache ────────────────────────────────────────────────────────────
    ck = _cache_key("version_diff", tool, from_version, to_version)
    cached = _cache_get(ck)
    if cached is not None:
        return BaseResponse(data=cached, meta={"cached": True})

    # ── Validate versions exist ──────────────────────────────────────────
    check_sql = f"""
        SELECT version, release_date, breaking_changes, breaking_changes_enriched, deprecated_apis
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s AND version IN (%s, %s)
    """
    with db.cursor() as cursor:
        cursor.execute(check_sql, (tool, from_version, to_version))
        found_rows = cursor.fetchall()

    found_versions = {row["version"] for row in found_rows}

    missing = []
    if from_version not in found_versions:
        missing.append(from_version)
    if to_version not in found_versions:
        missing.append(to_version)

    if missing:
        raise HTTPException(
            status_code=404,
            detail=f"Version(s) not found for {tool}: {', '.join(missing)}",
        )

    # ── All intermediate releases (from, to] ─────────────────────────────
    all_releases_sql = f"""
        SELECT version, release_date, breaking_changes, breaking_changes_enriched, deprecated_apis
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s
        ORDER BY version ASC
    """
    with db.cursor() as cursor:
        cursor.execute(all_releases_sql, (tool,))
        all_releases = cursor.fetchall()

    # Filter bằng semver comparison (chính xác hơn string comparison)
    intermediate_releases = [
        r for r in all_releases
        if _semver_between(r["version"], from_version, to_version,
                           inclusive_from=False, inclusive_to=True)
    ]

    # ── Tổng hợp breaking changes + deprecated APIs ─────────────────────
    all_breaking: List[Any] = []
    all_deprecated: List[str] = []
    new_features_count = 0
    bug_fixes_count = 0

    for rel in intermediate_releases:
        bc_enriched = _parse_json_field(rel.get("breaking_changes_enriched"))
        if bc_enriched:
            all_breaking.extend(bc_enriched)
        else:
            bc = _parse_json_field(rel.get("breaking_changes"))
            # convert string to mock enriched
            all_breaking.extend([
                {"text": b, "category": "UNCATEGORIZED", "impact": "Low", "action_required": False}
                for b in bc
            ])

        dep = _parse_json_field(rel.get("deprecated_apis"))
        all_deprecated.extend(dep)

    # ── CVE analysis ─────────────────────────────────────────────────────
    cves_sql = f"""
        SELECT cve_id, affected_versions, fixed_in_version,
               cvss_score, severity, description
        FROM {_SILVER_CVES}
        WHERE tool_name = %s
        ORDER BY cvss_score DESC
    """
    with db.cursor() as cursor:
        cursor.execute(cves_sql, (tool,))
        all_cves = cursor.fetchall()

    resolved_cves: List[dict] = []
    new_cves: List[dict] = []

    from_tuple = _parse_semver_tuple(from_version)
    to_tuple = _parse_semver_tuple(to_version)

    for cve in all_cves:
        affected = _parse_json_field(cve.get("affected_versions"))
        fixed_in = cve.get("fixed_in_version")
        fixed_tuple = _parse_semver_tuple(fixed_in) if fixed_in else (999, 999, 999)

        # CVE affects from_version?
        affects_from = from_version in affected or any(
            _parse_semver_tuple(v) <= from_tuple for v in affected if v != "unknown"
        )

        # CVE affects to_version?
        affects_to = to_version in affected or (
            fixed_tuple > to_tuple  # chưa fixed trong to_version
        )

        # Resolved: affected from, fixed <= to
        if affects_from and fixed_in and fixed_tuple <= to_tuple:
            resolved_cves.append({
                "cve_id": cve["cve_id"],
                "cvss_score": cve.get("cvss_score"),
                "severity": cve.get("severity"),
                "fixed_in_version": fixed_in,
            })

        # New: không affect from nhưng affect to (mới phát hiện)
        if not affects_from and affects_to:
            new_cves.append({
                "cve_id": cve["cve_id"],
                "cvss_score": cve.get("cvss_score"),
                "severity": cve.get("severity"),
                "description": (cve.get("description") or "")[:200],
            })

    # ── Config Changes analysis ──────────────────────────────────────────
    config_sql = f"""
        SELECT to_version, param_name, old_default, new_default, change_type, impact_level
        FROM {_SILVER_CONFIG}
        WHERE tool_name = %s
    """
    with db.cursor() as cursor:
        cursor.execute(config_sql, (tool,))
        all_configs = cursor.fetchall()

    config_changes = []
    for c in all_configs:
        if _semver_between(c["to_version"], from_version, to_version, inclusive_from=False, inclusive_to=True):
            mapped_type = "modify"
            if c["change_type"] == "new_param": mapped_type = "add"
            elif c["change_type"] == "deprecated": mapped_type = "remove"
            config_changes.append({
                "key": c["param_name"],
                "type": mapped_type,
                "oldVal": c.get("old_default"),
                "newVal": c.get("new_default"),
                "impact_level": c.get("impact_level")
            })

    # ── Issue counts (estimate từ intermediate releases) ─────────────────
    # Các issues type được đếm nếu có dữ liệu
    versions_with_breaking = [
        r["version"] for r in intermediate_releases
        if _parse_json_field(r.get("breaking_changes"))
    ]

    # ── Build result ─────────────────────────────────────────────────────
    result = {
        "tool_name": tool,
        "from_version": from_version,
        "to_version": to_version,
        "intermediate_versions": [r["version"] for r in intermediate_releases],
        "diff": {
            "new_breaking_changes": all_breaking,
            "new_deprecated_apis": all_deprecated,
            "resolved_cves": resolved_cves,
            "new_cves": new_cves,
            "config_changes": config_changes,
            "versions_with_breaking_changes": versions_with_breaking,
            "total_intermediate_releases": len(intermediate_releases),
        },
    }

    _cache_set(ck, result)

    return BaseResponse(
        data=result,
        meta={
            "breaking_changes_count": len(all_breaking),
            "resolved_cves_count": len(resolved_cves),
            "new_cves_count": len(new_cves),
        },
    )


# =============================================================================
# 2. Stack Comparator
# =============================================================================


@router.get(
    "/stack-comparator",
    summary="So sánh nhiều tools cùng lúc",
    response_model=BaseResponse,
)
async def stack_comparator(
    tools: str = Query(
        ...,
        min_length=1,
        description="Danh sách tool_name phân cách bởi dấu phẩy (max 5)",
        examples=["apache-kafka,apache-flink,apache-spark"],
    ),
    db=Depends(get_db),
):
    """So sánh nhiều tools: version, license, EOL, CVEs, dependencies.

    Max 5 tools per request để giới hạn query load.
    """
    # ── Parse & validate ─────────────────────────────────────────────────
    tool_list = [t.strip() for t in tools.split(",") if t.strip()]

    if len(tool_list) < 2:
        raise HTTPException(
            status_code=400,
            detail="Cần ít nhất 2 tools để so sánh. Phân cách bằng dấu phẩy.",
        )

    if len(tool_list) > 5:
        raise HTTPException(
            status_code=400,
            detail=f"Tối đa 5 tools per request. Đã nhận {len(tool_list)}.",
        )

    # ── Cache ────────────────────────────────────────────────────────────
    ck = _cache_key("stack_comparator", sorted(tool_list))
    cached = _cache_get(ck)
    if cached is not None:
        return BaseResponse(data=cached, meta={"cached": True})

    # ── Gold summary cho các tools ───────────────────────────────────────
    placeholders = ", ".join(["%s"] * len(tool_list))

    gold_sql = f"""
        SELECT
            tool_name, latest_version, eol_date, eos_date,
            total_cve_critical, total_cve_high, last_updated,
            CASE
                WHEN eol_date IS NOT NULL AND eol_date < CURRENT_DATE() THEN 'EOL'
                WHEN eol_date IS NOT NULL AND eol_date < DATE_ADD(CURRENT_DATE(), INTERVAL 90 DAY) THEN 'Maintenance'
                ELSE 'Active'
            END AS lifecycle_status,
            CASE
                WHEN total_cve_critical > 0 THEN 'critical'
                WHEN total_cve_high > 3 THEN 'high'
                WHEN total_cve_high > 0 THEN 'medium'
                ELSE 'low'
            END AS risk_level
        FROM {_GOLD_SUMMARY}
        WHERE tool_name IN ({placeholders})
    """

    with db.cursor() as cursor:
        cursor.execute(gold_sql, tuple(tool_list))
        gold_rows = cursor.fetchall()

    found_tools = {row["tool_name"] for row in gold_rows}
    missing_tools = [t for t in tool_list if t not in found_tools]

    # ── CVE severity breakdown per tool ──────────────────────────────────
    cve_sql = f"""
        SELECT
            tool_name,
            severity,
            COUNT(*) AS count
        FROM {_SILVER_CVES}
        WHERE tool_name IN ({placeholders})
        GROUP BY tool_name, severity
    """

    with db.cursor() as cursor:
        cursor.execute(cve_sql, tuple(tool_list))
        cve_rows = cursor.fetchall()

    # Build per-tool CVE breakdown
    cve_by_tool: Dict[str, Dict[str, int]] = {}
    for row in cve_rows:
        tn = row["tool_name"]
        if tn not in cve_by_tool:
            cve_by_tool[tn] = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        cve_by_tool[tn][row["severity"]] = row["count"]

    # ── Compatibility / dependencies per tool ────────────────────────────
    deps_by_tool: Dict[str, Any] = {}
    try:
        # Lấy dependencies cho latest version mỗi tool
        for row in gold_rows:
            tn = row["tool_name"]
            ver = row.get("latest_version")
            if not ver:
                continue

            dep_sql = f"""
                SELECT dependencies
                FROM {_SILVER_COMPAT}
                WHERE tool_name = %s AND version = %s
                LIMIT 1
            """
            with db.cursor() as cursor:
                cursor.execute(dep_sql, (tn, ver))
                dep_row = cursor.fetchone()

            if dep_row and dep_row.get("dependencies"):
                deps = dep_row["dependencies"]
                if isinstance(deps, str):
                    try:
                        deps = json.loads(deps)
                    except (json.JSONDecodeError, TypeError):
                        deps = {}
                deps_by_tool[tn] = deps
    except Exception:
        logger.debug("silver_compatibility not accessible — skipping")

    # ── License info per tool ────────────────────────────────────────────
    license_by_tool: Dict[str, str] = {}
    try:
        lic_sql = f"""
            SELECT tool_name, new_license
            FROM {_SILVER_LICENSES}
            WHERE tool_name IN ({placeholders})
            ORDER BY changed_at DESC
        """
        with db.cursor() as cursor:
            cursor.execute(lic_sql, tuple(tool_list))
            lic_rows = cursor.fetchall()

        # Lấy license mới nhất per tool (đã ORDER BY DESC)
        for row in lic_rows:
            tn = row["tool_name"]
            if tn not in license_by_tool:
                license_by_tool[tn] = row["new_license"]
    except Exception:
        logger.debug("silver_license_changes not accessible — skipping")

    # ── Build comparison matrix ──────────────────────────────────────────
    comparison_matrix: Dict[str, Dict[str, Any]] = {
        "latest_version": {},
        "lifecycle_status": {},
        "risk_level": {},
        "eol_date": {},
        "license": {},
        "critical_cves": {},
        "high_cves": {},
        "total_cves": {},
        "java_requirement": {},
    }

    for row in gold_rows:
        tn = row["tool_name"]

        comparison_matrix["latest_version"][tn] = row.get("latest_version")
        comparison_matrix["lifecycle_status"][tn] = row.get("lifecycle_status")
        comparison_matrix["risk_level"][tn] = row.get("risk_level")
        comparison_matrix["eol_date"][tn] = (
            row["eol_date"].isoformat() if row.get("eol_date") else None
        )
        comparison_matrix["license"][tn] = license_by_tool.get(tn, "Apache 2.0")

        cve_info = cve_by_tool.get(tn, {})
        comparison_matrix["critical_cves"][tn] = cve_info.get("Critical", 0)
        comparison_matrix["high_cves"][tn] = cve_info.get("High", 0)
        comparison_matrix["total_cves"][tn] = sum(cve_info.values())

        tool_deps = deps_by_tool.get(tn, {})
        comparison_matrix["java_requirement"][tn] = tool_deps.get("java")

    result = {
        "tools": [t for t in tool_list if t in found_tools],
        "comparison_matrix": comparison_matrix,
        "missing_tools": missing_tools,
    }

    _cache_set(ck, result)

    return BaseResponse(
        data=result,
        meta={
            "requested_tools": len(tool_list),
            "found_tools": len(found_tools),
        },
    )


# =============================================================================
# 3. Upgrade Path
# =============================================================================


@router.get(
    "/upgrade-path",
    summary="Tìm đường upgrade an toàn giữa 2 versions",
    response_model=BaseResponse,
)
async def upgrade_path(
    tool: str = Query(..., min_length=1, description="Tên tool"),
    current: str = Query(..., min_length=1, description="Version hiện tại"),
    target: str = Query(..., min_length=1, description="Version đích"),
    db=Depends(get_db),
):
    """Tìm đường upgrade từ current → target qua các intermediate versions.

    Trả về list versions theo thứ tự, kèm:
    - Breaking changes tích lũy cho mỗi bước
    - CVEs ảnh hưởng tại mỗi bước
    - Recommendation: safe / caution / risky
    """
    # ── Cache ────────────────────────────────────────────────────────────
    ck = _cache_key("upgrade_path", tool, current, target)
    cached = _cache_get(ck)
    if cached is not None:
        return BaseResponse(data=cached, meta={"cached": True})

    # ── Validate semver order ────────────────────────────────────────────
    if _parse_semver_tuple(current) >= _parse_semver_tuple(target):
        raise HTTPException(
            status_code=400,
            detail=f"current ({current}) phải nhỏ hơn target ({target})",
        )

    # ── Lấy tất cả releases cho tool ────────────────────────────────────
    releases_sql = f"""
        SELECT version, release_date, breaking_changes, breaking_changes_enriched, deprecated_apis
        FROM {_SILVER_RELEASES}
        WHERE tool_name = %s
    """

    with db.cursor() as cursor:
        cursor.execute(releases_sql, (tool,))
        all_releases = cursor.fetchall()

    if not all_releases:
        raise HTTPException(
            status_code=404,
            detail=f"No releases found for tool '{tool}'",
        )

    # ── Filter & sort theo semver ────────────────────────────────────────
    # Lấy tất cả versions trong range [current, target]
    path_releases = [
        r for r in all_releases
        if _semver_between(r["version"], current, target,
                           inclusive_from=True, inclusive_to=True)
    ]

    # Sort theo semantic version
    path_releases.sort(key=lambda r: _parse_semver_tuple(r["version"]))

    if not path_releases:
        raise HTTPException(
            status_code=404,
            detail=f"No versions found between {current} and {target} for {tool}",
        )

    # ── CVEs cho tool ────────────────────────────────────────────────────
    cves_sql = f"""
        SELECT cve_id, affected_versions, fixed_in_version,
               cvss_score, severity
        FROM {_SILVER_CVES}
        WHERE tool_name = %s
    """

    with db.cursor() as cursor:
        cursor.execute(cves_sql, (tool,))
        all_cves = cursor.fetchall()

    # ── Build upgrade path ───────────────────────────────────────────────
    steps: List[dict] = []
    cumulative_breaking: List[str] = []
    cumulative_deprecated: List[str] = []

    for i, release in enumerate(path_releases):
        ver = release["version"]
        ver_tuple = _parse_semver_tuple(ver)

        # Breaking changes cho step này
        step_breaking = _parse_json_field(release.get("breaking_changes_enriched"))
        if not step_breaking:
            flat_bc = _parse_json_field(release.get("breaking_changes"))
            step_breaking = [
                {"text": b, "category": "UNCATEGORIZED", "impact": "Low", "action_required": False}
                for b in flat_bc
            ]
        step_deprecated = _parse_json_field(release.get("deprecated_apis"))

        if ver != current:
            # Đây là một upgrade step (không phải starting point)
            cumulative_breaking.extend(step_breaking)
            cumulative_deprecated.extend(step_deprecated)

        # CVEs active tại version này
        active_cves = []
        for cve in all_cves:
            fixed_in = cve.get("fixed_in_version")
            fixed_tuple = _parse_semver_tuple(fixed_in) if fixed_in else (999, 999, 999)

            # CVE active nếu chưa được fix tại version này
            if fixed_tuple > ver_tuple:
                active_cves.append({
                    "cve_id": cve["cve_id"],
                    "severity": cve.get("severity"),
                    "cvss_score": cve.get("cvss_score"),
                })

        # Recommendation per step
        critical_active = sum(1 for c in active_cves if c.get("severity") == "Critical")
        high_active = sum(1 for c in active_cves if c.get("severity") == "High")

        if critical_active > 0:
            recommendation = "risky"
        elif step_breaking or high_active > 2:
            recommendation = "caution"
        else:
            recommendation = "safe"

        steps.append({
            "version": ver,
            "release_date": (
                release["release_date"].isoformat()
                if release.get("release_date") else None
            ),
            "is_current": ver == current,
            "is_target": ver == target,
            "breaking_changes": step_breaking,
            "deprecated_apis": step_deprecated,
            "active_cves_count": len(active_cves),
            "active_critical_cves": critical_active,
            "recommendation": recommendation,
        })

    # ── Overall recommendation ───────────────────────────────────────────
    risky_steps = sum(1 for s in steps if s["recommendation"] == "risky")
    caution_steps = sum(1 for s in steps if s["recommendation"] == "caution")

    if risky_steps > 0:
        overall = "risky"
    elif caution_steps > len(steps) // 2:
        overall = "caution"
    elif cumulative_breaking:
        overall = "caution"
    else:
        overall = "safe"

    result = {
        "tool_name": tool,
        "current_version": current,
        "target_version": target,
        "total_steps": len(steps),
        "steps": steps,
        "cumulative_breaking_changes": cumulative_breaking,
        "cumulative_deprecated_apis": cumulative_deprecated,
        "overall_recommendation": overall,
    }

    _cache_set(ck, result)

    return BaseResponse(
        data=result,
        meta={
            "total_steps": len(steps),
            "breaking_changes_count": len(cumulative_breaking),
            "overall_recommendation": overall,
        },
    )


# =============================================================================
# 4. Config Diff
# =============================================================================

@router.get(
    "/config-diff",
    summary="Liệt kê config changes giữa 2 version",
    response_model=BaseResponse,
)
async def config_diff(
    tool: str = Query(..., min_length=1),
    from_version: str = Query(..., min_length=1),
    to_version: str = Query(..., min_length=1),
    db=Depends(get_db),
):
    ck = _cache_key("config_diff", tool, from_version, to_version)
    cached = _cache_get(ck)
    if cached is not None:
        return BaseResponse(data=cached, meta={"cached": True})

    sql = f"""
        SELECT to_version, param_name, old_default, new_default, change_type, impact_level
        FROM {_SILVER_CONFIG}
        WHERE tool_name = %s
    """
    with db.cursor() as cursor:
        cursor.execute(sql, (tool,))
        rows = cursor.fetchall()

    filtered = [
        r for r in rows
        if _semver_between(r["to_version"], from_version, to_version, inclusive_from=False, inclusive_to=True)
    ]
    
    # Group by change_type
    grouped = {
        "new_param": [],
        "changed_default": [],
        "deprecated": []
    }
    for r in filtered:
        ct = r["change_type"]
        if ct in grouped:
            grouped[ct].append(r)

    _cache_set(ck, grouped)
    return BaseResponse(data=grouped, meta={"total_changes": len(filtered)})
