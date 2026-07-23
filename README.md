# Glasshouse

A transparent, half-hourly electricity settlement simulator for the
GB market -- built to demonstrate pricing-engine, systems, and DevOps
skills, not as a commercial product. **This is a simulation using
public reference data. It is not a licensed energy supplier and does
not offer real tariffs.**

## Why this exists

Octopus Agile already shows the public tomorrow's wholesale-linked
price. What nobody shows is *why* a bill is what it is: how much is
generation cost, how much is network charges, how much is policy cost,
how much is margin -- and what a "direct generator-to-business
matching" model (the pitch behind Tem's RED and, differently, Fuse's
real-time trading) would actually change about that breakdown.

Glasshouse pulls real GB settlement-period prices and generation data,
lets you build a synthetic generator + consumer portfolio, runs a
merit-order allocation to compute a "should-cost" price for each
half-hour period, and produces a fully itemised, penny-accurate bill --
benchmarked against the real, published Octopus Agile rate for the
same period.

It's also deliberately timed: Britain's Market-wide Half-Hourly
Settlement programme goes live in December 2026, at which point every
customer's consumption -- not just large or smart-metered ones -- gets
settled the way this project already assumes.

## Repo layout

| Folder | Status | What it is |
|---|---|---|
| `ingestion/` | **built** | Python: pulls GB system prices and generation-by-fuel-type from Elexon's public API, and Octopus's public Agile tariff rates as a benchmark. SQLite storage. |
| `settlement-engine/` | **built** | Rust: the merit-order allocation and bill-decomposition engine, exposed to Python via PyO3. Pure-Rust tests (`cargo test`) plus a Python bridge test. |
| `forecast/` | planned | Day-ahead demand/generation forecasting. |
| `api/` | planned | FastAPI service wiring ingestion + forecast + settlement-engine together. |
| `frontend/` | planned | React dashboard. |
| `infra/` | planned | AWS CDK (Python), CI/CD, observability. |
| `docs/adr/` | ongoing | Architecture decision records. |

See each folder's `README.md` for details and, where relevant, what's
still to be built.

## Quickstart

Examples below use [`uv`](https://docs.astral.sh/uv/) — it resolves and
installs faster than pip, and for `settlement-engine` specifically it
removes a real papercut: it detects the `maturin` build backend in
`pyproject.toml` and compiles the Rust extension directly on
`uv pip install -e .`, with no separate `maturin develop` call and no
manually exporting `VIRTUAL_ENV`. Plain `pip` still works fine for
`ingestion` if you'd rather not add a new tool — see the fallback
commands below each section.

### Ingestion (Python)

```bash
cd ingestion
uv venv && uv pip install -e ".[dev]"
uv run pytest -v                # 10 tests, all against mocked HTTP -- no network needed

# pip equivalent:
#   python3 -m venv .venv && . .venv/bin/activate
#   pip install -e ".[dev]" && pytest -v

# Against the real, public, key-free Elexon API:
uv run glasshouse-ingest elexon-prices --date 2026-07-22
uv run glasshouse-ingest elexon-generation --date 2026-07-22
uv run glasshouse-ingest octopus-rates --product AGILE-24-10-01 \
    --tariff E-1R-AGILE-24-10-01-C --date 2026-07-22
```

### Settlement engine (Rust + Python)

```bash
cd settlement-engine
cargo test                      # 9 tests, pure Rust, no Python involved

# Build it as an importable Python module:
uv venv && uv pip install -e .          # compiles the Rust extension via maturin, automatically
uv pip install pytest
uv run pytest python/test_bridge.py -v  # 3 more tests, against the compiled extension

# pip equivalent (needs an explicit `maturin develop` step -- see
# settlement-engine/python/README.md for why):
#   python3 -m venv .venv && . .venv/bin/activate
#   pip install maturin pytest && maturin develop --release
#   pytest python/test_bridge.py -v
```

## A note on data accuracy

The Elexon client's field names (`settlementDate`, `systemSellPrice`,
`fuelType`, ...) come from Elexon's published API docs and the
community `elexonpy` client, not from a live call verified in this
environment. Before trusting it against production data, run it once
against the real API and diff the response against
`ingestion/tests/fixtures/elexon_system_prices.json` -- if a field name
has moved, `ElexonClient._parse_system_price` /
`_parse_fuel_generation` are the only two places that need to change.

## License

MIT. See `LICENSE`.
