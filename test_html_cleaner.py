from pathlib import Path
import json

import pandas as pd

from fvn_dfm.reporting.final_archive_freeze import (
    FinalArchiveFreezeConfig,
    _valid_release_version,
    build_final_archive_diagnostics,
    build_freeze_manifest,
    build_release_metadata,
    render_release_notes,
)


def config(tmp_path: Path, *, version: str = "v1.0.0") -> FinalArchiveFreezeConfig:
    return FinalArchiveFreezeConfig(
        repo_root=tmp_path,
        release_version=version,
        release_title="Test Release",
        freeze_manifest_output_table_path=tmp_path / "data/processed/reports/final_archive_freeze_manifest.parquet",
        freeze_manifest_output_csv_path=tmp_path / "data/processed/reports/final_archive_freeze_manifest.csv",
        release_metadata_output_csv_path=tmp_path / "data/processed/reports/final_archive_release_metadata.csv",
        release_metadata_output_json_path=tmp_path / "outputs/audit/final_archive_release_metadata.json",
        release_notes_output_path=tmp_path / "outputs/reports/final_archive_release_notes.md",
        frozen_audit_manifest_path=tmp_path / "outputs/audit/final_archive_frozen_manifest.json",
        diagnostics_path=tmp_path / "outputs/diagnostics/final_archive_freeze_diagnostics.csv",
    )


def make_required_artifacts(tmp_path: Path, *, release_gate: str = "PASS"):
    files = [
        "README.md",
        "RESEARCH_PROTOCOL.md",
        "RESEARCH_LOG.md",
        "FINAL_VERDICT.md",
        "CHANGELOG.md",
        "LICENSE",
        "data/processed/reports/final_research_verdict.csv",
        "data/processed/reports/final_research_evidence.csv",
        "data/processed/reports/final_research_criteria.csv",
        "data/processed/reports/release_checklist.csv",
        "data/processed/reports/release_gate_summary.csv",
        "data/processed/reports/schema_contract_summary.csv",
        "data/processed/reports/schema_contract_registry.csv",
        "data/processed/reports/data_lineage_nodes.csv",
        "data/processed/reports/data_lineage_edges.csv",
        "data/processed/reports/publication_manifest.csv",
        "data/processed/reports/publication_sanitization_checks.csv",
        "data/processed/reports/reproducibility_file_manifest.csv",
        "outputs/publication/publication_package_v0/PUBLICATION_README.md",
        "outputs/publication/publication_package_v0.zip",
        "outputs/reports/final_research_verdict.md",
        "outputs/reports/release_checklist.md",
        "outputs/reports/data_lineage_map.md",
        "outputs/reports/schema_contract_validation_report.md",
        "outputs/audit/reproducibility_pack.zip",
    ]
    for rel in files:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if rel.endswith("final_research_verdict.csv"):
            pd.DataFrame([{"final_verdict": "PASS"}]).to_csv(path, index=False)
        elif rel.endswith("release_gate_summary.csv"):
            pd.DataFrame([{"release_gate_status": release_gate}]).to_csv(path, index=False)
        elif rel.endswith("schema_contract_summary.csv"):
            pd.DataFrame([{"schema_contract_status": "PASS"}]).to_csv(path, index=False)
        elif rel.endswith("publication_sanitization_checks.csv"):
            pd.DataFrame([{"status": "PASS"}]).to_csv(path, index=False)
        elif rel.endswith(".csv"):
            pd.DataFrame([{"x": 1}]).to_csv(path, index=False)
        else:
            path.write_text(f"{rel}\n", encoding="utf-8")


def test_valid_release_version():
    assert _valid_release_version("v1.0.0")
    assert _valid_release_version("archive-001+freeze")
    assert not _valid_release_version("")
    assert not _valid_release_version("bad version with spaces")


def test_build_freeze_manifest_has_checksums(tmp_path: Path):
    make_required_artifacts(tmp_path)
    manifest = build_freeze_manifest(config(tmp_path))
    required = manifest[manifest["required"].astype(bool)]
    assert not manifest.empty
    assert required["exists"].all()
    assert required["sha256"].astype(str).str.len().min() == 64


def test_build_release_metadata_frozen(tmp_path: Path):
    make_required_artifacts(tmp_path)
    cfg = config(tmp_path)
    manifest = build_freeze_manifest(cfg)
    metadata = build_release_metadata(cfg, manifest)
    assert metadata.iloc[0]["freeze_status"] == "FROZEN"
    assert metadata.iloc[0]["release_gate_status"] == "PASS"
    assert metadata.iloc[0]["final_verdict"] == "PASS"


def test_build_release_metadata_blocks_on_missing_required(tmp_path: Path):
    make_required_artifacts(tmp_path)
    (tmp_path / "outputs/publication/publication_package_v0.zip").unlink()
    cfg = config(tmp_path)
    manifest = build_freeze_manifest(cfg)
    metadata = build_release_metadata(cfg, manifest)
    assert metadata.iloc[0]["freeze_status"] == "BLOCKED"
    assert metadata.iloc[0]["required_missing_artifacts"] >= 1


def test_render_release_notes(tmp_path: Path):
    make_required_artifacts(tmp_path)
    cfg = config(tmp_path)
    manifest = build_freeze_manifest(cfg)
    metadata = build_release_metadata(cfg, manifest)
    notes = render_release_notes(cfg, metadata, manifest)
    assert "# Final Archive Freeze" in notes
    assert "Freeze status: **FROZEN**" in notes
    assert "Library storage note" in notes


def test_build_diagnostics(tmp_path: Path):
    make_required_artifacts(tmp_path)
    cfg = config(tmp_path)
    manifest = build_freeze_manifest(cfg)
    metadata = build_release_metadata(cfg, manifest)
    diagnostics = build_final_archive_diagnostics(manifest, metadata)
    assert "manifest_rows" in set(diagnostics["diagnostic"])
    assert "freeze_status" in set(diagnostics["diagnostic"])
