from __future__ import annotations

from fastapi import APIRouter

from app.api import auth, engine, universe, history, status, positions, analytics, strategies, backtests, settings

router = APIRouter()

router.include_router(auth.router, tags=["auth"])
router.include_router(engine.router, prefix="/api/engine", tags=["engine"])
router.include_router(universe.router, prefix="/api/universe", tags=["universe"])
router.include_router(history.router, prefix="/api/history", tags=["history"])
router.include_router(status.router, prefix="/api", tags=["status"])
router.include_router(positions.router, prefix="/api", tags=["positions"])
router.include_router(analytics.router, prefix="/api", tags=["analytics"])
router.include_router(strategies.router, prefix="/api", tags=["strategies"])
router.include_router(backtests.router, prefix="/api/backtests", tags=["backtests"])
router.include_router(settings.router, prefix="/api/settings", tags=["settings"])
