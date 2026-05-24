"""
FastAPI application for Ads Budget Optimizer API.

Provides REST endpoints for the frontend dashboard.
"""

import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from src.bandit_ads.api.routes import campaigns, dashboard, recommendations, optimizer, incrementality, ask, data, forecasting, scenarios, export, attribution, mmm
from src.bandit_ads.utils import get_logger

logger = get_logger('api')

# Create FastAPI app
app = FastAPI(
    title="Ads Budget Optimizer API",
    description="REST API for the Ads Budget Optimizer dashboard",
    version="1.0.0"
)

# CORS middleware - allow frontend to access API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["campaigns"])
app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["recommendations"])
app.include_router(optimizer.router, prefix="/api/optimizer", tags=["optimizer"])
app.include_router(incrementality.router, prefix="/api/incrementality", tags=["incrementality"])
app.include_router(ask.router, prefix="/api/ask", tags=["ask"])
app.include_router(data.router, prefix="/api/data", tags=["data"])
app.include_router(forecasting.router, prefix="/api/forecasting", tags=["forecasting"])
app.include_router(scenarios.router, prefix="/api/scenarios", tags=["scenarios"])
app.include_router(export.router, prefix="/api/export", tags=["export"])
app.include_router(attribution.router, prefix="/api/attribution", tags=["attribution"])
app.include_router(mmm.router, prefix="/api/mmm", tags=["mmm"])


def _optimizer_enabled() -> bool:
    """Whether to spin up the continuous optimizer on API boot.

    Default off so the test suite and ad-hoc API runs don't start a
    background loop that writes to the production DB. Flip via
    IPSA_OPTIMIZER_ENABLED=1.
    """
    return os.getenv("IPSA_OPTIMIZER_ENABLED", "0").strip().lower() in ("1", "true", "yes")


@app.on_event("startup")
async def _startup_optimizer():
    if not _optimizer_enabled():
        logger.info("Optimizer not enabled on startup (set IPSA_OPTIMIZER_ENABLED=1 to enable)")
        return
    try:
        from src.bandit_ads.optimization_service import get_optimization_service
        service = get_optimization_service()
        service.start()
        logger.info("Continuous optimization service started via API startup hook")
    except Exception as e:
        logger.error(f"Failed to start optimization service: {e}", exc_info=True)


@app.on_event("shutdown")
async def _shutdown_optimizer():
    if not _optimizer_enabled():
        return
    try:
        from src.bandit_ads.optimization_service import get_optimization_service
        service = get_optimization_service()
        service.stop()
        logger.info("Continuous optimization service stopped via API shutdown hook")
    except Exception as e:
        logger.error(f"Error stopping optimization service: {e}", exc_info=True)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Ads Budget Optimizer API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    try:
        from src.bandit_ads.database import get_db_manager
        db_manager = get_db_manager()
        db_healthy = db_manager.health_check()
        
        return {
            "status": "healthy" if db_healthy else "degraded",
            "database": "connected" if db_healthy else "disconnected",
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }
        )


@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    """Global exception handler."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": str(exc),
            "timestamp": datetime.utcnow().isoformat()
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
