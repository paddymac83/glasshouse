# frontend/

A Django + Django REST Framework (DRF) service: both the actual
dashboard (server-rendered HTML, no JS framework) and its own REST API
-- a second, independent implementation of the same pricing surface
`api/` (FastAPI) provides.

## Why two implementations of the same thing

This started as "build the frontend," with the original plan being a
separate React app calling `api/`'s FastAPI service. Partway through,
the goal shifted to specifically learning Django with a REST interface
-- so rather than Django becoming a thin client of the existing FastAPI
service, it's a **parallel** implementation: it imports
`glasshouse-ingestion`, `glasshouse-forecast`, and
`glasshouse-settlement` directly, the same way `api/` does, rather than
calling `api/` over HTTP.

`api/` was not retired. It's real, tested, working code, and deleting
it would have thrown away genuine value for no benefit -- and having
both around is a legitimate feature for a portfolio project: the same
pricing logic, wired up two different ways, is a natural thing to
compare and talk through in an interview.

## What's actually different from `api/`

The pricing logic itself (`pricing/services.py`) is a deliberate,
line-by-line port of `api/glasshouse_api/quote.py` + `main.py`'s
helper functions -- same business rules, same illustrative demand
figures, kept in sync by hand (see `services.py`'s module docstring).
What differs is entirely the framework layer:

| | `api/` | `frontend/` |
|---|---|---|
| Framework | FastAPI | Django + DRF |
| Validation | pydantic models | DRF serializers |
| Docs | auto-generated at `/docs` | DRF's browsable API at `/api/...` |
| UI | none (API-only) | server-rendered dashboard at `/` |
| Routing | function decorators | `urls.py` + class-based views |

## Routes

| Route | What it does |
|---|---|
| `GET /` | **the dashboard** -- a form (business type, renewable share, date, optional settlement period), rendered server-side |
| `GET /api/health/` | liveness check |
| `GET /api/prices/latest/` | most recent stored system prices |
| `GET /api/forecast/system-prices/?date=` | seasonal-baseline price forecast |
| `GET /api/forecast/fuel-generation/?date=&fuel_type=` | same, for one fuel type |
| `POST /api/settle/` | raw settlement engine passthrough |
| `GET /api/quote/?date=&business_type=&renewable_share=` | the one-click quote (same shape as `api/`'s `/quote`) |

## Usage

```bash
cd frontend
uv venv && uv pip install -e ".[dev]"   # resolves ingestion, forecast, and
                                         # settlement-engine as local path
                                         # deps and compiles the Rust
                                         # extension, same as api/ does
uv run python manage.py migrate         # sets up Django's own internal
                                         # tables (admin/auth/sessions) --
                                         # unrelated to glasshouse.db
uv run pytest -v                        # 30 tests

uv run python manage.py runserver
# -> http://127.0.0.1:8000/           the dashboard
# -> http://127.0.0.1:8000/api/quote/?date=2026-08-05&business_type=factory&renewable_share=0.6
```

By default it looks for `../ingestion/glasshouse.db`. Override with
`GLASSHOUSE_INGESTION_DB`, same environment variable `api/` uses:

```bash
GLASSHOUSE_INGESTION_DB=/path/to/glasshouse.db uv run python manage.py runserver
```

## Notes for anyone (including future-you) learning Django from this

- **Django's own `db.sqlite3`** (created by `migrate`, in this folder)
  has nothing to do with `ingestion/glasshouse.db`. It's Django's
  internal bookkeeping for the admin site, auth, and sessions -- none
  of which this project actually uses yet. It's a separate, unrelated
  database that just happens to also be SQLite.
- **The dashboard form submits as `GET`, not `POST`.** Deliberately --
  it doesn't change any state, so there's no CSRF token to wire up, and
  a GET means the resulting URL (with `?date=...&business_type=...`) is
  shareable and bookmarkable. A form that actually created or modified
  something (not the case here) should be a POST with
  `{% csrf_token %}`.
- **`pricing/services.py` has no Django imports at all.** It's plain
  Python, testable and usable outside a request entirely (see
  `pricing/tests/test_services.py`, which never touches a test client).
  Django-specific code (`views.py`, `urls.py`, the template) is a thin
  layer on top of it. This is the same pure-logic-vs-framework-glue
  split as `settlement-engine`'s `settle_period` and `forecast`'s
  `seasonal_average` -- same idea, third framework it shows up in.
- **DRF serializers vs. pydantic**: `serializer.is_valid(raise_exception=True)`
  is doing the same job pydantic does automatically on model
  construction in `api/` -- DRF just wants that check spelled out as
  an explicit method call rather than happening implicitly.

## The `/quote` portfolio is illustrative, not measured

Same caveat as `api/README.md`: there's no real per-business
consumption data feeding this project. The demand and generator-cost
figures in `pricing/services.py` are stylised, plausible numbers for a
single settlement period -- useful for demonstrating the pricing
mechanism, not a real quote for a real business.
