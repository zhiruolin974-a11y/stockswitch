from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from src.portfolio.portfolio import Portfolio, Position
from src.trading.models import Fill, Order, Trade, TradingSignal


class TradeJournal:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.executescript("""
            CREATE TABLE IF NOT EXISTS quotes (id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS signals (id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT, strategy TEXT, side TEXT, reason TEXT, reference_price REAL);
            CREATE TABLE IF NOT EXISTS risk_decisions (id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT, accepted INTEGER, reason TEXT);
            CREATE TABLE IF NOT EXISTS orders (id TEXT PRIMARY KEY, timestamp TEXT, symbol TEXT, side TEXT, quantity INTEGER, status TEXT, signal_price REAL, order_price REAL, reject_reason TEXT, strategy TEXT);
            CREATE TABLE IF NOT EXISTS fills (id INTEGER PRIMARY KEY, order_id TEXT, timestamp TEXT, symbol TEXT, quantity INTEGER, fill_price REAL, slippage REAL, commission REAL, stamp_tax REAL);
            CREATE TABLE IF NOT EXISTS trades (id INTEGER PRIMARY KEY, order_id TEXT, timestamp TEXT, symbol TEXT, side TEXT, quantity INTEGER, price REAL, fees REAL, realized_pnl REAL);
            CREATE TABLE IF NOT EXISTS positions (id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT, quantity INTEGER, available_quantity INTEGER, average_cost REAL, market_price REAL);
            CREATE TABLE IF NOT EXISTS portfolio_snapshots (id INTEGER PRIMARY KEY, timestamp TEXT, state_json TEXT);
            CREATE TABLE IF NOT EXISTS strategy_runs (id INTEGER PRIMARY KEY, timestamp TEXT, symbol TEXT, outcome TEXT);
        """)

    def record_signal(self, signal: TradingSignal) -> None:
        with self.connection:
            self.connection.execute("INSERT INTO signals(timestamp,symbol,strategy,side,reason,reference_price) VALUES(?,?,?,?,?,?)",
                                    (signal.timestamp.isoformat(), signal.symbol, signal.strategy, signal.side.value, signal.reason, signal.reference_price))

    def record_risk(self, at: datetime, symbol: str, accepted: bool, reason: str) -> None:
        with self.connection:
            self.connection.execute("INSERT INTO risk_decisions(timestamp,symbol,accepted,reason) VALUES(?,?,?,?)", (at.isoformat(), symbol, int(accepted), reason))

    def record_order(self, order: Order) -> None:
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO orders VALUES(?,?,?,?,?,?,?,?,?,?)",
                                    (order.id, order.created_at.isoformat(), order.symbol, order.side.value, order.quantity,
                                     order.status.value, order.signal_price, order.order_price, order.reject_reason, order.strategy))

    def record_execution(self, fill: Fill, trade: Trade) -> None:
        with self.connection:
            self.connection.execute("INSERT INTO fills(order_id,timestamp,symbol,quantity,fill_price,slippage,commission,stamp_tax) VALUES(?,?,?,?,?,?,?,?)",
                                    (fill.order_id, fill.timestamp.isoformat(), fill.symbol, fill.quantity, fill.fill_price,
                                     fill.slippage, fill.commission, fill.stamp_tax))
            self.connection.execute("INSERT INTO trades(order_id,timestamp,symbol,side,quantity,price,fees,realized_pnl) VALUES(?,?,?,?,?,?,?,?)",
                                    (trade.order_id, trade.timestamp.isoformat(), trade.symbol, trade.side.value, trade.quantity,
                                     trade.price, trade.fees, trade.realized_pnl))

    def record_snapshot(self, portfolio: Portfolio, at: datetime) -> None:
        state = {
            "initial_cash": portfolio.initial_cash, "available_cash": portfolio.available_cash,
            "realized_pnl": portfolio.realized_pnl, "current_day": portfolio.current_day.isoformat() if portfolio.current_day else None,
            "day_start_equity": portfolio.day_start_equity,
            "positions": {symbol: asdict(position) for symbol, position in portfolio.positions.items()},
        }
        with self.connection:
            self.connection.execute("INSERT INTO portfolio_snapshots(timestamp,state_json) VALUES(?,?)", (at.isoformat(), json.dumps(state)))
            self.connection.executemany("INSERT INTO positions(timestamp,symbol,quantity,available_quantity,average_cost,market_price) VALUES(?,?,?,?,?,?)",
                [(at.isoformat(), p.symbol, p.quantity, p.available_quantity, p.average_cost, p.market_price) for p in portfolio.positions.values()])

    def load_portfolio(self, fallback_initial_cash: float) -> Portfolio:
        row = self.connection.execute("SELECT state_json FROM portfolio_snapshots ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return Portfolio(fallback_initial_cash)
        data = json.loads(row[0])
        portfolio = Portfolio(float(data["initial_cash"]))
        portfolio.available_cash = float(data["available_cash"])
        portfolio.realized_pnl = float(data["realized_pnl"])
        portfolio.current_day = date.fromisoformat(data["current_day"]) if data["current_day"] else None
        portfolio.day_start_equity = float(data["day_start_equity"])
        portfolio.positions = {symbol: Position(**payload) for symbol, payload in data["positions"].items()}
        return portfolio

    def count(self, table: str) -> int:
        if table not in {"signals", "risk_decisions", "orders", "fills", "trades", "portfolio_snapshots"}:
            raise ValueError("Unsupported table")
        return self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def close(self) -> None:
        self.connection.close()
