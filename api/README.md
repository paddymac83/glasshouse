# api/ (not yet built)

FastAPI service that ties `ingestion`, `forecast`, and `settlement-engine`
together and serves the dashboard. Planned surface:

- `GET /prices/latest` -- most recent Elexon system prices from the store
- `POST /settle` -- build a portfolio (generators + consumers), call
  `glasshouse_settlement.settle_period_py` directly (no HTTP hop --
  see `docs/adr/0001-python-rust-boundary.md`), return the itemised bill
- `GET /benchmark` -- compare the computed price against the live
  Octopus Agile rate for the same settlement period
- `WS /live` -- push a refreshed price/bill every ~30 minutes, matching
  the cadence real half-hourly settlement runs on

Depends on `ingestion` (for stored market data) and `settlement-engine`
(for the pricing math) as local packages.
