"""CLI for running Glasshouse ingestion jobs by hand or from a scheduler.

Examples:
    glasshouse-ingest elexon-prices --date 2026-07-22
    glasshouse-ingest elexon-generation --date 2026-07-22
    glasshouse-ingest elexon-backfill --start 2026-06-01 --end 2026-07-26
    glasshouse-ingest octopus-rates --product AGILE-24-10-01 \\
        --tariff E-1R-AGILE-24-10-01-C --date 2026-07-22
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime, timedelta

from glasshouse_ingestion.backfill import run_backfill
from glasshouse_ingestion.elexon_client import ElexonApiError, ElexonClient
from glasshouse_ingestion.octopus_client import OctopusApiError, OctopusClient
from glasshouse_ingestion.storage import Storage


def _parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def cmd_elexon_prices(args: argparse.Namespace) -> int:
    with ElexonClient() as client, Storage(args.db) as store:
        try:
            prices = client.get_system_prices(args.date)
        except ElexonApiError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        written = store.save_system_prices(prices)
        print(f"wrote {written} system-price rows for {args.date}")
    return 0


def cmd_elexon_generation(args: argparse.Namespace) -> int:
    with ElexonClient() as client, Storage(args.db) as store:
        try:
            records = client.get_fuel_type_generation(args.date)
        except ElexonApiError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        written = store.save_fuel_generation(records)
        print(f"wrote {written} fuel-generation rows for {args.date}")
    return 0


def cmd_elexon_backfill(args: argparse.Namespace) -> int:
    def print_progress(i: int, num_days: int, target_date: date, outcomes: list[str]) -> None:
        print(f"[{i + 1}/{num_days}] {target_date}: {', '.join(outcomes)}")

    try:
        result = run_backfill(
            args.db,
            args.start,
            args.end,
            dataset=args.dataset,
            delay_seconds=args.delay_seconds,
            on_progress=print_progress,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"\nDone: {result.total_rows} rows written across {result.total_dates} dates "
        f"({result.prices_rows} price rows, {result.generation_rows} generation rows)."
    )

    if result.failures:
        print(f"\n{len(result.failures)} date/dataset combination(s) failed:", file=sys.stderr)
        for failed_date, dataset, message in result.failures:
            print(f"  {failed_date} {dataset}: {message}", file=sys.stderr)
        return 1
    return 0


def cmd_octopus_rates(args: argparse.Namespace) -> int:
    period_from = datetime.combine(args.date, datetime.min.time())
    period_to = period_from + timedelta(days=1)
    with OctopusClient() as client, Storage(args.db) as store:
        try:
            rates = client.get_standard_unit_rates(
                args.product, args.tariff, period_from, period_to
            )
        except OctopusApiError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        written = store.save_agile_rates(rates, args.product, args.tariff)
        print(f"wrote {written} Octopus unit-rate rows for {args.date}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="glasshouse-ingest")
    parser.add_argument("--db", default="glasshouse.db", help="path to the SQLite store")
    sub = parser.add_subparsers(dest="command", required=True)

    p_prices = sub.add_parser("elexon-prices", help="fetch GB system sell/buy prices")
    p_prices.add_argument("--date", type=_parse_date, required=True)
    p_prices.set_defaults(func=cmd_elexon_prices)

    p_gen = sub.add_parser("elexon-generation", help="fetch generation by fuel type")
    p_gen.add_argument("--date", type=_parse_date, required=True)
    p_gen.set_defaults(func=cmd_elexon_generation)

    p_backfill = sub.add_parser(
        "elexon-backfill",
        help="ingest a whole date range in one command (loops elexon-prices/-generation per day)",
    )
    p_backfill.add_argument("--start", type=_parse_date, required=True)
    p_backfill.add_argument("--end", type=_parse_date, required=True)
    p_backfill.add_argument(
        "--dataset", choices=["prices", "generation", "both"], default="both",
        help="which dataset(s) to backfill (default: both)",
    )
    p_backfill.add_argument(
        "--delay-seconds", type=float, default=0.25,
        help="pause between API calls -- be polite to a free public API (default: 0.25)",
    )
    p_backfill.set_defaults(func=cmd_elexon_backfill)

    p_octopus = sub.add_parser("octopus-rates", help="fetch a published half-hourly tariff, as a benchmark")
    p_octopus.add_argument("--product", required=True, help="e.g. AGILE-24-10-01")
    p_octopus.add_argument("--tariff", required=True, help="e.g. E-1R-AGILE-24-10-01-C")
    p_octopus.add_argument("--date", type=_parse_date, required=True)
    p_octopus.set_defaults(func=cmd_octopus_rates)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
