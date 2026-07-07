from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.reproducibility_pack import (
    ReproducibilityPackConfig,
    build_config_snapshot,
    build_file_manifest,
    build_pipeline_run_order,
    build_report_index,
    render_bundle_index_markdown,
    render_pipeline_run_order_markdown,
)


def make_config(tmp_path: Path) -> ReproducibilityPackConfig:
    return ReproducibilityPackConfig(
        output_dir=tmp_path / "outputs/audit/reproducibility_pack",
        bundle_zip_path=tmp_path / "outputs/audit/reproducibility_pack.zip",
        diagnostics_path=tmp_path / "outputs/diagnostics/reproducibility_pack_diagnostics.csv",
        manifest_output_table_path=tmp_path / "data/processed/reports/reproducibility_file_manifest.parquet",
        manifest_output_csv_path=tmp_path / "data/processed/reports/reproducibility_file_manifest.csv",
    )


def make_repo(tmp_path: Path) -> Path:
    (tmp_path / "configs").mkdir(parents=True)
    (tmp_path / "src/example").mkdir(parents=True)
    (tmp_path / "outputs/reports").mkdir(parents=True)
    (tmp_path / "data/raw").mkdir(parents=True)
    (tmp_path / "configs/00_project.yaml").write_text("project: test\n", encoding="utf-8")
    (tmp_path / "src/example/module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "outputs/reports/final.md").write_text("# Report\n", encoding="utf-8")
    (tmp_path / "data/raw/large.csv").write_text("x\n1\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("pandas\n", encoding="utf-8")
    (tmp_path / "environment.yml").write_text("name: test\n", encoding="utf-8")
    return tmp_path


def test_build_file_manifest_excludes_data_by_default(tmp_path: Path):
    repo = make_repo(tmp_path)
    manifest = build_file_manifest(repo, make_config(tmp_path))
    assert not manifest.empty
    assert "sha256" in manifest.columns
    assert "src/example/module.py" in set(manifest["relative_path"])
    assert "data/raw/large.csv" not in set(manifest["relative_path"])


def test_build_config_snapshot(tmp_path: Path):
    repo = make_repo(tmp_path)
    snapshot = build_config_snapshot(repo)
    assert "configs" in snapshot
    assert "00_project.yaml" in snapshot["configs"]
    assert "requirements_txt" in snapshot


def test_build_report_index(tmp_path: Path):
    repo = make_repo(tmp_path)
    manifest = build_file_manifest(repo, make_config(tmp_path))
    report_index = build_report_index(repo, manifest)
    assert len(report_index) == 1
    assert report_index.iloc[0]["report_path"] == "outputs/reports/final.md"


def test_pipeline_markdown_and_bundle_index(tmp_path: Path):
    repo = make_repo(tmp_path)
    cfg = make_config(tmp_path)
    manifest = build_file_manifest(repo, cfg)
    report_index = build_report_index(repo, manifest)
    pipeline = build_pipeline_run_order()
    md = render_pipeline_run_order_markdown(pipeline)
    index_md = render_bundle_index_markdown(manifest, report_index, pipeline, cfg)
    assert "# Pipeline Run Order" in md
    assert "build-final-verdict" in md
    assert "# Reproducibility Pack" in index_md
    assert "file_manifest.csv" in index_md
