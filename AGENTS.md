# StockSwitch project rules

- The only project root is `D:\stockswitch`. Keep source, tests, logs, build output, data, documentation and Git work here. Never access or modify `D:\Galtai`.
- Phase 1 is paper trading only. Never connect to a real brokerage account, read account assets or credentials, or transmit real orders.
- Keep strategy, risk, brokerage, portfolio, market access and UI independent. Every simulated order must pass the RiskManager.
- Treat missing, stale, invalid or regressing market data as a trading stop. Show the data source, timestamp and approximate/delayed status.
- Tests use the deterministic FakeMarketDataProvider and do not need public network access.
- Never commit user configuration, databases, logs, caches, secrets or credentials. The only permitted GitHub remote is `https://github.com/zhiruolin974-a11y/stockswitch.git`; never force push.
- Phase 2 adds historical research and backtesting only. Keep live paper trading behavior intact; use only market data and virtual funds. Never start Phase 3 without instruction.
- Before claiming a phase complete, run compileall, all unit tests, GUI smoke, functional smoke, `git diff --check`, sensitive-data review, commit and push. Report failures honestly.
