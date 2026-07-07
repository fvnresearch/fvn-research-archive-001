from __future__ import annotations

import argparse

from fvn_dfm.data_ingestion.sec_complete_submissions import (
    FilingRef,
    SecCompleteSubmissionDownloader,
    load_complete_submission_config,
    read_filing_refs_csv,
)
from fvn_dfm.data_ingestion.sec_financial_statement_datasets import (
    SECFinancialStatementDataSetsDownloader,
    load_fsds_download_config,
    parse_quarters,
    parse_years,
)
from fvn_dfm.data_ingestion.sec_primary_documents import (
    PrimaryDocumentDiscoveryConfig,
    SecPrimaryDocumentDownloader,
    discover_primary_document_candidates,
    load_primary_document_download_config,
    read_primary_document_candidates_csv,
    write_primary_document_candidates_csv,
)
from fvn_dfm.data_ingestion.sec_submissions import (
    SecSubmissionsDownloader,
    load_sec_download_config,
    read_cik_list,
)
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Sprint 02 raw data ingestion entrypoint."
    )
    parser.add_argument(
        "--source",
        choices=["sec-submissions", "sec-complete-submissions", "sec-primary-documents", "sec-fsds"],
        required=True,
        help="Raw data source to ingest.",
    )

    # SEC submissions args
    parser.add_argument("--cik", action="append", help="CIK to download. Can be used for either source.")
    parser.add_argument("--cik-file", help="Text/CSV file with CIKs for sec-submissions.")

    # Complete submission args
    parser.add_argument("--accession-number", action="append", help="Accession number for complete submission.")
    parser.add_argument("--form-type", default="")
    parser.add_argument("--filing-date", default="")
    parser.add_argument("--filing-refs-csv", help="CSV with cik,accession_number[,form_type,filing_date].")

    # Primary document args
    parser.add_argument("--filing-availability-path", default="data/processed/point_in_time/filing_availability.csv")
    parser.add_argument("--complete-submissions-dir", default="data/raw/sec/complete_submissions")
    parser.add_argument("--primary-document-candidates-csv", default="data/interim/sec/primary_document_candidates.csv")
    parser.add_argument("--allowed-forms", default="10-K,10-Q")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--download-only", action="store_true")

    # FSDS args
    parser.add_argument("--years", help="For sec-fsds. Example: 2009-2025 or 2024,2025")
    parser.add_argument("--quarters", default="1,2,3,4")

    parser.add_argument("--config", default="configs/01_data_sources.yaml")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--gzip-raw", action="store_true")
    args = parser.parse_args()

    if args.source == "sec-submissions":
        ciks: list[str] = []
        if args.cik:
            ciks.extend(args.cik)
        if args.cik_file:
            ciks.extend(read_cik_list(args.cik_file))
        if not ciks:
            raise SystemExit("SEC submissions ingestion requires --cik or --cik-file.")

        config = load_sec_download_config(root() / args.config)
        downloader = SecSubmissionsDownloader(config)
        downloader.download_many(ciks, force=args.force, gzip_raw=args.gzip_raw)
        return

    if args.source == "sec-complete-submissions":
        filings: list[FilingRef] = []

        if args.cik and args.accession_number:
            if len(args.cik) != len(args.accession_number):
                raise SystemExit(
                    "For repeated --cik/--accession-number usage, counts must match."
                )
            filings.extend(
                FilingRef(
                    cik=cik,
                    accession_number=accession,
                    form_type=args.form_type,
                    filing_date=args.filing_date,
                )
                for cik, accession in zip(args.cik, args.accession_number)
            )

        if args.filing_refs_csv:
            filings.extend(read_filing_refs_csv(args.filing_refs_csv))

        if not filings:
            raise SystemExit(
                "Complete submission ingestion requires --cik + --accession-number "
                "or --filing-refs-csv."
            )

        config = load_complete_submission_config(root() / args.config)
        downloader = SecCompleteSubmissionDownloader(config)
        downloader.download_many(filings, force=args.force, gzip_raw=args.gzip_raw)
        return

    if args.source == "sec-primary-documents":
        allowed_forms = tuple(f.strip().upper() for f in args.allowed_forms.split(",") if f.strip())

        if args.download_only:
            candidates = read_primary_document_candidates_csv(root() / args.primary_document_candidates_csv)
        else:
            discovery_config = PrimaryDocumentDiscoveryConfig(
                filing_availability_path=root() / args.filing_availability_path,
                complete_submissions_dir=root() / args.complete_submissions_dir,
                candidates_csv_path=root() / args.primary_document_candidates_csv,
                allowed_forms=allowed_forms,
            )
            candidates = discover_primary_document_candidates(discovery_config)
            write_primary_document_candidates_csv(candidates, discovery_config.candidates_csv_path)

        if args.discover_only:
            return

        config = load_primary_document_download_config(root() / args.config)
        downloader = SecPrimaryDocumentDownloader(config)
        downloader.download_many(candidates, force=args.force, gzip_raw=args.gzip_raw)
        return

    if args.source == "sec-fsds":
        if not args.years:
            raise SystemExit("sec-fsds download requires --years.")
        config = load_fsds_download_config(root() / args.config)
        downloader = SECFinancialStatementDataSetsDownloader(config)
        downloader.download_many(
            years=parse_years(args.years) or (),
            quarters=parse_quarters(args.quarters) or (1, 2, 3, 4),
            force=args.force,
        )
        return


if __name__ == "__main__":
    main()
