from __future__ import annotations

from fastapi import APIRouter

from app.strategies.registry import strategy_registry

router = APIRouter()


@router.get("/strategies")
def list_strategies():
    return strategy_registry.list_all()
