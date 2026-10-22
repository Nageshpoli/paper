from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter()


class SettingsPatch(BaseModel):
    virtual_capital: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_position_notional: Optional[float] = None
    risk_per_trade_pct: Optional[float] = None
    max_entries_per_day: Optional[int] = None
    max_daily_loss: Optional[float] = None
    max_total_exposure: Optional[float] = None
    max_positions_per_sector: Optional[int] = None
    minimum_relative_volume: Optional[float] = None
    minimum_median_traded_value: Optional[float] = None
    maximum_spread_bps: Optional[float] = None


@router.get("")
def get_settings_view():
    s = get_settings()
    return {
        "virtual_capital": s.virtual_capital,
        "max_open_positions": s.max_open_positions,
        "max_position_notional": s.max_position_notional,
        "risk_per_trade_pct": s.risk_per_trade_pct,
        "max_entries_per_day": s.max_entries_per_day,
        "max_daily_loss": s.max_daily_loss,
        "max_total_exposure": s.max_total_exposure,
        "max_positions_per_sector": s.max_positions_per_sector,
        "minimum_relative_volume": s.minimum_relative_volume,
        "minimum_median_traded_value": s.minimum_median_traded_value,
        "maximum_spread_bps": s.maximum_spread_bps,
        "paper_only": s.paper_only,
    }


@router.patch("")
def patch_settings(patch: SettingsPatch):
    """
    Runtime settings overrides are not persisted between restarts.
    To make them permanent, edit the .env file.
    """
    s = get_settings()
    for field, value in patch.model_dump(exclude_none=True).items():
        if hasattr(s, field):
            object.__setattr__(s, field, value)
    return get_settings_view()
