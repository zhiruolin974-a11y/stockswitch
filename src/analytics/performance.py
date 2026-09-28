from __future__ import annotations

import math
import statistics

from src.backtest.models import EquityPoint, RoundTrip


class PerformanceAnalyzer:
    def __init__(self, risk_free_rate: float = 0.02, annualization_factor: int = 252):
        self.risk_free_rate = risk_free_rate
        self.annualization_factor = annualization_factor

    def analyze(self, initial_equity: float, curve: list[EquityPoint], trades: list[RoundTrip]) -> dict:
        if not curve:
            raise ValueError("Equity curve is empty")
        final = curve[-1].total_equity
        total = final / initial_equity - 1
        returns = [later.total_equity / earlier.total_equity - 1
                   for earlier, later in zip(curve, curve[1:]) if earlier.total_equity > 0]
        annualized = ((final / initial_equity) ** (self.annualization_factor / len(returns)) - 1
                      if returns and final > 0 else None)
        volatility = (statistics.stdev(returns) * math.sqrt(self.annualization_factor)
                      if len(returns) >= 2 else None)
        sharpe = ((statistics.mean(returns) - self.risk_free_rate / self.annualization_factor)
                  / statistics.stdev(returns) * math.sqrt(self.annualization_factor)
                  if len(returns) >= 2 and statistics.stdev(returns) > 0 else None)
        trough = min(curve, key=lambda item: item.drawdown)
        earlier = [point for point in curve if point.timestamp <= trough.timestamp]
        peak = max(earlier, key=lambda item: item.total_equity)
        wins = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
        losses = [trade.net_pnl for trade in trades if trade.net_pnl < 0]
        return {
            "initial_equity": initial_equity, "final_equity": final, "total_return": total,
            "annualized_return": annualized, "max_drawdown": min(point.drawdown for point in curve),
            "peak_date": peak.timestamp.date().isoformat(), "trough_date": trough.timestamp.date().isoformat(),
            "volatility": volatility, "sharpe": sharpe,
            "win_rate": len(wins) / len(trades) if trades else None,
            "loss_rate": len(losses) / len(trades) if trades else None,
            "total_trades": len(trades), "winning_trades": len(wins), "losing_trades": len(losses),
            "average_win": statistics.mean(wins) if wins else None,
            "average_loss": statistics.mean(losses) if losses else None,
            "profit_factor": sum(wins) / -sum(losses) if losses else None,
            "average_holding_period": statistics.mean(t.holding_period for t in trades) if trades else None,
            "benchmark_return": (curve[-1].benchmark_equity / initial_equity - 1 if curve else None),
        }
