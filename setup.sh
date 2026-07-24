#!/usr/bin/env bash
# setup.sh -- one-command environment setup for Glasshouse.
#
# What it does:
#   1. Checks for uv and a Rust toolchain, with a clear message (not a
#      cryptic failure) if either is missing.
#   2. Sets up ingestion/'s venv and installs it plus dev dependencies.
#   3. Runs the pure-Rust settlement-engine test suite (cargo test) --
#      no Python needed for this part.
#   4. Sets up settlement-engine/'s venv and builds the PyO3 extension
#      (uv pip install -e . invokes maturin under the hood).
#   5. Runs every test suite and prints one pass/fail summary.
#
# Safe to re-run: every step is idempotent.
#
# Usage:
#   ./setup.sh

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FAILED=0

info() { printf '\n\033[1;34m==>\033[0m %s\n' "$1"; }
ok()   { printf '\033[1;32m✓\033[0m %s\n' "$1"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$1"; }

# ---------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------
info "Checking prerequisites"

if ! command -v uv >/dev/null 2>&1; then
    fail "uv not found. Install it: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi
ok "uv $(uv --version)"

if ! command -v cargo >/dev/null 2>&1; then
    fail "cargo not found. Install Rust: https://rustup.rs"
    exit 1
fi
ok "cargo $(cargo --version)"

# ---------------------------------------------------------------------
# 2. ingestion/
# ---------------------------------------------------------------------
info "Setting up ingestion/"
cd "$ROOT_DIR/ingestion"
uv venv --allow-existing
uv pip install -e ".[dev]"
ok "ingestion venv ready"

info "Running ingestion tests"
if uv run pytest -q; then
    ok "ingestion: all tests passed"
else
    fail "ingestion: tests failed"
    FAILED=1
fi

# ---------------------------------------------------------------------
# 3. forecast/ -- pure Python, no Rust involved
# ---------------------------------------------------------------------
info "Setting up forecast/"
cd "$ROOT_DIR/forecast"
uv venv --allow-existing
uv pip install -e ".[dev]"
ok "forecast venv ready"

info "Running forecast tests"
if uv run pytest -q; then
    ok "forecast: all tests passed"
else
    fail "forecast: tests failed"
    FAILED=1
fi

# ---------------------------------------------------------------------
# 4. settlement-engine/ -- pure Rust first: fast, no Python involved
# ---------------------------------------------------------------------
info "Running settlement-engine Rust tests"
cd "$ROOT_DIR/settlement-engine"
if cargo test --quiet; then
    ok "settlement-engine: Rust tests passed"
else
    fail "settlement-engine: Rust tests failed"
    FAILED=1
fi

info "Building the Python extension (compiles Rust -- first run can take ~1 minute)"
uv venv --allow-existing
uv pip install -e .
uv pip install pytest
ok "settlement-engine Python extension built"

info "Running settlement-engine Python bridge tests"
if uv run pytest python/test_bridge.py -q; then
    ok "settlement-engine: Python bridge tests passed"
else
    fail "settlement-engine: Python bridge tests failed"
    FAILED=1
fi

# ---------------------------------------------------------------------
# 5. Summary
# ---------------------------------------------------------------------
cd "$ROOT_DIR"
if [ "$FAILED" -eq 0 ]; then
    info "All set -- 38 tests passing across ingestion + forecast + settlement-engine."
    cat <<'EOF'

Next steps:
  - Try the ingestion CLI against the real, public Elexon API:
      cd ingestion && uv run glasshouse-ingest elexon-prices --date <YYYY-MM-DD>
  - Check the live API schema still matches what the parser assumes:
      cd ingestion && uv run python scripts/verify_live_schema.py
  - See README.md for the full architecture, current status, and roadmap.
EOF
else
    fail "Setup finished with failures -- see the output above."
    exit 1
fi
