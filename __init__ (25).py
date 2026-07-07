from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from fvn_dfm.utils.io import ensure_dir
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


SUBMISSIONS_FILENAME_RE = re.compile(r"CIK(?P<cik>\d{10})\.json(?:\.gz)?$", re.IGNORECASE)


@dataclass(frozen=True)
class FilingEventExtractionConfig:
    submissions_dir: Path
    output_table_path: Path
    output_csv_path: Path
    filing_refs_csv_path: Path
    included_forms: tuple[str, ...]
    min_filing_date: str | None = None
    max_filing_date: str | None = None


FILING_EVENT_COLUMNS = [
    "cik",
    "cik10",
    "accession_number",
    "accession_no_dashes",
    "form_type",
    "filing_date",
    "report_date",
    "acceptance_datetime_from_submissions",
    "primary_document",
    "primary_doc_description",
    "act",
    "file_number",
    "film_number",
    "items",
    "size",
    "is_xbrl",
    "is_inline_xbrl",
    "source_file",
    "source_json_section",
    "candidate_for_complete_submission_download",
    "extraction_warning",
]


def normalize_cik_10(cik: str | int) -> str:
    return f"{int(str(cik).strip().lstrip('0') or '0'):010d}"


def normalize_cik_no_leading_zeros(cik: str | int) -> str:
    return str(int(str(cik).strip().lstrip("0") or "0"))


def accession_no_dashes(accession_number: str) -> str:
    return accession_number.strip().replace("-", "")


def infer_cik_from_filename(path: str | Path) -> str | None:
    match = SUBMISSIONS_FILENAME_RE.search(Path(path).name)
    if not match:
        return None
    return match.group("cik")


def read_submissions_json(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if p.suffix == ".gz" or p.name.endswith(".json.gz"):
        with gzip.open(p, "rt", encoding="utf-8") as f:
            return json.load(f)
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get_recent_filings(payload: dict[str, Any]) -> dict[str, list[Any]]:
    filings = payload.get("filings") or {}
    recent = filings.get("recent") or {}
    if not isinstance(recent, dict):
        raise ValueError("SEC submissions JSON has no filings.recent dictionary.")
    return recent


def _safe_list(recent: dict[str, list[Any]], key: str, n: int) -> list[Any]:
    value = recent.get(key)
    if value is None or not isinstance(value, list):
        return [""] * n
    if len(value) < n:
        return value + [""] * (n - len(value))
    return value[:n]


def _parse_date_or_none(value: str | None) -> date | None:
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def _date_in_range(value: str, min_date: str | None, max_date: str | None) -> bool:
    if not value:
        return False
    parsed = _parse_date_or_none(value)
    if parsed is None:
        return False
    min_parsed = _parse_date_or_none(min_date)
    max_parsed = _parse_date_or_none(max_date)
    if min_parsed and parsed < min_parsed:
        return False
    if max_parsed and parsed > max_parsed:
        return False
    return True


def extract_recent_filing_events_from_payload(
    payload: dict[str, Any],
    *,
    source_file: str,
    included_forms: Iterable[str] = ("10-K", "10-Q"),
    min_filing_date: str | None = None,
    max_filing_date: str | None = None,
) -> list[dict[str, Any]]:
    """Extract candidate filing events from SEC submissions JSON `filings.recent`.

    `acceptanceDateTime` in submissions JSON is kept only as metadata.
    The complete submission file `<ACCEPTANCE-DATETIME>` remains the source of truth.
    """
    included = {f.upper() for f in included_forms}
    recent = _get_recent_filings(payload)

    accessions = recent.get("accessionNumber") or []
    if not isinstance(accessions, list):
        raise ValueError("filings.recent.accessionNumber is not a list.")

    n = len(accessions)
    forms = _safe_list(recent, "form", n)
    filing_dates = _safe_list(recent, "filingDate", n)
    report_dates = _safe_list(recent, "reportDate", n)
    acceptance_datetimes = _safe_list(recent, "acceptanceDateTime", n)
    primary_documents = _safe_list(recent, "primaryDocument", n)
    primary_doc_descriptions = _safe_list(recent, "primaryDocDescription", n)
    acts = _safe_list(recent, "act", n)
    file_numbers = _safe_list(recent, "fileNumber", n)
    film_numbers = _safe_list(recent, "filmNumber", n)
    items = _safe_list(recent, "items", n)
    sizes = _safe_list(recent, "size", n)
    is_xbrl = _safe_list(recent, "isXBRL", n)
    is_inline_xbrl = _safe_list(recent, "isInlineXBRL", n)

    cik_from_payload = payload.get("cik")
    cik_from_filename = infer_cik_from_filename(source_file)
    cik10 = normalize_cik_10(cik_from_payload or cik_from_filename or "0")
    cik = normalize_cik_no_leading_zeros(cik10)

    rows: list[dict[str, Any]] = []
    seen_accessions: set[str] = set()

    for i, accession in enumerate(accessions):
        accession = str(accession or "").strip()
        form_type = str(forms[i] or "").strip().upper()
        filing_date = str(filing_dates[i] or "").strip()
        report_date = str(report_dates[i] or "").strip()

        warnings: list[str] = []

        if not accession:
            continue
        if accession in seen_accessions:
            warnings.append("duplicate_accession_in_source_json")
        seen_accessions.add(accession)

        if form_type not in included:
            continue
        if min_filing_date or max_filing_date:
            if not _date_in_range(filing_date, min_filing_date, max_filing_date):
                continue

        if not filing_date:
            warnings.append("missing_filing_date")
        if not report_date:
            warnings.append("missing_report_date")
        if not primary_documents[i]:
            warnings.append("missing_primary_document")
        if not acceptance_datetimes[i]:
            warnings.append("missing_acceptance_datetime_in_submissions_metadata")

        rows.append(
            {
                "cik": cik,
                "cik10": cik10,
                "accession_number": accession,
                "accession_no_dashes": accession_no_dashes(accession),
                "form_type": form_type,
                "filing_date": filing_date,
                "report_date": report_date,
                "acceptance_datetime_from_submissions": str(acceptance_datetimes[i] or ""),
                "primary_document": str(primary_documents[i] or ""),
                "primary_doc_description": str(primary_doc_descriptions[i] or ""),
                "act": str(acts[i] or ""),
                "file_number": str(file_numbers[i] or ""),
                "film_number": str(film_numbers[i] or ""),
                "items": str(items[i] or ""),
                "size": str(sizes[i] or ""),
                "is_xbrl": str(is_xbrl[i] or ""),
                "is_inline_xbrl": str(is_inline_xbrl[i] or ""),
                "source_file": str(source_file),
                "source_json_section": "filings.recent",
                "candidate_for_complete_submission_download": True,
                "extraction_warning": ";".join(warnings),
            }
        )

    return rows


def find_submission_json_files(submissions_dir: str | Path) -> list[Path]:
    p = Path(submissions_dir)
    files = sorted(p.glob("CIK*.json")) + sorted(p.glob("CIK*.json.gz"))
    return sorted(set(files))


def extract_filing_events_from_files(
    paths: Iterable[str | Path],
    *,
    included_forms: Iterable[str] = ("10-K", "10-Q"),
    min_filing_date: str | None = None,
    max_filing_date: str | None = None,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in paths:
        payload = read_submissions_json(path)
        rows.extend(
            extract_recent_filing_events_from_payload(
                payload,
                source_file=str(path),
                included_forms=included_forms,
                min_filing_date=min_filing_date,
                max_filing_date=max_filing_date,
            )
        )

    df = pd.DataFrame(rows, columns=FILING_EVENT_COLUMNS)
    if df.empty:
        return df

    df = df.sort_values(["cik10", "filing_date", "accession_number"]).reset_index(drop=True)
    df = df.drop_duplicates(subset=["cik10", "accession_number"], keep="first")
    return df


def write_filing_refs_csv(df: pd.DataFrame, path: str | Path) -> None:
    """Write downloader-ready candidate CSV.

    Required by SecCompleteSubmissionDownloader:
    cik, accession_number, form_type, filing_date
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    cols = ["cik", "accession_number", "form_type", "filing_date", "report_date", "primary_document"]
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols)
        writer.writeheader()
        for _, row in df.iterrows():
            writer.writerow({c: row.get(c, "") for c in cols})


def write_filing_event_outputs(
    df: pd.DataFrame,
    *,
    output_table_path: str | Path,
    output_csv_path: str | Path,
    filing_refs_csv_path: str | Path,
) -> None:
    """Write source-table outputs.

    Production output is Parquet. If Parquet dependencies are unavailable, pandas
    raises a clear ImportError. The project environment pins pyarrow in
    requirements.txt/environment.yml.
    """
    output_table_path = Path(output_table_path)
    output_csv_path = Path(output_csv_path)
    filing_refs_csv_path = Path(filing_refs_csv_path)

    output_table_path.parent.mkdir(parents=True, exist_ok=True)
    output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    filing_refs_csv_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_parquet(output_table_path, index=False)
    df.to_csv(output_csv_path, index=False)
    write_filing_refs_csv(df, filing_refs_csv_path)


def build_sec_filing_event_outputs(config: FilingEventExtractionConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.sec_filing_event",
        root() / "logs/pipeline/sec_filing_event_extraction.log",
    )
    files = find_submission_json_files(config.submissions_dir)
    if not files:
        raise FileNotFoundError(f"No CIK*.json or CIK*.json.gz files found in {config.submissions_dir}")

    logger.info("Extracting filing events from %d submissions JSON files", len(files))
    df = extract_filing_events_from_files(
        files,
        included_forms=config.included_forms,
        min_filing_date=config.min_filing_date,
        max_filing_date=config.max_filing_date,
    )

    write_filing_event_outputs(
        df,
        output_table_path=config.output_table_path,
        output_csv_path=config.output_csv_path,
        filing_refs_csv_path=config.filing_refs_csv_path,
    )

    logger.info("Wrote %d filing events to %s", len(df), config.output_table_path)
    logger.info("Wrote complete-submission candidate CSV to %s", len(df), config.filing_refs_csv_path)
    return df


def parse_forms(forms: str) -> tuple[str, ...]:
    return tuple(f.strip().upper() for f in forms.split(",") if f.strip())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract SEC filing event candidates from submissions JSON files."
    )
    parser.add_argument("--submissions-dir", default="data/raw/sec/submissions")
    parser.add_argument("--output-table", default="data/processed/source_tables/sec_filing_event.parquet")
    parser.add_argument("--output-csv", default="data/processed/source_tables/sec_filing_event.csv")
    parser.add_argument("--filing-refs-csv", default="data/interim/sec/complete_submission_filing_refs.csv")
    parser.add_argument("--forms", default="10-K,10-Q")
    parser.add_argument("--min-filing-date")
    parser.add_argument("--max-filing-date")
    args = parser.parse_args()

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
