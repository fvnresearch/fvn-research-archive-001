from __future__ import annotations

import argparse

from fvn_dfm.text.filing_text_raw import FilingTextRawConfig, build_filing_text_raw
from fvn_dfm.text.section_extractor import SectionExtractionConfig, build_filing_section_text
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(description="Text extraction entrypoint.")
    parser.add_argument(
        "--layer",
        choices=["filing-text-raw", "filing-section-text"],
        required=True,
        help="Text layer to extract.",
    )

    # filing_text_raw args
    parser.add_argument("--primary-documents-dir", default="data/raw/sec/primary_documents")
    parser.add_argument("--keep-tables", action="store_true")

    # filing_section_text args
    parser.add_argument("--filing-text-raw-path", default="data/processed/source_tables/filing_text_raw.csv")
    parser.add_argument("--min-mda-word-count", type=int, default=300)
    parser.add_argument("--min-risk-word-count", type=int, default=150)
    parser.add_argument("--min-liquidity-word-count", type=int, default=80)

    parser.add_argument("--output-table")
    parser.add_argument("--output-csv")
    parser.add_argument("--min-clean-word-count", type=int, default=1000)
    args = parser.parse_args()

    if args.layer == "filing-text-raw":
        config = FilingTextRawConfig(
            primary_documents_dir=root() / args.primary_documents_dir,
            output_table_path=root() / (args.output_table or "data/processed/source_tables/filing_text_raw.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/source_tables/filing_text_raw.csv"),
            remove_tables=not args.keep_tables,
            min_clean_word_count=args.min_clean_word_count,
        )
        build_filing_text_raw(config)
        return

    if args.layer == "filing-section-text":
        config = SectionExtractionConfig(
            filing_text_raw_path=root() / args.filing_text_raw_path,
            output_table_path=root() / (args.output_table or "data/processed/source_tables/filing_section_text.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/source_tables/filing_section_text.csv"),
            min_mda_word_count=args.min_mda_word_count,
            min_risk_word_count=args.min_risk_word_count,
            min_liquidity_word_count=args.min_liquidity_word_count,
        )
        build_filing_section_text(config)
        return


if __name__ == "__main__":
    main()
