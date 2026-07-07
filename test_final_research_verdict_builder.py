from pathlib import Path

import pandas as pd

from fvn_dfm.testing.e2e_smoke_runner import EndToEndSmokeConfig, build_end_to_end_smoke


def test_build_end_to_end_smoke_outputs(tmp_path: Path):
    cfg = EndToEndSmokeConfig(
        work_dir=tmp_path / "e2e_smoke",
        smoke_zip_path=tmp_path / "e2e_smoke.zip",
        n_securities=12,
        n_months=30,
        min_names_per_rebalance=6,
        max_folds=3,
        clean=True,
    )
    summary = build_end_to_end_smoke(cfg)

    assert summary.iloc[0]["status"] == "PASS"
    assert (tmp_path / "e2e_smoke.zip").exists()
    assert (cfg.work_dir / "outputs/smoke/smoke_pipeline_steps.csv").exists()
    assert (cfg.work_dir / "outputs/smoke/smoke_artifact_checks.csv").exists()
    assert (cfg.work_dir / "outputs/smoke/smoke_pipeline_report.md").exists()
    assert (cfg.work_dir / "data/processed/reports/final_research_verdict.csv").exists()
    assert (cfg.work_dir / "outputs/audit/reproducibility_pack.zip").exists()

    steps = pd.read_csv(cfg.work_dir / "outputs/smoke/smoke_pipeline_steps.csv")
    artifacts = pd.read_csv(cfg.work_dir / "outputs/smoke/smoke_artifact_checks.csv")
    assert len(steps) == 14
    assert steps["status"].eq("success").all()
    assert artifacts["passed"].astype(bool).all()
