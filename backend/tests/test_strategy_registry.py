from __future__ import annotations

from app.strategies.registry import strategy_registry


def test_orb_registered():
    strat = strategy_registry.get("orb_v1")
    assert strat is not None
    assert strat.name == "orb_v1"


def test_list_all():
    all_strats = strategy_registry.list_all()
    assert any(s["name"] == "orb_v1" for s in all_strats)


def test_get_unknown_raises():
    import pytest
    with pytest.raises(KeyError):
        strategy_registry.get("nonexistent_strategy")
