"""
DataStack Compass — FastAPI Backend
====================================

API Gateway cho nền tảng quản trị rủi ro phiên bản phần mềm.
Query StarRocks (External Catalog → Delta Lake trên MinIO) và trả về
JSON chuẩn ``{data, meta, errors}``.

Run (dev):
    uvicorn api.main:app --reload --host 0.0.0.0 --port 8000

Endpoints:
    GET  /health              — Health check
    GET  /api/v1/tools/...    — Tool summary & details
    GET  /api/v1/cves/...     — CVE data
    GET  /api/v1/analysis/... — Risk analysis
    GET  /api/v1/governance/  — Governance dashboards
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.database import check_db_connection, close_pool
from api.models.response import BaseResponse
from api.routers import analysis, cves, governance, tools, assets, search

# =============================================================================
# Logging
# =============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("api")

# =============================================================================
# App version
# =============================================================================

APP_VERSION = "1.0.0"

# =============================================================================
# Lifespan (startup / shutdown)
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify DB connection. Shutdown: close connection pool."""
    logger.info("DataStack Compass API v%s starting up…", APP_VERSION)

    db_ok = check_db_connection()
    if db_ok:
        logger.info("✓ StarRocks connection verified")
    else:
        logger.warning("⚠ StarRocks not reachable — API will start but DB queries will fail")

    yield

    logger.info("Shutting down — closing DB pool")
    close_pool()


# =============================================================================
# FastAPI app
# =============================================================================

app = FastAPI(
    title="DataStack Compass API",
    description=(
        "API cho nền tảng quản trị rủi ro phiên bản phần mềm. "
        "Thu thập, xử lý và hiển thị thông tin Release Notes, CVE, "
        "Breaking Changes, License thay đổi từ các Data Stack tools."
    ),
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# =============================================================================
# CORS middleware
# =============================================================================

_frontend_origin = os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _frontend_origin.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# Request logging middleware
# =============================================================================


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log mỗi request với thời gian xử lý."""
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - start) * 1000

    logger.info(
        "%s %s → %d (%.1fms)",
        request.method,
        request.url.path,
        response.status_code,
        elapsed_ms,
    )
    return response


# =============================================================================
# Global exception handler — trả về JSON chuẩn {error, detail, status_code}
# =============================================================================


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all exception handler — đảm bảo API luôn trả về JSON."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)

    status_code = getattr(exc, "status_code", 500)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": type(exc).__name__,
            "detail": str(exc),
            "status_code": status_code,
        },
    )


# =============================================================================
# Health check
# =============================================================================


@app.get(
    "/health",
    tags=["system"],
    summary="Health check",
    response_model=None,
)
async def health_check():
    """Kiểm tra trạng thái API và kết nối database."""
    db_ok = check_db_connection()

    return {
        "status": "ok" if db_ok else "degraded",
        "db": db_ok,
        "version": APP_VERSION,
    }


# =============================================================================
# Include routers
# =============================================================================

app.include_router(tools.router, prefix="/api/v1/tools", tags=["tools"])
app.include_router(cves.router, prefix="/api/v1/cves", tags=["cves"])
app.include_router(analysis.router, prefix="/api/v1/analysis", tags=["analysis"])
app.include_router(governance.router, prefix="/api/v1/governance", tags=["governance"])
app.include_router(assets.router, prefix="/api/v1/assets", tags=["assets"])
app.include_router(search.router, prefix="/api/v1/search", tags=["search"])
