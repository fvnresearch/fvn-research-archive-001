from __future__ import annotations

import argparse

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import (
    FSDSIngestionConfig,
    build_fsds_source_tables,
    parse_quarters,
    parse_years,
)
from fvn_dfm.utils.paths import root
from fvn_dfm.xbrl.fact_selector import AccountingFactSelectorConfig, build_accounting_fact_selected


def main() -> None:
    parser = argparse.ArgumentParser(description="XBRL / SEC Financial Statement Data Sets entrypoint.")
    parser.add_argument(
        "--source",
        choices=["sec-fsds", "accounting-fact-selected"],
        required=True,
        help="XBRL source/layer to ingest or build.",
    )

    # FSDS ingestion args
    parser.add_argument("--raw-fsds-dir", default="data/raw/sec/financial_statement_data_sets")
    parser.add_argument("--output-dir", default="data/processed/source_tables")
    parser.add_argument("--diagnostics-dir", default="outputs/diagnostics")
    parser.add_argument("--years")
    parser.add_argument("--quarters")
    parser.add_argument("--forms", default="10-K,10-Q")
    parser.add_argument("--chunksize", type=int, default=250000)

    # Accounting selector args
    parser.add_argument("--xbrl-fact-path", default="data/processed/source_tables/xbrl_fact_accession_raw.csv")
    parser.add_argument("--xbrl-submission-path", default="data/processed/source_tables/xbrl_submission_metadata.csv")
    parser.add_argument("--output-table")
    parser.add_argument("--output-csv")
    parser.add_argument("--diagnostics-path")

    args = parser.parse_args()

    if args.source == "sec-fsds":
        config = FSDSIngestionConfig(
            raw_fsds_dir=root() / args.raw_fsds_dir,
            output_dir=root() / args.output_dir,
            diagnostics_dir=root() / args.diagnostics_dir,
            years=parse_years(args.years),
            quarters=parse_quarters(args.quarters),
            forms_filter=tuple(f.strip().upper() for f in args.forms.split(",") if f.strip()),
            chunksize=args.chunksize,
        )
        build_fsds_source_tables(config)
        return

    if args.source == "accounting-fact-selected":
        config = AccountingFactSelectorConfig(
            xbrl_fact_accession_raw_path=root() / args.xbrl_fact_path,
            xbrl_submission_metadata_path=root() / args.xbrl_submission_path,
            output_table_path=root() / (args.output_table or "data/processed/source_tables/accounting_fact_selected.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/source_tables/accounting_fact_selected.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/accounting_fact_selected_diagnostics.csv"),
        )
        build_accounting_fact_selected(config)
        return


if __name__ == "__main__":
    main()
