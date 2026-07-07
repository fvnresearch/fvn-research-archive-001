from pathlib import Path

import pandas as pd

from fvn_dfm.testing.e2e_smoke_runner import (
    EndToEndSmokeConfig,
    SmokeArtifact,
    _artifact_check,
    generate_synthetic_fixture,
    render_smoke_report,
)


def test_generate_synthetic_fixture(tmp_path: Path):
    cfg = EndToEndSmokeConfig(
        work_dir=tmp_path / "smoke",
        smoke_zip_path=tmp_path / "smoke.zip",
        n_securities=6,
        n_months=12,
        min_names_per_rebalance=4,
        max_folds=2,
    )
    paths = generate_synthetic_fixture(cfg)
    assert paths["fundamental_composite"].exists()
    assert paths["text_features"].exists()
    assert paths["raw_prices"].exists()

    fund = pd.read_csv(paths["fundamental_composite"])
    text = pd.read_csv(paths["text_features"])
    prices = pd.read_csv(paths["raw_prices"])
    assert len(fund) == 72
    assert len(text) == 72
    assert not prices.empty
    assert "dfm_score_simple" not in fund.columns  # built later by mismatch layer


def test_artifact_check(tmp_path: Path):
    path = tmp_path / "artifact.csv"
    pd.DataFrame([{"x": 1}, {"x": 2}]).to_csv(path, index=False)
    row = _artifact_check(SmokeArtifact("artifact", path, min_rows=2))
    assert row["exists"] is True
    assert row["rows_or_units"] == 2
    assert row["passed"] is True


def test_render_smoke_report():
    steps = pd.DataFrame(
        [{"step_order": 1, "step_name": "example", "status": "success", "elapsed_seconds": 0.1}]
    )
    artifacts = pd.DataFrame(
        [{"step_order": 1, "artifact_name": "file", "exists": True, "rows_or_units": 1, "passed": True}]
    )
    md = render_smoke_report(steps, artifacts, {"status": "PASS", "steps": 1})
    assert "# End-to-End Smoke Pipeline Report" in md
    assert "example" in md
    assert "file" in md
