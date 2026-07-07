from __future__ import annotations

import argparse

from fvn_dfm.normalization.filing_availability import (
    FilingAvailabilityConfig,
    build_filing_availability,
)
from fvn_dfm.utils.paths import root
from fvn_dfm.utils.trading_calendar import DEFAULT_MARKET_TIMEZONE


def main() -> None:
    parser = argparse.ArgumentParser(description="Build point-in-time tables.")
    parser.add_argument(
        "--table",
        choices=["filing-availability"],
        required=True,
        help="Point-in-time table to build.",
    )
    parser.add_argument("--complete-submissions-dir", default="data/raw/sec/complete_submissions")
    parser.add_argument("--filing-event-path", default="data/processed/source_tables/sec_filing_event.csv")
    parser.add_argument("--output-table", default="data/processed/point_in_time/filing_availability.parquet")
    parser.add_argument("--output-csv", default="data/processed/point_in_time/filing_availability.csv")
    parser.add_argument("--holidays-path", default="data/raw/calendars/us_market_holidays.csv")
    parser.add_argument("--timezone-name", default=DEFAULT_MARKET_TIMEZONE)
    args = parser.parse_args()

    if args.table == "filing-availability":
        config = FilingAvailabilityConfig(
            complete_submissions_dir=root() / args.complete_submissions_dir,
            filing_event_path=root() / args.filing_event_path if args.filing_event_path else None,
            output_table_path=root() / args.output_table,
            output_csv_path=root() / args.output_csv,
            holidays_path=root() / args.holidays_path if args.holidays_path else None,
            timezone_name=args.timezone_name,
        )
        build_filing_availability(config)


if __name__ == "__main__":
    main()
