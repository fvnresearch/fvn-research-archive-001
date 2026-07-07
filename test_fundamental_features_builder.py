from pathlib import Path
import json

import pandas as pd

from fvn_dfm.reporting.final_archive_freeze import FinalArchiveFreezeConfig, build_final_archive_freeze


def make_required_artifacts(tmp_path: Path):
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
            pd.DataFrame([{"release_gate_status": "PASS"}]).to_csv(path, index=False)
        elif rel.endswith("schema_contract_summary.csv"):
            pd.DataFrame([{"schema_contract_status": "PASS"}]).to_csv(path, index=False)
        elif rel.endswith("publication_sanitization_checks.csv"):
            pd.DataFrame([{"status": "PASS"}]).to_csv(path, index=False)
        elif rel.endswith(".csv"):
            pd.DataFrame([{"x": 1}]).to_csv(path, index=False)
        else:
            path.write_text(f"{rel}\n", encoding="utf-8")


def test_build_final_archive_freeze_outputs(tmp_path: Path):
    make_required_artifacts(tmp_path)
    cfg = FinalArchiveFreezeConfig(
        repo_root=tmp_path,
        release_version="v1.0.0",
        release_title="Test Release",
        freeze_manifest_output_table_path=tmp_path / "data/processed/reports/final_archive_freeze_manifest.parquet",
        freeze_manifest_output_csv_path=tmp_path / "data/processed/reports/final_archive_freeze_manifest.csv",
        release_metadata_output_csv_path=tmp_path / "data/processed/reports/final_archive_release_metadata.csv",
        release_metadata_output_json_path=tmp_path / "outputs/audit/final_archive_release_metadata.json",
        release_notes_output_path=tmp_path / "outputs/reports/final_archive_release_notes.md",
        frozen_audit_manifest_path=tmp_path / "outputs/audit/final_archive_frozen_manifest.json",
        diagnostics_path=tmp_path / "outputs/diagnostics/final_archive_freeze_diagnostics.csv",
    )

    metadata = build_final_archive_freeze(cfg)

    assert metadata.iloc[0]["freeze_status"] == "FROZEN"
    assert cfg.freeze_manifest_output_csv_path.exists()
    assert cfg.release_metadata_output_csv_path.exists()
    assert cfg.release_metadata_output_json_path.exists()
    assert cfg.release_notes_output_path.exists()
    assert cfg.frozen_audit_manifest_path.exists()
    assert cfg.diagnostics_path.exists()

    payload = json.loads(cfg.frozen_audit_manifest_path.read_text(encoding="utf-8"))
    assert payload["metadata"]["release_version"] == "v1.0.0"
    assert len(payload["artifacts"]) >= 20
