# StockSwitch — Phase 1

StockSwitch is a personal research and learning desktop application for **paper trading only**. It reads public A-share market quotes, uses virtual cash and simulated fills, and never connects to a real securities account or sends a real order. It does not promise investment returns.

## Start

Use Python 3.12 or newer on Windows:

```powershell
cd D:\stockswitch
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe main.py
```

Copy `config.example.toml` to ignored `config.toml` to change the virtual cash, watchlist, refresh intervals, paper fees, risk limits or strategy parameters. If `config.toml` does not exist, the example settings are used. SQLite data is stored in ignored `data/stockswitch.db`; logs are stored in ignored `logs/`.

## Market data and timeliness

The live provider performs one public, unauthenticated, read-only batch request to Tencent Finance (`https://qt.gtimg.cn/q=...`) for four indices and at most eight watchlist stocks. It stores each quote's remote timestamp and local receipt time. The UI labels the source **Approximate Real-Time / Delayed**, shows the market state, and marks old holdings prices **STALE**. This is a public website feed without an exchange-grade latency guarantee or a supported API service contract. Source fields or access may change. The project does not bypass authentication or access limits.

The [AKShare project documentation](https://github.com/akfamily/akshare/blob/main/docs/tutorial.md) identifies Tencent A-share spot data as a current source; [AKShare stock documentation](https://github.com/akfamily/akshare/blob/main/docs/data/stock/stock.md) also documents its Tencent data integration. The direct batch endpoint was verified read-only during Phase 1 development. Remote timestamps are not network latency measurements. A closed market may show the latest published quote, with **Market Closed** and stale indicators.

At market open, the default request interval is five seconds; outside trading hours it is 120 seconds. The source is polled only for the small configured watchlist, never the full exchange. A request failure, missing or invalid quote, timestamp regression, or stock quote older than `max_quote_age_seconds` blocks all new simulated orders. The last displayed position price remains visible as stale. Quote timestamps must be timezone-aware.

## Simulated trading

The account starts with configurable ¥100,000 virtual cash. The `TrendBreakoutStrategy` is a transparent demonstration: after at least 61 distinct sampled quotes per stock, it compares short and long moving averages, a prior-high breakout and sampled volume increase. It can then issue BUY or an exit SELL signal. It has no profitability claim. It does not request historical bars, and therefore must warm up after each application start. Sampled snapshots are not exchange ticks or conventional candles.

Watchlist symbols can be added or removed in the GUI for the current run. A stock with an open paper position cannot be removed, so its mark price continues to update. To make watchlist changes permanent, edit ignored `config.toml`.

Every automatic signal and every manual **SIMULATED / PAPER Buy/Sell** action passes the same independent `RiskManager`. Defaults limit one position to 10% of equity, total positions to 60%, one order to 10%, and daily virtual loss to 2%. The engine checks market hours, quote freshness, available cash and T+1 available holdings. The first market calendar covers ordinary weekdays and morning/afternoon sessions; an injectable holiday calendar interface is reserved, but no verified holiday feed is included. On an exchange holiday that falls on a weekday, users must leave monitoring stopped or disable trading until a holiday calendar is configured.

`PaperBroker` uses quote price plus configurable slippage, commission (with a minimum), and sell-side stamp tax to simulate an immediate market fill. It does not model order book depth, partial fills, queue priority, price limits or suspension state. These and exchange holiday handling are limitations of Phase 1. BUY shares become sellable only on a later trading date. Simulated orders, fills, trades, signals, risk decisions and portfolio snapshots are persisted in SQLite. The latest account snapshot restores virtual cash and holdings on restart; in-memory strategy samples are intentionally not restored. Portfolio figures are mark-to-market estimates and may use the last stale price, visibly labeled in the interface.

## Tests and smoke checks

```powershell
.\.venv\Scripts\python.exe -m compileall -q src tests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest tests.test_engine_journal_gui.EngineJournalTests.test_gui_smoke_with_fake_provider -v
.\.venv\Scripts\python.exe -m unittest tests.test_engine_journal_gui.EngineJournalTests.test_full_buy_mark_sell_pnl -v
.\.venv\Scripts\python.exe -m scripts.smoke_real_market
```

All automated tests use deterministic fake data and require no public network. The final command is a separate read-only live market check and may fail if the public feed or network is unavailable. A run after 15:00 China time verifies the last published data and prints **Market Closed**; it cannot establish intraday freshness.

## Safety and limits

No real broker adapter, login, token, password, real account access, real order submission or AI trade execution exists in Phase 1. The public quote source offers no completeness or timeliness guarantee. The weekday-only calendar, no historical warm start, no suspension/limit-up/limit-down checks, simplified immediate fills and one-process SQLite writer mean the application is a research prototype, not a production trading system.
