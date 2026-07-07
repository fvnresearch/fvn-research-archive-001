from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


FINAL_ARCHIVE_FREEZE_VERSION = "FINAL_ARCHIVE_FREEZE_V0"

CRITICAL_FREEZE_ARTIFACTS: tuple[tuple[str, str, bool], ...] = (
    ("repository_readme", "README.md", True),
    ("research_protocol", "RESEARCH_PROTOCOL.md", True),
    ("research_log", "RESEARCH_LOG.md", True),
    ("final_verdict_notes", "FINAL_VERDICT.md", True),
    ("changelog", "CHANGELOG.md", True),
    ("license", "LICENSE", True),
    ("final_research_verdict", "data/processed/reports/final_research_verdict.csv", True),
    ("final_research_evidence", "data/processed/reports/final_research_evidence.csv", True),
    ("final_research_criteria", "data/processed/reports/final_research_criteria.csv", True),
    ("release_checklist", "data/processed/reports/release_checklist.csv", True),
    ("release_gate_summary", "data/processed/reports/release_gate_summary.csv", True),
    ("schema_contract_summary", "data/processed/reports/schema_contract_summary.csv", True),
    ("schema_contract_registry", "data/processed/reports/schema_contract_registry.csv", True),
    ("data_lineage_nodes", "data/processed/reports/data_lineage_nodes.csv", True),
    ("data_lineage_edges", "data/processed/reports/data_lineage_edges.csv", True),
    ("publication_manifest", "data/processed/reports/publication_manifest.csv", True),
    ("publication_sanitization_checks", "data/processed/reports/publication_sanitization_checks.csv", True),
    ("reproducibility_manifest", "data/processed/reports/reproducibility_file_manifest.csv", True),
    ("public_readme", "outputs/publication/publication_package_v0/PUBLICATION_README.md", True),
    ("publication_package_zip", "outputs/publication/publication_package_v0.zip", True),
    ("final_verdict_report", "outputs/reports/final_research_verdict.md", True),
    ("release_checklist_report", "outputs/reports/release_checklist.md", True),
    ("data_lineage_map", "outputs/reports/data_lineage_map.md", True),
    ("schema_contract_report", "outputs/reports/schema_contract_validation_report.md", True),
    ("reproducibility_pack_zip", "outputs/audit/reproducibility_pack.zip", True),
    ("live_readiness_summary", "data/processed/reports/live_data_readiness_summary.csv", False),
    ("live_pipeline_execution_summary", "outputs/logs/live_pipeline_execution_summary.csv", False),
)


@dataclass(frozen=True)
class FinalArchiveFreezeConfig:
    repo_root: Path
    release_version: str
    release_title: str
    freeze_manifest_output_table_path: Path
    freeze_manifest_output_csv_path: Path
    release_metadata_output_csv_path: Path
    release_metadata_output_json_path: Path
    release_notes_output_path: Path
    frozen_audit_manifest_path: Path
    diagnostics_path: Path
    require_release_gate_pass: bool = True
    require_publication_package: bool = True
    include_optional_missing: bool = True
    freeze_version: str = FINAL_ARCHIVE_FREEZE_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _first_value(path: Path, column: str, default: str = "MISSING") -> str:
    df = _read_csv(path)
    if df.empty or column not in df.columns:
        return default
    value = df.iloc[0].get(column, default)
    if pd.isna(value):
        return default
    return str(value)


def _valid_release_version(version: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._\-+]{1,63}", version.strip()))


def _artifact_row(
    *,
    artifact_id: str,
    relative_path: str,
    required: bool,
    repo_root: Path,
    release_version: str,
    freeze_version: str,
) -> dict[str, Any]:
    path = repo_root / relative_path
    exists = path.exists() and path.is_file()
    size = int(path.stat().st_size) if exists else None
    checksum = _sha256_file(path) if exists else ""
    suffix = path.suffix.lower()
    if relative_path.endswith(".md"):
        artifact_kind = "markdown"
    elif suffix == ".csv":
        artifact_kind = "csv"
    elif suffix == ".json":
        artifact_kind = "json"
    elif suffix == ".zip":
        artifact_kind = "zip"
    else:
        artifact_kind = "file"

    return {
        "release_version": release_version,
        "artifact_id": artifact_id,
        "relative_path": relative_path,
        "artifact_kind": artifact_kind,
        "required": bool(required),
        "exists": bool(exists),
        "size_bytes": size,
        "sha256": checksum,
        "frozen_at_utc": _utc_now(),
        "freeze_version": freeze_version,
    }


def build_freeze_manifest(config: FinalArchiveFreezeConfig) -> pd.DataFrame:
    rows = [
        _artifact_row(
            artifact_id=artifact_id,
            relative_path=relative_path,
            required=required,
            repo_root=config.repo_root,
            release_version=config.release_version,
            freeze_version=config.freeze_version,
        )
        for artifact_id, relative_path, required in CRITICAL_FREEZE_ARTIFACTS
    ]
    return pd.DataFrame(rows)


def build_release_metadata(config: FinalArchiveFreezeConfig, manifest: pd.DataFrame) -> pd.DataFrame:
    release_gate_status = _first_value(config.repo_root / "data/processed/reports/release_gate_summary.csv", "release_gate_status")
    final_verdict = _first_value(config.repo_root / "data/processed/reports/final_research_verdict.csv", "final_verdict")
    schema_status = _first_value(config.repo_root / "data/processed/reports/schema_contract_summary.csv", "schema_contract_status")
    live_readiness = _first_value(config.repo_root / "data/processed/reports/live_data_readiness_summary.csv", "live_readiness_status")
    sanitization_status = "MISSING"
    sanitization_path = config.repo_root / "data/processed/reports/publication_sanitization_checks.csv"
    sanitization = _read_csv(sanitization_path)
    if not sanitization.empty and "status" in sanitization.columns:
        sanitization_status = "PASS" if int((sanitization["status"] == "FAIL").sum()) == 0 else "FAIL"

    required_missing = 0
    if not manifest.empty:
        required_missing = int(((manifest["required"].astype(bool)) & (~manifest["exists"].astype(bool))).sum())

    release_version_valid = _valid_release_version(config.release_version)
    publication_package_exists = bool((config.repo_root / "outputs/publication/publication_package_v0.zip").exists())
    release_gate_ok = release_gate_status == "PASS" or (not config.require_release_gate_pass and release_gate_status in {"PASS", "PASS_WITH_WARNINGS"})
    publication_ok = publication_package_exists or not config.require_publication_package

    freeze_status = "FROZEN" if release_version_valid and required_missing == 0 and release_gate_ok and publication_ok else "BLOCKED"

    return pd.DataFrame(
        [
            {
                "release_version": config.release_version,
                "release_title": config.release_title,
                "freeze_status": freeze_status,
                "release_gate_status": release_gate_status,
                "final_verdict": final_verdict,
                "schema_contract_status": schema_status,
                "publication_sanitization_status": sanitization_status,
                "live_readiness_status": live_readiness,
                "required_artifacts": int(manifest["required"].astype(bool).sum()) if not manifest.empty else 0,
                "required_missing_artifacts": required_missing,
                "total_frozen_artifacts": len(manifest),
                "release_version_valid": release_version_valid,
                "publication_package_exists": publication_package_exists,
                "python_version": sys.version.replace("\n", " "),
                "platform": platform.platform(),
                "frozen_at_utc": _utc_now(),
                "freeze_version": config.freeze_version,
            }
        ]
    )


def build_final_archive_diagnostics(manifest: pd.DataFrame, metadata: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "freeze_version", "value": FINAL_ARCHIVE_FREEZE_VERSION},
        {"diagnostic": "manifest_rows", "value": len(manifest)},
        {"diagnostic": "metadata_rows", "value": len(metadata)},
    ]
    if not manifest.empty:
        rows.extend(
            [
                {"diagnostic": "required_artifacts", "value": int(manifest["required"].astype(bool).sum())},
                {"diagnostic": "existing_artifacts", "value": int(manifest["exists"].astype(bool).sum())},
                {"diagnostic": "missing_required_artifacts", "value": int(((manifest["required"].astype(bool)) & (~manifest["exists"].astype(bool))).sum())},
                {"diagnostic": "total_size_bytes", "value": int(pd.to_numeric(manifest["size_bytes"], errors="coerce").fillna(0).sum())},
            ]
        )
        for kind, count in manifest["artifact_kind"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"artifact_kind_{kind}", "value": int(count)})
    if not metadata.empty:
        for col in ["release_version", "freeze_status", "release_gate_status", "final_verdict", "schema_contract_status", "publication_sanitization_status"]:
            rows.append({"diagnostic": col, "value": metadata.iloc[0].get(col, "")})
    return pd.DataFrame(rows)


def render_release_notes(config: FinalArchiveFreezeConfig, metadata: pd.DataFrame, manifest: pd.DataFrame) -> str:
    meta = metadata.iloc[0].to_dict() if not metadata.empty else {}
    missing = manifest[(manifest["required"].astype(bool)) & (~manifest["exists"].astype(bool))] if not manifest.empty else pd.DataFrame()
    lines = [
        "# Final Archive Freeze",
        "",
        f"Release: `{config.release_version}`",
        "",
        f"Title: {config.release_title}",
        "",
        f"Freeze status: **{meta.get('freeze_status', 'BLOCKED')}**",
        "",
        "## Release metadata",
        "",
        "| Field | Value |",
        "|---|---:|",
    ]
    for key in [
        "release_gate_status",
        "final_verdict",
        "schema_contract_status",
        "publication_sanitization_status",
        "live_readiness_status",
        "required_artifacts",
        "required_missing_artifacts",
        "total_frozen_artifacts",
        "publication_package_exists",
        "frozen_at_utc",
    ]:
        lines.append(f"| {key} | {meta.get(key, '')} |")

    lines.extend(
        [
            "",
            "## Frozen artifact classes",
            "",
            "| Kind | Count |",
            "|---|---:|",
        ]
    )
    if not manifest.empty:
        for kind, count in manifest["artifact_kind"].value_counts().sort_index().items():
            lines.append(f"| {kind} | {int(count)} |")

    lines.extend(
        [
            "",
            "## Required artifacts",
            "",
            "| Artifact | Exists | SHA256 |",
            "|---|---:|---|",
        ]
    )
    required = manifest[manifest["required"].astype(bool)] if not manifest.empty else pd.DataFrame()
    for _, row in required.iterrows():
        checksum = str(row.get("sha256", ""))
        checksum_short = checksum[:12] + "…" if checksum else ""
        lines.append(f"| `{row.get('relative_path', '')}` | {row.get('exists', '')} | `{checksum_short}` |")

    lines.extend(["", "## Missing required artifacts", ""])
    if missing.empty:
        lines.append("None.")
    else:
        for _, row in missing.iterrows():
            lines.append(f"- `{row.get('relative_path', '')}`")

    lines.extend(
        [
            "",
            "## Freeze rule",
            "",
            "The archive is `FROZEN` only when the release version is valid, all required artifacts exist, the publication package exists, and the release checklist satisfies the configured gate.",
            "",
            "## Library storage note",
            "",
            "Store the repository ZIP together with this release metadata, the frozen audit manifest, the publication package ZIP, and the reproducibility pack ZIP. These checksums are the canonical integrity references for the frozen archive.",
            "",
        ]
    )
    return "\n".join(lines)


def write_final_archive_outputs(
    manifest: pd.DataFrame,
    metadata: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    config: FinalArchiveFreezeConfig,
) -> None:
    safe_write_table(manifest, parquet_path=config.freeze_manifest_output_table_path, csv_path=config.freeze_manifest_output_csv_path)

    config.release_metadata_output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    metadata.to_csv(config.release_metadata_output_csv_path, index=False)

    config.release_metadata_output_json_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_dict = metadata.iloc[0].to_dict() if not metadata.empty else {}
    config.release_metadata_output_json_path.write_text(json.dumps(metadata_dict, indent=2, sort_keys=True), encoding="utf-8")

    config.release_notes_output_path.parent.mkdir(parents=True, exist_ok=True)
    config.release_notes_output_path.write_text(render_release_notes(config, metadata, manifest), encoding="utf-8")

    config.frozen_audit_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    frozen_payload = {
        "metadata": metadata_dict,
        "artifacts": manifest.to_dict(orient="records"),
    }
    config.frozen_audit_manifest_path.write_text(json.dumps(frozen_payload, indent=2, sort_keys=True), encoding="utf-8")

    config.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(config.diagnostics_path, index=False)


def build_final_archive_freeze(config: FinalArchiveFreezeConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.final_archive_freeze",
        root() / "logs/pipeline/final_archive_freeze.log",
    )
    logger.info("Building final archive freeze for %s", config.release_version)

    manifest = build_freeze_manifest(config)
    metadata = build_release_metadata(config, manifest)
    diagnostics = build_final_archive_diagnostics(manifest, metadata)
    write_final_archive_outputs(manifest, metadata, diagnostics, config=config)

    logger.info("Final archive freeze status: %s", metadata.iloc[0]["freeze_status"])
    return metadata


def default_config(repo_root: Path | None = None, release_version: str = "v0.1.0-freeze") -> FinalArchiveFreezeConfig:
    r = repo_root or root()
    return FinalArchiveFreezeConfig(
        repo_root=r,
        release_version=release_version,
        release_title="FVN Research Archive 001 — Disclosure–Fundamental Mismatch",
        freeze_manifest_output_table_path=r / "data/processed/reports/final_archive_freeze_manifest.parquet",
        freeze_manifest_output_csv_path=r / "data/processed/reports/final_archive_freeze_manifest.csv",
        release_metadata_output_csv_path=r / "data/processed/reports/final_archive_release_metadata.csv",
        release_metadata_output_json_path=r / "outputs/audit/final_archive_release_metadata.json",
        release_notes_output_path=r / "outputs/reports/final_archive_release_notes.md",
        frozen_audit_manifest_path=r / "outputs/audit/final_archive_frozen_manifest.json",
        diagnostics_path=r / "outputs/diagnostics/final_archive_freeze_diagnostics.csv",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build final archive freeze v0.")
    parser.add_argument("--release-version", default="v0.1.0-freeze")
    parser.add_argument("--release-title", default="FVN Research Archive 001 — Disclosure–Fundamental Mismatch")
    parser.add_argument("--freeze-manifest-output-table", default="data/processed/reports/final_archive_freeze_manifest.parquet")
    parser.add_argument("--freeze-manifest-output-csv", default="data/processed/reports/final_archive_freeze_manifest.csv")
    parser.add_argument("--release-metadata-output-csv", default="data/processed/reports/final_archive_release_metadata.csv")
    parser.add_argument("--release-metadata-output-json", default="outputs/audit/final_archive_release_metadata.json")
    parser.add_argument("--release-notes-output-path", default="outputs/reports/final_archive_release_notes.md")
    parser.add_argument("--frozen-audit-manifest-path", default="outputs/audit/final_archive_frozen_manifest.json")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/final_archive_freeze_diagnostics.csv")
    parser.add_argument("--allow-release-gate-warning", action="store_true")
    parser.add_argument("--allow-missing-publication-package", action="store_true")
    args = parser.parse_args()

    r = root()
    config = FinalArchiveFreezeConfig(
        repo_root=r,
        release_version=args.release_version,
        release_title=args.release_title,
        freeze_manifest_output_table_path=r / args.freeze_manifest_output_table,
        freeze_manifest_output_csv_path=r / args.freeze_manifest_output_csv,
        release_metadata_output_csv_path=r / args.release_metadata_output_csv,
        release_metadata_output_json_path=r / args.release_metadata_output_json,
        release_notes_output_path=r / args.release_notes_output_path,
        frozen_audit_manifest_path=r / args.frozen_audit_manifest_path,
        diagnostics_path=r / args.diagnostics_path,
        require_release_gate_pass=not args.allow_release_gate_warning,
        require_publication_package=not args.allow_missing_publication_package,
    )
    build_final_archive_freeze(config)


if __name__ == "__main__":
    main()
