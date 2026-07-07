from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.publication_package import PublicationPackageConfig, build_publication_package


def make_repo_files(tmp_path: Path):
    (tmp_path / "outputs/reports").mkdir(parents=True)
    (tmp_path / "data/processed/reports").mkdir(parents=True)
    (tmp_path / "outputs/audit/reproducibility_pack").mkdir(parents=True)

    for name in ["README.md", "RESEARCH_PROTOCOL.md", "FINAL_VERDICT.md", "CHANGELOG.md", "LICENSE"]:
        (tmp_path / name).write_text(f"# {name}\n", encoding="utf-8")

    for name in [
        "final_research_verdict.md",
        "portfolio_performance_report.md",
        "model_selection_report.md",
        "ablation_study_report.md",
        "data_lineage_map.md",
        "schema_contract_validation_report.md",
        "release_checklist.md",
    ]:
        (tmp_path / "outputs/reports" / name).write_text(f"# {name}\n", encoding="utf-8")

    for name in [
        "final_research_verdict.csv",
        "final_research_evidence.csv",
        "final_research_criteria.csv",
        "release_checklist.csv",
        "release_gate_summary.csv",
        "schema_contract_summary.csv",
        "schema_contract_registry.csv",
        "data_lineage_nodes.csv",
        "data_lineage_edges.csv",
        "reproducibility_file_manifest.csv",
    ]:
        pd.DataFrame([{"x": 1}]).to_csv(tmp_path / "data/processed/reports" / name, index=False)

    (tmp_path / "outputs/audit/reproducibility_pack/README.md").write_text("# Repro\n", encoding="utf-8")
    for name in ["report_index.csv", "pipeline_run_order.csv", "reproducibility_pack_diagnostics.csv"]:
        pd.DataFrame([{"x": 1}]).to_csv(tmp_path / "outputs/audit/reproducibility_pack" / name, index=False)
    (tmp_path / "outputs/audit/reproducibility_pack/pipeline_run_order.md").write_text("# Run order\n", encoding="utf-8")


def test_build_publication_package_outputs(monkeypatch, tmp_path: Path):
    make_repo_files(tmp_path)
    import fvn_dfm.reporting.publication_package as module
    monkeypatch.setattr(module, "root", lambda: tmp_path)

    cfg = PublicationPackageConfig(
        package_dir=tmp_path / "outputs/publication/publication_package_v0",
        package_zip_path=tmp_path / "outputs/publication/publication_package_v0.zip",
        manifest_output_table_path=tmp_path / "data/processed/reports/publication_manifest.parquet",
        manifest_output_csv_path=tmp_path / "data/processed/reports/publication_manifest.csv",
        exclusions_output_csv_path=tmp_path / "data/processed/reports/publication_exclusions.csv",
        sanitization_output_csv_path=tmp_path / "data/processed/reports/publication_sanitization_checks.csv",
        diagnostics_path=tmp_path / "outputs/diagnostics/publication_package_diagnostics.csv",
    )
    manifest = build_publication_package(cfg)

    assert not manifest.empty
    assert cfg.package_zip_path.exists()
    assert (cfg.package_dir / "PUBLICATION_README.md").exists()
    assert (cfg.package_dir / "publication_manifest.csv").exists()
    assert (cfg.package_dir / "publication_exclusions.csv").exists()
    assert (cfg.package_dir / "publication_sanitization_checks.csv").exists()
    assert cfg.manifest_output_csv_path.exists()
    assert cfg.exclusions_output_csv_path.exists()
    assert cfg.sanitization_output_csv_path.exists()
    assert cfg.diagnostics_path.exists()

    included = pd.read_csv(cfg.manifest_output_csv_path)
    assert not any(str(p).startswith("data/raw/") for p in included["package_path"])
