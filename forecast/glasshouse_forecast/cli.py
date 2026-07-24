"""CLI for running seasonal-baseline forecasts by hand.

Examples (run from inside forecast/, after ingestion has populated
../ingestion/glasshouse.db with a few weeks of history):

    glasshouse-forecast system-prices --date 2026-08-05
    glasshouse-forecast fuel-generation --fuel-type WIND --date 2026-08-05
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime

from glasshouse_forecast.models import ForecastPoint
from glasshouse_forecast.seasonal_baseline import InsufficientHistoryError, SeasonalBaselineForecaster


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _print_points(points: list[ForecastPoint]) -> None:
    print(f"{'period':>6}  {'forecast':>10}  {'±stdev':>8}  {'n':>4}  fallback?")
    for p in points:
        flag = "yes" if p.fallback_used else ""
        print(f"{p.settlement_period:>6}  {p.forecast_value:>10.2f}  {p.std_dev:>8.2f}  {p.sample_size:>4}  {flag}")

    fallback_count = sum(1 for p in points if p.fallback_used)
    if fallback_count:
        print(
            f"\n{fallback_count}/{len(points)} periods fell back to an all-weekday average "
            f"(fewer than {3} same-weekday historical samples). More history will sharpen these."
        )


def cmd_system_prices(args: argparse.Namespace) -> int:
    try:
        with SeasonalBaselineForecaster(args.db) as forecaster:
            points = forecaster.forecast_system_prices(args.date)
    except (InsufficientHistoryError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Seasonal baseline forecast -- system sell price (GBP/MWh) -- {args.date} ({args.date:%A})\n")
    _print_points(points)
    return 0


def cmd_fuel_generation(args: argparse.Namespace) -> int:
    try:
        with SeasonalBaselineForecaster(args.db) as forecaster:
            points = forecaster.forecast_fuel_generation(args.date, args.fuel_type)
    except (InsufficientHistoryError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Seasonal baseline forecast -- {args.fuel_type} generation (MW) -- {args.date} ({args.date:%A})\n")
    _print_points(points)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="glasshouse-forecast")
    parser.add_argument(
        "--db",
        default="../ingestion/glasshouse.db",
        help="path to ingestion's SQLite store (default: assumes you're running from forecast/)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_prices = sub.add_parser("system-prices", help="forecast GB system sell price")
    p_prices.add_argument("--date", type=_parse_date, required=True)
    p_prices.set_defaults(func=cmd_system_prices)

    p_gen = sub.add_parser("fuel-generation", help="forecast generation for one fuel type")
    p_gen.add_argument("--fuel-type", required=True, help="e.g. WIND, CCGT, NUCLEAR, SOLAR")
    p_gen.add_argument("--date", type=_parse_date, required=True)
    p_gen.set_defaults(func=cmd_fuel_generation)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
