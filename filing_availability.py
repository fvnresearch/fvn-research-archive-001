from __future__ import annotations

import argparse
import gzip
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import requests

from fvn_dfm.data_ingestion.raw_manifest import RawFileManifest, RawManifestRecord
from fvn_dfm.utils.config import load_yaml
from fvn_dfm.utils.io import ensure_dir
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


@dataclass(frozen=True)
class SecDownloadConfig:
    submissions_base: str
    output_dir: Path
    manifest_path: Path
    user_agent: str
    max_requests_per_second: float
    retry_count: int
    retry_backoff_seconds: list[int]


def cik_to_submissions_filename(cik: int | str) -> str:
    """Return SEC submissions filename, e.g. CIK0000320193.json."""
    cik_int = int(str(cik).lstrip("0"))
    return f"CIK{cik_int:010d}.json"


def cik_to_submissions_url(cik: int | str, submissions_base: str) -> str:
    return submissions_base.rstrip("/") + "/" + cik_to_submissions_filename(cik)


def load_sec_download_config(config_path: str | Path) -> SecDownloadConfig:
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

    return SecDownloadConfig(
        submissions_base=endpoints["submissions_base"],
        output_dir=root() / raw_storage["submissions"],
        manifest_path=root() / "data/manifests/raw_file_manifest.csv",
        user_agent=user_agent,
        max_requests_per_second=float(policy.get("max_requests_per_second", 5)),
        retry_count=int(policy.get("retry_count", 5)),
        retry_backoff_seconds=list(policy.get("retry_backoff_seconds", [1, 2, 5, 10, 30])),
    )


class SecSubmissionsDownloader:
    """Downloader for SEC CIK submissions JSON files.

    This module downloads one file per CIK from:
    https://data.sec.gov/submissions/CIK##########.json

    Design rules:
    - raw files are immutable
    - each file is recorded in raw_file_manifest.csv
    - existing files are not overwritten unless force=True
    - request rate is throttled
    - SEC User-Agent is mandatory
    """

    def __init__(self, config: SecDownloadConfig) -> None:
        self.config = config
        self.output_dir = ensure_dir(config.output_dir)
        self.manifest = RawFileManifest(config.manifest_path)
        self.logger = get_logger(
            "fvn_dfm.sec_submissions",
            root() / "logs/pipeline/sec_submissions_download.log",
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": config.user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "application/json,text/plain,*/*",
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
            response = self.session.get(url, timeout=30)
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

    def download_cik(self, cik: int | str, *, force: bool = False, gzip_raw: bool = False) -> Path | None:
        filename = cik_to_submissions_filename(cik)
        url = cik_to_submissions_url(cik, self.config.submissions_base)

        if gzip_raw:
            output_path = self.output_dir / f"{filename}.gz"
        else:
            output_path = self.output_dir / filename

        if output_path.exists() and not force:
            self.logger.info("Skipping existing immutable file: %s", output_path)
            return output_path

        if output_path.exists() and force:
            timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
            output_path = self.output_dir / f"{output_path.stem}.{timestamp}{output_path.suffix}"

        response, retry_count = self._request(url)

        if response.status_code != 200:
            self.logger.warning("Download failed for CIK %s | HTTP %s", cik, response.status_code)
            return None

        # Validate JSON before storing.
        payload = response.content
        try:
            json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"SEC submissions response for {cik} is not valid JSON") from exc

        if gzip_raw:
            with gzip.open(output_path, "wb") as f:
                f.write(payload)
            compression = "gzip"
        else:
            output_path.write_bytes(payload)
            compression = ""

        record = RawManifestRecord.from_downloaded_file(
            path=output_path,
            source_family="sec_submissions_api",
            source_name="SEC submissions JSON",
            source_url_or_origin=url,
            compression_type=compression,
            download_status="success",
            http_status_code=response.status_code,
            retry_count=retry_count,
            notes=f"CIK={str(cik)}",
        )
        self.manifest.append(record)
        self.logger.info("Downloaded CIK %s to %s", cik, output_path)
        return output_path

    def download_many(self, ciks: Iterable[int | str], *, force: bool = False, gzip_raw: bool = False) -> list[Path]:
        paths: list[Path] = []
        for cik in ciks:
            path = self.download_cik(cik, force=force, gzip_raw=gzip_raw)
            if path is not None:
                paths.append(path)
        self.manifest.validate()
        return paths


def read_cik_list(path: str | Path) -> list[str]:
    p = Path(path)
    ciks: list[str] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        clean = line.strip()
        if not clean or clean.startswith("#"):
            continue
        ciks.append(clean.split(",")[0].strip())
    return ciks


def main() -> None:
    parser = argparse.ArgumentParser(description="Download SEC submissions JSON files by CIK.")
    parser.add_argument("--config", default="configs/01_data_sources.yaml")
    parser.add_argument("--cik", action="append", help="CIK to download. Can be supplied multiple times.")
    parser.add_argument("--cik-file", help="Text/CSV file with one CIK per line.")
    parser.add_argument("--force", action="store_true", help="Do not overwrite; create timestamped copy if file exists.")
    parser.add_argument("--gzip-raw", action="store_true", help="Store downloaded JSON as gzip.")
    args = parser.parse_args()

    ciks: list[str] = []
    if args.cik:
        ciks.extend(args.cik)
    if args.cik_file:
        ciks.extend(read_cik_list(args.cik_file))

    if not ciks:
        raise SystemExit("No CIKs supplied. Use --cik or --cik-file.")

    config = load_sec_download_config(root() / args.config)
    downloader = SecSubmissionsDownloader(config)
    downloader.download_many(ciks, force=args.force, gzip_raw=args.gzip_raw)


if __name__ == "__main__":
    main()
