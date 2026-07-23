# ADR 0001: where the Python/Rust boundary sits

## Status
Accepted

## Context
Glasshouse has two kinds of work: orchestration (pull data from Elexon
and Octopus, forecast tomorrow's demand and generation, serve an API,
schedule jobs) and one narrow, numerically hot, correctness-critical
calculation (turning a generator portfolio and a consumer portfolio
into a fair, transparent, penny-accurate bill for a settlement period).
Real deployments run this calculation across many consumers x many
generators x 17,520 half-hour periods a year -- and it has to be exact,
because it's money.

## Decision
Everything except the settlement calculation itself is Python:
ingestion, forecasting, the API layer, scheduling. The settlement/
allocation math lives in a small Rust crate (`settlement-engine/`) and
is called directly from Python via a PyO3-compiled extension module --
not over HTTP, not as a separate service.

## Why not pure Python for everything
It would be simpler, and for the MVP's data volumes, fast enough. The
reasons to do it in Rust anyway:
- **Correctness under load is different from correctness in a demo.**
  A merit-order allocation over thousands of meters is an easy place
  for Python's dynamic typing to hide a silent unit mix-up (MWh vs kWh,
  a rounding step applied twice) that only shows up at scale. Rust's
  type system and the ability to write exhaustive, fast unit tests
  (`cargo test` runs the full suite in under a second) make that class
  of bug much harder to ship.
- **The rounding rule has to be enforced everywhere, not just remembered.**
  Bill lines round individually and a bill's total is the sum of its
  rounded lines -- never a separately-rounded subtotal. Encoding that as
  the *only* code path to a `ConsumerBill` (rather than a convention
  Python call sites have to remember) removes an entire category of
  penny-drift bugs.
- **It's the one place raw throughput plausibly matters** at MHHS-era
  data volumes (Elexon expects ~500bn meter reads/year once Market-wide
  Half-Hourly Settlement is fully live), even though the MVP's synthetic
  portfolios are nowhere near that scale yet.

## Why not Rust for everything
Ingestion, forecasting, and the API layer benefit far more from Python's
ecosystem (`httpx`, `pydantic`, the ML/forecasting stack, FastAPI) than
they would from Rust's performance -- none of that code is on a hot
path, and rewriting it in Rust would trade iteration speed for no real
benefit.

## Consequences
- Two build systems (`pip`/`hatchling` for ingestion, `cargo`/`maturin`
  for the engine) instead of one. Documented in each folder's README.
- The Rust crate's tests run without Python at all (`cargo test`), and
  the PyO3 bridge has its own, separate integration tests
  (`settlement-engine/python/test_bridge.py`) that only run once the
  extension is built -- so a contributor who never touches the Python
  bridge still gets fast, dependency-free feedback on the core logic.
- If a second consumer of the settlement engine ever needs it over the
  network rather than in-process (e.g. a non-Python service), the
  natural next step is wrapping the same Rust crate in a small Axum
  HTTP server rather than duplicating the logic -- the domain logic in
  `lib.rs` doesn't know or care how it's called.
