from pathlib import Path

from fvn_dfm.reporting.reproducibility_pack import ReproducibilityPackConfig, build_reproducibility_pack


def test_build_reproducibility_pack_outputs(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "configs").mkdir()
    (repo / "src").mkdir()
    (repo / "outputs/reports").mkdir(parents=True)
    (repo / "data/processed/reports").mkdir(parents=True)
    (repo / "configs/00_project.yaml").write_text("project: test\n", encoding="utf-8")
    (repo / "src/module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "outputs/reports/report.md").write_text("# Report\n", encoding="utf-8")
    (repo / "data/processed/reports/final_research_verdict.csv").write_text("final_verdict\nPASS\n", encoding="utf-8")
    (repo / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (repo / "requirements.txt").write_text("pandas\n", encoding="utf-8")
    (repo / "environment.yml").write_text("name: test\n", encoding="utf-8")

    import fvn_dfm.reporting.reproducibility_pack as module
    monkeypatch.setattr(module, "root", lambda: repo)

    cfg = ReproducibilityPackConfig(
        output_dir=repo / "outputs/audit/reproducibility_pack",
        bundle_zip_path=repo / "outputs/audit/reproducibility_pack.zip",
        diagnostics_path=repo / "outputs/diagnostics/reproducibility_pack_diagnostics.csv",
        manifest_output_table_path=repo / "data/processed/reports/reproducibility_file_manifest.parquet",
        manifest_output_csv_path=repo / "data/processed/reports/reproducibility_file_manifest.csv",
    )

    manifest = build_reproducibility_pack(cfg)

    assert not manifest.empty
    assert (repo / "outputs/audit/reproducibility_pack/file_manifest.csv").exists()
    assert (repo / "outputs/audit/reproducibility_pack/file_checksums.csv").exists()
    assert (repo / "outputs/audit/reproducibility_pack/config_snapshot.json").exists()
    assert (repo / "outputs/audit/reproducibility_pack/report_index.csv").exists()
    assert (repo / "outputs/audit/reproducibility_pack/pipeline_run_order.csv").exists()
    assert (repo / "outputs/audit/reproducibility_pack/pipeline_run_order.md").exists()
    assert (repo / "outputs/audit/reproducibility_pack/README.md").exists()
    assert (repo / "outputs/audit/reproducibility_pack.zip").exists()
    assert (repo / "outputs/diagnostics/reproducibility_pack_diagnostics.csv").exists()
    assert (repo / "data/processed/reports/reproducibility_file_manifest.csv").exists()
