# Building the Python extension

The settlement engine is pure Rust at its core (`../src/lib.rs`), with a
thin PyO3 bridge in the same file. Three independent ways to exercise it:

## 1. Pure Rust (no Python involved)

```bash
cd settlement-engine
cargo test
```

This is the fast inner-loop -- no Python interpreter, no maturin, just
`cargo test` against the domain logic directly.

## 2. As an importable Python module, with uv (recommended)

```bash
cd settlement-engine
uv venv
uv pip install -e .
uv pip install pytest
uv run pytest python/test_bridge.py -v
```

`uv pip install -e .` reads `build-backend = "maturin"` from
`pyproject.toml` and invokes maturin itself -- no separate
`maturin develop` call, and critically, no manually exporting
`VIRTUAL_ENV` (which plain `maturin develop` needs if it can't
auto-detect an active environment; `uv venv` + `uv pip install` doesn't
have that problem because uv always makes its target environment
explicit to the tools it shells out to).

## 3. As an importable Python module, with plain pip/maturin

```bash
cd settlement-engine
python3 -m venv .venv
. .venv/bin/activate
pip install maturin pytest
maturin develop --release   # compiles the Rust crate, installs it into .venv
python -m pytest python/test_bridge.py -v
```

`maturin develop` reads the `[tool.maturin]` section of `pyproject.toml`,
which enables the `python-ext` Cargo feature (this is what switches
PyO3 from "link against libpython" mode, used by `cargo test`, into
"extension module loaded by the interpreter" mode, used by `import`).

## Using it from Python

However you built it, the result is the same importable module:

```python
import glasshouse_settlement

result = glasshouse_settlement.settle_period_py(
    generators=[("wind_farm_1", 5.0, 30.0), ("gas_peaker", 100.0, 80.0)],
    consumers=[("bakery", 2.0), ("brewery", 8.0)],
    network_charge_gbp_per_mwh=20.0,
    policy_cost_gbp_per_mwh=15.0,
    platform_margin_fraction=0.05,
)
```

This is exactly how the `api/` service (phase 3) will call it: FastAPI
handlers import `glasshouse_settlement` like any other Python module --
there's no HTTP hop between the API layer and the Rust engine.
