# StockSwitch — Phase 2.5 Windows desktop packaging

StockSwitch is a personal research and learning desktop application for **live-data paper trading and historical backtesting only**. It uses virtual cash and simulated fills. It never connects to a real securities account or sends a real order. **Backtest performance is not future performance.** No investment return is promised.

## Windows installation and running

Three options are supported: an Inno Setup installer when available, the
`release/StockSwitch-0.2.0-Windows-x64.zip` portable archive, or Python source.
For the portable archive, extract the complete `StockSwitch/` directory and
double-click `StockSwitch.exe`; keep `_internal/` beside it. No console or
separate Python installation is needed. The installer adds a Start Menu entry
and an optional desktop shortcut. Uninstalling does not remove user data.

The packaged program stores configuration, the paper journal, historical cache,
logs and exports under `%LOCALAPPDATA%\StockSwitch` (`config/config.toml`,
`data/stockswitch.db`, `data/history/daily.sqlite`, `logs/stockswitch.log`,
`exports/`). The first launch creates missing directories and a credential-free
config template without replacing existing files. To diagnose startup errors,
inspect `logs/stockswitch.log`. In source mode, the existing ignored project-root
locations are preserved; `STOCKSWITCH_DATA_HOME` can override the data root for
isolated tests. Neither EXE nor installer stores runtime data in its program
directory. Packaging does not add any real brokerage connection, real account
access or real orders.

Build on Windows with Python 3.12+, the project venv and PyInstaller:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[windows-build]"
powershell -ExecutionPolicy Bypass -File scripts/build_windows.ps1
```

The script builds an onedir, windowed EXE, generates a portable ZIP and, if
`ISCC.exe` is installed, compiles `installer/StockSwitch.iss`. Build products
under `build/`, `dist/` and `release/` are ignored by Git. The program icon is
an original generated project asset. See `THIRD_PARTY_NOTICES.md` for the
third-party release review still required before public distribution.

For isolated frozen-package checks, set an absolute `STOCKSWITCH_DATA_HOME`
outside your production LocalAppData and run `StockSwitch.exe --self-test` for
GUI/Fake Paper/Backtest/export, or `StockSwitch.exe --network-smoke` for public
read-only quote and historical-download checks. These smoke flags refuse to
write into the normal user data directory.

## Start from source

Use Python 3.12 or newer on Windows:

```powershell
cd D:\stockswitch
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe main.py
```

Edit ignored `config.toml` to change the virtual cash, watchlist, refresh intervals, paper fees, risk limits, strategy parameters or backtest defaults. If it does not exist, the first launch copies the example settings. Live paper account state is stored in ignored `data/stockswitch.db`; logs are in ignored `logs/`.

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
.\.venv\Scripts\python.exe -m unittest tests.test_backtest_gui -v
.\.venv\Scripts\python.exe -m scripts.smoke_real_market
.\.venv\Scripts\python.exe -m scripts.smoke_historical
```

All automated tests use deterministic fake data and require no public network. The last two commands are separate read-only public market checks and may fail if a feed or network is unavailable. A live check after 15:00 China time verifies the last published data and prints **Market Closed**; it cannot establish intraday freshness.

## Historical backtesting

The Backtest tab accepts one or more Shanghai/Shenzhen A-share symbols, a date range, initial virtual cash, the daily frequency, the `TrendBreakoutStrategy`, a benchmark (default CSI 300, `sh000300`), an explicit security profile, and either cached Tencent history or deterministic fake data. Download and calculation run in a worker thread; Cancel stops without saving an incomplete official result. Progress, summary metrics, equity/benchmark curves, drawdown, simulated execution history and export are shown in the tab.

The historical provider requests Tencent Finance daily OHLCV using the [current AKShare `stock_zh_a_hist_tx` integration](https://github.com/akfamily/akshare/blob/main/akshare/stock_feature/stock_hist_tx.py). This is a public read-only website feed, with no guaranteed service contract or completeness. It was verified in September 2026 for two A-share stocks and CSI 300. Network access is needed for uncovered ranges; previously downloaded ranges work offline. Only **daily** bars are supported. The provider and `data/history/daily.sqlite` cache (under the source root or packaged AppData root) distinguish `none`, `qfq` and `hfq` adjustment; backtests default to **none** and use one adjustment consistently for both indicators and fills. Adjusted bars do not model cash dividends or other corporate actions separately. Minute bars are not included.

The cache stores bars plus coverage metadata (symbol, daily frequency, adjustment, start/end, provider, updated time). Only uncovered date intervals are downloaded. Missing a bar on an observed CSI 300 trading day prevents a fill for that stock. The benchmark's observed sessions form the backtest trading calendar, including weekends and past exchange holidays. It supports previous/next trading day queries. Dates outside observed coverage are unknown, rather than guessed. A benchmark feed omission could still be mistaken for a market closure; compare important runs with an official exchange calendar before relying on them.

The strategy reuses the Phase 1 implementation. It consumes completed daily bars chronologically, warming up before the requested start without booking warmup returns. At **T day 15:00**, it may generate a signal using data through T and prior-window values through T−1. That signal can only become an order and simulated fill at **the next observed trading day's 09:30 open**. Risk checks run at that open. All symbols share a single chronological portfolio, cash balance, T+1 availability and daily loss limit. No future bar close, high or low sets the execution price. A dedicated test mutates future bars and verifies earlier signals remain unchanged.

`BacktestBroker` reuses `PaperBroker`'s virtual account and `TradingCostModel`: next bar open plus directional slippage, commission with minimum, and sell-side stamp tax. The example `config.example.toml` uses 5 basis points slippage, 0.03% commission with ¥5 minimum, and 0.05% sell stamp tax. These are **simulation parameters**, not a quote for any user's broker. [Shanghai Stock Exchange trading guidance](https://one.sse.com.cn/onething/gptz/) describes the exchange stamp tax; broker commission and other costs vary. The program does not model order-book liquidity, partial fills or auction price formation.

Buying uses 100-share lots. A full residual position containing an odd lot may be sold in one order, consistent with [Shenzhen Stock Exchange investor guidance](https://investor.szse.cn/institute/bookshelf/manualseriesbook/P020230403389861343977.pdf). Price limits use an **explicit, date-valid security profile**: regular main board 10%, ST main board 5%, ChiNext/STAR 20%, with a conservative no-fill assumption at a buy upper limit or sell lower limit. The [SZSE main-board guide](https://investor.szse.cn/institute/bookshelf/manualseriesbook/P020230403389861343977.pdf) and [SSE trading rules](https://www.sse.com.cn/lawandrules/sselawsrules2025/stocks/exchange/c/c_20260424_10816482.shtml) describe these different regimes and exceptions. Default `unknown` blocks fills; select a profile only after verifying it applies for the **entire chosen period**. IPO no-limit days, changing ST status, exceptional exchange rules, ex-right reference prices and exchange rounding are not automatically identified. Zero-volume bars and dates missing a stock bar are conservatively unfillable; the source does not prove the precise suspension reason.

The result records source, data range/hash, adjustment, strategy and cost parameters, benchmark, executions and completed round trips. Metrics include total and annualized return, equity-based maximum drawdown with peak/trough dates, daily volatility, Sharpe, win/loss rate, profit factor and holding period. Sharpe uses daily returns, a configurable annual risk-free rate (default 2%) and configurable **252** trading-day annualization. Insufficient data yields `N/A`, not an invented value. Benchmark return normalizes its first in-range close to initial virtual capital. The separately stored completed-run index is `data/backtests.db`; `summary.json`, `trades.csv` and `equity_curve.csv` export to ignored `exports/backtests/<run_id>/` or another selected folder inside the active application data root.

## Safety and limits

No real broker adapter, login, token, password, real account access, real order submission or AI trade execution exists. The live Paper tab retains Phase 1's weekday-only calendar and sampled-quote warmup; the historical Backtest tab uses observed benchmark sessions and downloaded warmup bars. Public feeds, simplified fills, explicit security-profile assumptions and missing corporate-action cash flows make this a research prototype, not a production trading system.
