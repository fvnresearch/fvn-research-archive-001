from pathlib import Path

import pandas as pd

from fvn_dfm.modeling.walk_forward_splits import WalkForwardSplitConfig, build_model_dataset_with_splits


def test_build_model_dataset_with_splits_outputs(tmp_path: Path):
    rows = []
    for idx, asof in enumerate(pd.date_range("2019-01-31", "2021-12-31", freq="M")):
        rows.append(
            {
                "model_row_id": f"row_{idx}",
                "panel_row_id": f"row_{idx}",
                "cik": str(1000 + idx),
                "cik10": str(1000 + idx).zfill(10),
                "ticker": f"T{idx}",
                "sector": "Tech",
                "accession_number": f"000000{idx}",
                "primary_document": "doc.htm",
                "accession_lineage_key": f"{str(1000 + idx).zfill(10)}:000000{idx}:doc.htm",
                "feature_asof_date": asof.date().isoformat(),
                "model_dataset_eligible": True,
                "y_forward_63d_sector_adjusted_return": 0.01,
                "dfm_score_simple": idx / 100,
            }
        )
    source = pd.DataFrame(rows)
    source_path = tmp_path / "model_dataset_v0.csv"
    source.to_csv(source_path, index=False)

    config = WalkForwardSplitConfig(
        model_dataset_path=source_path,
        output_table_path=tmp_path / "model_dataset_with_splits.parquet",
        output_csv_path=tmp_path / "model_dataset_with_splits.csv",
        diagnostics_path=tmp_path / "model_dataset_with_splits_diagnostics.csv",
        min_train_months=12,
        validation_months=6,
        test_months=1,
        step_months=3,
        embargo_days=14,
        first_test_month="2020-10-01",
        max_folds=3,
    )
    out = build_model_dataset_with_splits(config)

    assert not out.empty
    assert (tmp_path / "model_dataset_with_splits.csv").exists()
    assert (tmp_path / "model_dataset_with_splits_diagnostics.csv").exists()
    assert out["walk_forward_fold_id"].nunique() <= 3
    assert {"train", "validation", "test"}.issubset(set(out["walk_forward_role"]))
