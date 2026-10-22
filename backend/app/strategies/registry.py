from __future__ import annotations

from app.strategies.base import Strategy


class StrategyRegistry:
    """
    Central registry for all trading strategies.

    To add a new strategy:
      1. Create backend/app/strategies/my_strategy/strategy.py
      2. Implement the Strategy base class
      3. Register at the bottom of this file:
            registry.register(MyStrategy())
    """
    def __init__(self) -> None:
        self._strategies: dict[str, Strategy] = {}

    def register(self, strategy: Strategy) -> None:
        self._strategies[strategy.name] = strategy

    def get(self, name: str) -> Strategy:
        if name not in self._strategies:
            raise KeyError(f"Strategy '{name}' is not registered. "
                           f"Available: {list(self._strategies)}")
        return self._strategies[name]

    def list_all(self) -> list[dict]:
        return [{"name": s.name, "description": getattr(s, "description", "")}
                for s in self._strategies.values()]


strategy_registry = StrategyRegistry()

# ── Register strategies here ──────────────────────────────────────────────────
from app.strategies.orb.strategy import OpeningRangeBreakoutStrategy  # noqa: E402
strategy_registry.register(OpeningRangeBreakoutStrategy())
