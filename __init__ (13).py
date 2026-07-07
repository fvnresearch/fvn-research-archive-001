from __future__ import annotations

import argparse
import csv
import gzip
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests

from fvn_dfm.data_ingestion.raw_manifest import RawFileManifest, RawManifestRecord
from fvn_dfm.utils.config import load_yaml
from fvn_dfm.utils.io import ensure_dir
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


ACCEPTANCE_DATETIME_RE = re.compile(
    r"<ACCEPTANCE-DATETIME>\s*(?P<value>\d{14})\s*", re.IGNORECASE
)


@dataclass(frozen=True)
class FilingRef:
    cik: str
    accession_number: str
    form_type: str = ""
    filing_date: str = ""


@dataclass(frozen=True)
class CompleteSubmissionDownloadConfig:
    archives_base: str
    output_dir: Path
    manifest_path: Path
    user_agent: str
    max_requests_per_second: float
    retry_count: int
    retry_backoff_seconds: list[int]


def normalize_cik_for_archive(cik: int | str) -> str:
    """SEC archive paths use CIK without leading zeros."""
    return str(int(str(cik).strip().lstrip("0") or "0"))


def normalize_cik_10(cik: int | str) -> str:
    """Return zero-padded 10-digit CIK."""
    return f"{int(str(cik).strip().lstrip('0') or '0'):010d}"


def normalize_accession_no_dashes(accession_number: str) -> str:
    return accession_number.strip().replace("-", "")


def normalize_accession_with_dashes(accession_number: str) -> str:
    """Return accession with dashes if a no-dash accession is supplied.

    SEC accession format: 0000320193-23-000106
    No-dash format:      000032019323000106
    """
    acc = accession_number.strip()
    if "-" in acc:
        return acc
    if len(acc) != 18 or not acc.isdigit():
        raise ValueError(f"Cannot infer dashed accession from: {accession_number}")
    return f"{acc[:10]}-{acc[10:12]}-{acc[12:]}"


def complete_submission_url(
    *,
    cik: int | str,
    accession_number: str,
    archives_base: str,
) -> str:
    """Build SEC complete-submission .txt URL.

    Example:
    https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/0000320193-23-000106.txt
    """
    cik_archive = normalize_cik_for_archive(cik)
    acc_dashed = normalize_accession_with_dashes(accession_number)
    acc_no_dashes = normalize_accession_no_dashes(acc_dashed)
    return (
        archives_base.rstrip("/")
        + f"/edgar/data/{cik_archive}/{acc_no_dashes}/{acc_dashed}.txt"
    )


def complete_submission_output_path(
    *,
    output_dir: str | Path,
    cik: int | str,
    accession_number: str,
    gzip_raw: bool = False,
) -> Path:
    cik_10 = normalize_cik_10(cik)
    acc_dashed = normalize_accession_with_dashes(accession_number)
    suffix = ".txt.gz" if gzip_raw else ".txt"
    return Path(output_dir) / cik_10 / f"{acc_dashed}{suffix}"


def parse_acceptance_datetime_from_text(text: str) -> datetime | None:
    """Parse EDGAR <ACCEPTANCE-DATETIME> as naive datetime.

    EDGAR complete submission files usually encode it as YYYYMMDDHHMMSS.
    Timezone interpretation is handled later in point-in-time tables.
    """
    match = ACCEPTANCE_DATETIME_RE.search(text)
    if not match:
        return None
    value = match.group("value")
    return datetime.strptime(value, "%Y%m%d%H%M%S")


def load_complete_submission_config(config_path: str | Path) -> CompleteSubmissionDownloadConfig:
    cfg = load_yaml(config_path)
    sec = cfg["sec"]
    endpoints = sec["endpoints"]
    policy = sec["request_policy"]
    raw_storage = sec["raw_storage"]

    user_agent = policy["user_agent"]
    if "to_be_set" in user_agent.lower():
        raise ValueError(
            "SEC User-Agent is not set. Edit configs/01_data_sources.yaml "
            "and replace 'contact_email_to_be_set' before downloading."
        )

    return CompleteSubmissionDownloadConfig(
        archives_base=endpoints["sec_archives_base"],
        output_dir=root() / raw_storage["complete_submissions"],
        manifest_path=root() / "data/manifests/raw_file_manifest.csv",
        user_agent=user_agent,
        max_requests_per_second=float(policy.get("max_requests_per_second", 5)),
        retry_count=int(policy.get("retry_count", 5)),
        retry_backoff_seconds=list(policy.get("retry_backoff_seconds", [1, 2, 5, 10, 30])),
    )


class SecCompleteSubmissionDownloader:
    """Downloader for SEC complete submission .txt files.

    Complete submission files are required for:
    - EDGAR header reconstruction
    - <ACCEPTANCE-DATETIME>
    - primary document discovery
    - raw filing text preservation

    Design rules:
    - raw files are immutable
    - existing files are skipped unless force=True
    - force=True creates timestamped copies, never overwrites
    - every successful file is appended to raw_file_manifest.csv
    """

    def __init__(self, config: CompleteSubmissionDownloadConfig) -> None:
        self.config = config
        self.output_dir = ensure_dir(config.output_dir)
        self.manifest = RawFileManifest(config.manifest_path)
        self.logger = get_logger(
            "fvn_dfm.sec_complete_submissions",
            root() / "logs/pipeline/sec_complete_submissions_download.log",
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "text/plain,text/html,*/*",
            }
        )
        self._min_interval = 1.0 / max(config.max_requests_per_second, 0.1)
        self._last_request_ts = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_ts
        sleep_for = self._min_interval - elapsed
        if sleep_for > 0:
            time.sleep(sleep_for)
        self._last_request_ts = time.time()

    def _request(self, url: str) -> tuple[requests.Response, int]:
        last_response: requests.Response | None = None
        for attempt in range(self.config.retry_count + 1):
            self._throttle()
            response = self.session.get(url, timeout=45)
            last_response = response
            if response.status_code == 200:
                return response, attempt
            if response.status_code in {403, 404}:
                return response, attempt
            if attempt < self.config.retry_count:
                backoff = self.config.retry_backoff_seconds[
                    min(attempt, len(self.config.retry_backoff_seconds) - 1)
                ]
                time.sleep(backoff)
        assert last_response is not None
        return last_response, self.config.retry_count

    def download_filing(
        self,
        filing: FilingRef,
        *,
        force: bool = False,
        gzip_raw: bool = False,
    ) -> Path | None:
        url = complete_submission_url(
            cik=filing.cik,
            accession_number=filing.accession_number,
            archives_base=self.config.archives_base,
        )
        output_path = complete_submission_output_path(
            output_dir=self.output_dir,
            cik=filing.cik,
            accession_number=filing.accession_number,
            gzip_raw=gzip_raw,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.exists() and not force:
            self.logger.info("Skipping existing immutable file: %s", output_path)
            return output_path

        if output_path.exists() and force:
            timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            if gzip_raw:
                output_path = output_path.with_name(output_path.name.replace(".txt.gz", f".{timestamp}.txt.gz"))
            else:
                output_path = output_path.with_name(output_path.name.replace(".txt", f".{timestamp}.txt"))

        response, retry_count = self._request(url)

        if response.status_code != 200:
            self.logger.warning(
                "Download failed for CIK %s accession %s | HTTP %s",
                filing.cik,
                filing.accession_number,
                response.status_code,
            )
            return None

        content = response.content
        text_preview = content[:200000].decode("utf-8", errors="replace")
        accepted_at = parse_acceptance_datetime_from_text(text_preview)
        if accepted_at is None:
            self.logger.warning(
                "No ACCEPTANCE-DATETIME parsed for CIK %s accession %s",
                filing.cik,
                filing.accession_number,
            )

        if gzip_raw:
            with gzip.open(output_path, "wb") as f:
                f.write(content)
            compression = "gzip"
        else:
            output_path.write_bytes(content)
            compression = ""

        notes = (
            f"CIK={filing.cik}; accession={normalize_accession_with_dashes(filing.accession_number)}; "
            f"form_type={filing.form_type}; filing_date={filing.filing_date}; "
            f"acceptance_datetime={accepted_at.isoformat() if accepted_at else ''}"
        )

        record = RawManifestRecord.from_downloaded_file(
            path=output_path,
            source_family="sec_complete_submission_text",
            source_name="SEC complete submission text file",
            source_url_or_origin=url,
            compression_type=compression,
            download_status="success",
            http_status_code=response.status_code,
            retry_count=retry_count,
            notes=notes,
        )
        self.manifest.append(record)
        self.logger.info(
            "Downloaded complete submission CIK %s accession %s to %s",
            filing.cik,
            filing.accession_number,
            output_path,
        )
        return output_path

    def download_many(
        self,
        filings: Iterable[FilingRef],
        *,
        force: bool = False,
        gzip_raw: bool = False,
    ) -> list[Path]:
        paths: list[Path] = []
        for filing in filings:
            path = self.download_filing(filing, force=force, gzip_raw=gzip_raw)
            if path is not None:
                paths.append(path)
        self.manifest.validate()
        return paths


def read_filing_refs_csv(path: str | Path) -> list[FilingRef]:
    """Read filing references from CSV.

    Required columns:
    - cik
    - accession_number

    Optional columns:
    - form_type
    - filing_date
    """
    p = Path(path)
    filings: list[FilingRef] = []
    with p.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"cik", "accession_number"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns in {p}: {sorted(missing)}")

        for row in reader:
            cik = (row.get("cik") or "").strip()
            accession = (row.get("accession_number") or "").strip()
            if not cik or not accession:
                continue
            filings.append(
                FilingRef(
                    cik=cik,
                    accession_number=accession,
                    form_type=(row.get("form_type") or "").strip(),
                    filing_date=(row.get("filing_date") or "").strip(),
                )
            )
    return filings


def main() -> None:
    parser = argparse.ArgumentParser(description="Download SEC complete submission .txt files.")
    parser.add_argument("--config", default="configs/01_data_sources.yaml")
    parser.add_argument("--cik", help="CIK for one filing.")
    parser.add_argument("--accession-number", help="SEC accession number for one filing.")
    parser.add_argument("--form-type", default="")
    parser.add_argument("--filing-date", default="")
    parser.add_argument("--filing-refs-csv", help="CSV with cik,accession_number[,form_type,filing_date].")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--gzip-raw", action="store_true")
    args = parser.parse_args()

    filings: list[FilingRef] = []
    if args.cik and args.accession_number:
        filings.append(
            FilingRef(
                cik=args.cik,
                accession_number=args.accession_number,
                form_type=args.form_type,
                filing_date=args.filing_date,
            )
        )
    if args.filing_refs_csv:
        filings.extend(read_filing_refs_csv(args.filing_refs_csv))

    if not filings:
        raise SystemExit("No filings supplied. Use --cik + --accession-number or --filing-refs-csv.")

    config = load_complete_submission_config(root() / args.config)
    downloader = SecCompleteSubmissionDownloader(config)
    downloader.download_many(filings, force=args.force, gzip_raw=args.gzip_raw)


if __name__ == "__main__":
    main()
