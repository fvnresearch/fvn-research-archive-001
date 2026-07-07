from __future__ import annotations

import argparse

from fvn_dfm.normalization.sec_filing_event import (
    FilingEventExtractionConfig,
    build_sec_filing_event_outputs,
    parse_forms,
)
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(description="Build normalized source tables.")
    parser.add_argument(
        "--table",
        choices=["sec-filing-event"],
        required=True,
        help="Source table to build.",
    )
    parser.add_argument("--submissions-dir", default="data/raw/sec/submissions")
    parser.add_argument("--output-table", default="data/processed/source_tables/sec_filing_event.parquet")
    parser.add_argument("--output-csv", default="data/processed/source_tables/sec_filing_event.csv")
    parser.add_argument("--filing-refs-csv", default="data/interim/sec/complete_submission_filing_refs.csv")
    parser.add_argument("--forms", default="10-K,10-Q")
    parser.add_argument("--min-filing-date")
    parser.add_argument("--max-filing-date")
    args = parser.parse_args()

    if args.table == "sec-filing-event":
        config = FilingEventExtractionConfig(
            submissions_dir=root() / args.submissions_dir,
            output_table_path=root() / args.output_table,
            output_csv_path=root() / args.output_csv,
            filing_refs_csv_path=root() / args.filing_refs_csv,
            included_forms=parse_forms(args.forms),
            min_filing_date=args.min_filing_date,
            max_filing_date=args.max_filing_date,
        )
        build_sec_filing_event_outputs(config)


if __name__ == "__main__":
    main()
