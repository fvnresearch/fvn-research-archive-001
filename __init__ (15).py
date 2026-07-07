from __future__ import annotations

import argparse
import csv
import gzip
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

from fvn_dfm.data_ingestion.raw_manifest import RawFileManifest, RawManifestRecord
from fvn_dfm.normalization.sec_filing_event import (
    accession_no_dashes,
    normalize_cik_10,
    normalize_cik_no_leading_zeros,
)
from fvn_dfm.utils.config import load_yaml
from fvn_dfm.utils.io import ensure_dir
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


DOCUMENT_BLOCK_RE = re.compile(r"<DOCUMENT>(?P<body>.*?)</DOCUMENT>", re.IGNORECASE | re.DOTALL)
DOCUMENT_FIELD_RE_TEMPLATE = r"<{field}>\s*(?P<value>[^\n\r<]+)"


@dataclass(frozen=True)
class PrimaryDocumentCandidate:
    cik: str
    cik10: str
    accession_number: str
    accession_no_dashes: str
    form_type: str
    primary_document: str
    discovery_method: str
    complete_submission_file: str = ""
    filing_availability_source: str = ""
    candidate_warning: str = ""

    @property
    def lineage_key(self) -> str:
        return f"{self.cik10}:{self.accession_number}:{self.primary_document}"


@dataclass(frozen=True)
class PrimaryDocumentDownloadConfig:
    archives_base: str
    output_dir: Path
    manifest_path: Path
    user_agent: str
    max_requests_per_second: float
    retry_count: int
    retry_backoff_seconds: list[int]


@dataclass(frozen=True)
class PrimaryDocumentDiscoveryConfig:
    filing_availability_path: Path | None
    complete_submissions_dir: Path
    candidates_csv_path: Path
    allowed_forms: tuple[str, ...] = ("10-K", "10-Q")


def read_text_maybe_gzip(path: str | Path, *, max_chars: int | None = None) -> str:
    p = Path(path)
    if p.suffix == ".gz" or p.name.endswith(".gz"):
        with gzip.open(p, "rt", encoding="utf-8", errors="replace") as f:
            return f.read(max_chars) if max_chars else f.read()
    with p.open("r", encoding="utf-8", errors="replace") as f:
        return f.read(max_chars) if max_chars else f.read()


def parse_document_field(block: str, field: str) -> str:
    pattern = re.compile(DOCUMENT_FIELD_RE_TEMPLATE.format(field=re.escape(field)), re.IGNORECASE)
    match = pattern.search(block)
    if not match:
        return ""
    return match.group("value").strip()


def parse_complete_submission_document_index(text: str) -> list[dict[str, str]]:
    """Parse <DOCUMENT> blocks from a complete submission file."""
    docs: list[dict[str, str]] = []
    for i, match in enumerate(DOCUMENT_BLOCK_RE.finditer(text), start=1):
        block = match.group("body")
        docs.append(
            {
                "sequence": parse_document_field(block, "SEQUENCE") or str(i),
                "type": parse_document_field(block, "TYPE"),
                "filename": parse_document_field(block, "FILENAME"),
                "description": parse_document_field(block, "DESCRIPTION"),
            }
        )
    return docs


def choose_primary_document_from_index(
    docs: list[dict[str, str]],
    *,
    form_type: str,
    primary_document_hint: str = "",
    allowed_forms: Iterable[str] = ("10-K", "10-Q"),
) -> tuple[str, str, str]:
    """Return primary document filename, discovery method, warning.

    Priority:
    1. exact primary document hint if present in <DOCUMENT> index
    2. first document whose TYPE equals the filing form type
    3. first document whose TYPE is in allowed forms
    4. empty with warning
    """
    warnings: list[str] = []
    allowed = {f.upper() for f in allowed_forms}
    form_upper = (form_type or "").upper()
    hint = (primary_document_hint or "").strip()

    docs_with_filename = [d for d in docs if d.get("filename")]

    if hint:
        for doc in docs_with_filename:
            if doc["filename"].strip().lower() == hint.lower():
                return doc["filename"], "primary_document_hint_confirmed_in_complete_submission", ""
        warnings.append("primary_document_hint_not_found_in_complete_submission_index")
        return hint, "primary_document_hint_from_filing_event", ";".join(warnings)

    if form_upper:
        for doc in docs_with_filename:
            if doc.get("type", "").upper() == form_upper:
                return doc["filename"], "document_type_matches_form", ""

    for doc in docs_with_filename:
        if doc.get("type", "").upper() in allowed:
            return doc["filename"], "document_type_allowed_form_fallback", ""

    warnings.append("primary_document_not_discovered")
    return "", "not_discovered", ";".join(warnings)


def primary_document_url(
    *,
    cik: str | int,
    accession_number: str,
    primary_document: str,
    archives_base: str,
) -> str:
    cik_archive = normalize_cik_no_leading_zeros(cik)
    acc_no_dash = accession_no_dashes(accession_number)
    return archives_base.rstrip("/") + f"/edgar/data/{cik_archive}/{acc_no_dash}/{primary_document}"


def primary_document_output_path(
    *,
    output_dir: str | Path,
    cik: str | int,
    accession_number: str,
    primary_document: str,
    gzip_raw: bool = False,
) -> Path:
    cik10 = normalize_cik_10(cik)
    suffix = ".gz" if gzip_raw and not primary_document.endswith(".gz") else ""
    return Path(output_dir) / cik10 / accession_number / f"{primary_document}{suffix}"


def infer_complete_submission_by_accession(
    complete_submissions_dir: str | Path,
    *,
    cik10: str,
    accession_number: str,
) -> Path | None:
    root_dir = Path(complete_submissions_dir)
    candidate_dir = root_dir / cik10
    for suffix in [".txt", ".txt.gz"]:
        candidate = candidate_dir / f"{accession_number}{suffix}"
        if candidate.exists():
            return candidate
    # fallback recursive search
    matches = list(root_dir.rglob(f"{accession_number}.txt")) + list(root_dir.rglob(f"{accession_number}.txt.gz"))
    return matches[0] if matches else None


def _read_filing_availability(path: str | Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    p = Path(path)
    if not p.exists():
        return pd.DataFrame()
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    return pd.read_csv(p, dtype=str).fillna("")


def discover_primary_document_candidates(config: PrimaryDocumentDiscoveryConfig) -> list[PrimaryDocumentCandidate]:
    df = _read_filing_availability(config.filing_availability_path)
    if df.empty:
        raise FileNotFoundError(
            "Filing availability table is required for primary document discovery. "
            "Expected CSV/parquet with accession lineage."
        )

    candidates: list[PrimaryDocumentCandidate] = []
    allowed = {f.upper() for f in config.allowed_forms}

    for _, row in df.iterrows():
        cik10 = normalize_cik_10(str(row.get("cik10") or row.get("cik") or "0"))
        cik = normalize_cik_no_leading_zeros(cik10)
        accession = str(row.get("accession_number") or "").strip()
        if not accession:
            continue

        form_type = str(row.get("form_type_from_header") or row.get("form_type_from_event") or "").strip().upper()
        if form_type and form_type not in allowed:
            continue

        primary_hint = str(row.get("primary_document_from_event") or "").strip()
        complete_file = str(row.get("header_source_file") or "").strip()
        if not complete_file:
            inferred = infer_complete_submission_by_accession(
                config.complete_submissions_dir,
                cik10=cik10,
                accession_number=accession,
            )
            complete_file = str(inferred) if inferred else ""

        docs: list[dict[str, str]] = []
        warning: list[str] = []
        if complete_file and Path(complete_file).exists():
            text = read_text_maybe_gzip(complete_file)
            docs = parse_complete_submission_document_index(text)
        else:
            warning.append("complete_submission_file_missing_for_document_index")

        primary_doc, method, method_warning = choose_primary_document_from_index(
            docs,
            form_type=form_type,
            primary_document_hint=primary_hint,
            allowed_forms=config.allowed_forms,
        )
        if method_warning:
            warning.append(method_warning)

        if not primary_doc:
            warning.append("no_primary_document_filename")
            continue

        candidates.append(
            PrimaryDocumentCandidate(
                cik=cik,
                cik10=cik10,
                accession_number=accession,
                accession_no_dashes=accession_no_dashes(accession),
                form_type=form_type,
                primary_document=primary_doc,
                discovery_method=method,
                complete_submission_file=complete_file,
                filing_availability_source=str(config.filing_availability_path or ""),
                candidate_warning=";".join(w for w in warning if w),
            )
        )

    # deterministic unique candidates
    seen: set[str] = set()
    unique: list[PrimaryDocumentCandidate] = []
    for candidate in sorted(candidates, key=lambda c: (c.cik10, c.accession_number, c.primary_document)):
        if candidate.lineage_key in seen:
            continue
        seen.add(candidate.lineage_key)
        unique.append(candidate)

    return unique


def write_primary_document_candidates_csv(candidates: Iterable[PrimaryDocumentCandidate], path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "cik",
        "cik10",
        "accession_number",
        "accession_no_dashes",
        "form_type",
        "primary_document",
        "discovery_method",
        "complete_submission_file",
        "filing_availability_source",
        "candidate_warning",
    ]
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for c in candidates:
            writer.writerow({col: getattr(c, col) for col in columns})


def read_primary_document_candidates_csv(path: str | Path) -> list[PrimaryDocumentCandidate]:
    p = Path(path)
    candidates: list[PrimaryDocumentCandidate] = []
    with p.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"cik", "cik10", "accession_number", "primary_document"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing required columns in {p}: {sorted(missing)}")
        for row in reader:
            if not row.get("primary_document"):
                continue
            candidates.append(
                PrimaryDocumentCandidate(
                    cik=str(row.get("cik") or ""),
                    cik10=normalize_cik_10(row.get("cik10") or row.get("cik") or "0"),
                    accession_number=str(row.get("accession_number") or ""),
                    accession_no_dashes=str(row.get("accession_no_dashes") or accession_no_dashes(row.get("accession_number") or "")),
                    form_type=str(row.get("form_type") or ""),
                    primary_document=str(row.get("primary_document") or ""),
                    discovery_method=str(row.get("discovery_method") or ""),
                    complete_submission_file=str(row.get("complete_submission_file") or ""),
                    filing_availability_source=str(row.get("filing_availability_source") or ""),
                    candidate_warning=str(row.get("candidate_warning") or ""),
                )
            )
    return candidates


def load_primary_document_download_config(config_path: str | Path) -> PrimaryDocumentDownloadConfig:
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

    return PrimaryDocumentDownloadConfig(
        archives_base=endpoints["sec_archives_base"],
        output_dir=root() / raw_storage["primary_documents"],
        manifest_path=root() / "data/manifests/raw_file_manifest.csv",
        user_agent=user_agent,
        max_requests_per_second=float(policy.get("max_requests_per_second", 5)),
        retry_count=int(policy.get("retry_count", 5)),
        retry_backoff_seconds=list(policy.get("retry_backoff_seconds", [1, 2, 5, 10, 30])),
    )


class SecPrimaryDocumentDownloader:
    """Download discovered primary filing documents from SEC Archives.

    Raw primary documents are stored separately from complete submission files
    because text extraction should operate on the actual 10-K/10-Q HTML document,
    not on SGML wrapper text.
    """

    def __init__(self, config: PrimaryDocumentDownloadConfig) -> None:
        self.config = config
        self.output_dir = ensure_dir(config.output_dir)
        self.manifest = RawFileManifest(config.manifest_path)
        self.logger = get_logger(
            "fvn_dfm.sec_primary_documents",
            root() / "logs/pipeline/sec_primary_documents_download.log",
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "text/html,application/xhtml+xml,text/plain,*/*",
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

    def download_candidate(
        self,
        candidate: PrimaryDocumentCandidate,
        *,
        force: bool = False,
        gzip_raw: bool = False,
    ) -> Path | None:
        url = primary_document_url(
            cik=candidate.cik,
            accession_number=candidate.accession_number,
            primary_document=candidate.primary_document,
            archives_base=self.config.archives_base,
        )
        output_path = primary_document_output_path(
            output_dir=self.output_dir,
            cik=candidate.cik10,
            accession_number=candidate.accession_number,
            primary_document=candidate.primary_document,
            gzip_raw=gzip_raw,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.exists() and not force:
            self.logger.info("Skipping existing immutable primary document: %s", output_path)
            return output_path

        if output_path.exists() and force:
            timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            output_path = output_path.with_name(f"{output_path.name}.{timestamp}")

        response, retry_count = self._request(url)
        if response.status_code != 200:
            self.logger.warning(
                "Primary document download failed | CIK %s accession %s document %s | HTTP %s",
                candidate.cik,
                candidate.accession_number,
                candidate.primary_document,
                response.status_code,
            )
            return None

        content = response.content
        if gzip_raw:
            with gzip.open(output_path, "wb") as f:
                f.write(content)
            compression = "gzip"
        else:
            output_path.write_bytes(content)
            compression = ""

        notes = (
            f"CIK={candidate.cik}; accession={candidate.accession_number}; "
            f"form_type={candidate.form_type}; primary_document={candidate.primary_document}; "
            f"discovery_method={candidate.discovery_method}; candidate_warning={candidate.candidate_warning}"
        )

        record = RawManifestRecord.from_downloaded_file(
            path=output_path,
            source_family="sec_primary_document",
            source_name="SEC primary filing document",
            source_url_or_origin=url,
            compression_type=compression,
            download_status="success",
            http_status_code=response.status_code,
            retry_count=retry_count,
            notes=notes,
        )
        self.manifest.append(record)
        self.logger.info("Downloaded primary document to %s", output_path)
        return output_path

    def download_many(
        self,
        candidates: Iterable[PrimaryDocumentCandidate],
        *,
        force: bool = False,
        gzip_raw: bool = False,
    ) -> list[Path]:
        paths: list[Path] = []
        for candidate in candidates:
            path = self.download_candidate(candidate, force=force, gzip_raw=gzip_raw)
            if path is not None:
                paths.append(path)
        self.manifest.validate()
        return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Discover and download SEC primary filing documents.")
    parser.add_argument("--config", default="configs/01_data_sources.yaml")
    parser.add_argument("--filing-availability-path", default="data/processed/point_in_time/filing_availability.csv")
    parser.add_argument("--complete-submissions-dir", default="data/raw/sec/complete_submissions")
    parser.add_argument("--candidates-csv", default="data/interim/sec/primary_document_candidates.csv")
    parser.add_argument("--allowed-forms", default="10-K,10-Q")
    parser.add_argument("--discover-only", action="store_true")
    parser.add_argument("--download-only", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--gzip-raw", action="store_true")
    args = parser.parse_args()

    allowed_forms = tuple(f.strip().upper() for f in args.allowed_forms.split(",") if f.strip())

    if not args.download_only:
        discovery_config = PrimaryDocumentDiscoveryConfig(
            filing_availability_path=root() / args.filing_availability_path,
            complete_submissions_dir=root() / args.complete_submissions_dir,
            candidates_csv_path=root() / args.candidates_csv,
            allowed_forms=allowed_forms,
        )
        candidates = discover_primary_document_candidates(discovery_config)
        write_primary_document_candidates_csv(candidates, discovery_config.candidates_csv_path)
    else:
        candidates = read_primary_document_candidates_csv(root() / args.candidates_csv)

    if args.discover_only:
        return

    download_config = load_primary_document_download_config(root() / args.config)
    downloader = SecPrimaryDocumentDownloader(download_config)
    downloader.download_many(candidates, force=args.force, gzip_raw=args.gzip_raw)


if __name__ == "__main__":
    main()
