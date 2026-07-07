from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.publication_package import (
    PublicationPackageConfig,
    _is_forbidden_path,
    build_publication_manifest,
    build_sanitization_checks,
    render_publication_readme,
)


def config(tmp_path: Path) -> PublicationPackageConfig:
    return PublicationPackageConfig(
        package_dir=tmp_path / "outputs/publication/publication_package_v0",
        package_zip_path=tmp_path / "outputs/publication/publication_package_v0.zip",
        manifest_output_table_path=tmp_path / "data/processed/reports/publication_manifest.parquet",
        manifest_output_csv_path=tmp_path / "data/processed/reports/publication_manifest.csv",
        exclusions_output_csv_path=tmp_path / "data/processed/reports/publication_exclusions.csv",
        sanitization_output_csv_path=tmp_path / "data/processed/reports/publication_sanitization_checks.csv",
        diagnostics_path=tmp_path / "outputs/diagnostics/publication_package_diagnostics.csv",
    )


def make_repo_files(tmp_path: Path):
    (tmp_path / "outputs/reports").mkdir(parents=True)
    (tmp_path / "data/processed/reports").mkdir(parents=True)
    (tmp_path / "outputs/audit/reproducibility_pack").mkdir(parents=True)
    (tmp_path / "data/raw").mkdir(parents=True)

    (tmp_path / "README.md").write_text("# README\n", encoding="utf-8")
    (tmp_path / "RESEARCH_PROTOCOL.md").write_text("# Protocol\n", encoding="utf-8")
    (tmp_path / "FINAL_VERDICT.md").write_text("# Verdict\n", encoding="utf-8")
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n", encoding="utf-8")
    (tmp_path / "LICENSE").write_text("MIT\n", encoding="utf-8")

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
    (tmp_path / "data/raw/private.csv").write_text("secret\n", encoding="utf-8")


def test_forbidden_path_rules():
    assert _is_forbidden_path("data/raw/private.csv")[0]
    assert _is_forbidden_path("outputs/logs/run.csv")[0]
    assert _is_forbidden_path("outputs/reports/final_research_verdict.md")[0] is False


def test_build_publication_manifest(monkeypatch, tmp_path: Path):
    make_repo_files(tmp_path)
    import fvn_dfm.reporting.publication_package as module
    monkeypatch.setattr(module, "root", lambda: tmp_path)

    cfg = config(tmp_path)
    cfg.package_dir.mkdir(parents=True)
    manifest, exclusions = build_publication_manifest(cfg)

    assert not manifest.empty
    assert "README.md" in set(manifest["relative_path"])
    assert not any(str(p).startswith("data/raw/") for p in manifest["package_path"])
    assert "outputs/reports/final_research_verdict.md" in set(manifest["relative_path"])


def test_sanitization_checks(monkeypatch, tmp_path: Path):
    make_repo_files(tmp_path)
    import fvn_dfm.reporting.publication_package as module
    monkeypatch.setattr(module, "root", lambda: tmp_path)

    cfg = config(tmp_path)
    cfg.package_dir.mkdir(parents=True)
    manifest, exclusions = build_publication_manifest(cfg)
    (cfg.package_dir / "PUBLICATION_README.md").write_text("public\n", encoding="utf-8")
    checks = build_sanitization_checks(cfg, manifest)

    assert not checks.empty
    assert checks["status"].eq("PASS").all()


def test_render_publication_readme(monkeypatch, tmp_path: Path):
    make_repo_files(tmp_path)
    import fvn_dfm.reporting.publication_package as module
    monkeypatch.setattr(module, "root", lambda: tmp_path)

    cfg = config(tmp_path)
    cfg.package_dir.mkdir(parents=True)
    manifest, exclusions = build_publication_manifest(cfg)
    md = render_publication_readme(manifest, exclusions, cfg)
    assert "# FVN Research Archive 001" in md
    assert "Excluded by design" in md
    assert "publication_manifest.csv" in md
