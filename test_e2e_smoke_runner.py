from pathlib import Path

import pandas as pd

from fvn_dfm.modeling.baseline_trainer import (
    BaselineTrainerConfig,
    build_baseline_predictions_and_diagnostics,
    make_model,
    parse_feature_columns,
    parse_model_names,
)


def make_split_dataset() -> pd.DataFrame:
    rows = []
    for idx in range(36):
        if idx < 24:
            role = "train"
        elif idx < 30:
            role = "validation"
        else:
            role = "test"
        x1 = idx / 10
        x2 = (idx % 5) / 5
        y = 0.2 * x1 - 0.1 * x2
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
                "feature_asof_date": f"2021-01-{(idx % 28) + 1:02d}",
                "walk_forward_fold_id": "WF0001_202101",
                "walk_forward_role": role,
                "model_dataset_eligible": True,
                "y_forward_63d_sector_adjusted_return": y,
                "dfm_score_simple": x1,
                "downside_mismatch_score": x2,
                "model_feature_columns": "dfm_score_simple,downside_mismatch_score",
            }
        )
    return pd.DataFrame(rows)


def config(tmp_path: Path, *, models=("ridge",), min_train_rows=10) -> BaselineTrainerConfig:
    return BaselineTrainerConfig(
        model_dataset_with_splits_path=tmp_path / "model_dataset_with_splits.csv",
        predictions_output_table_path=tmp_path / "baseline_fold_predictions.parquet",
        predictions_output_csv_path=tmp_path / "baseline_fold_predictions.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
        model_names=models,
        min_train_rows=min_train_rows,
    )


def test_parse_model_names():
    assert parse_model_names("ridge,elastic_net") == ("ridge", "elastic_net")


def test_make_model_known_names():
    for name in ["ridge", "elastic_net", "gradient_boosting"]:
        model = make_model(name, random_state=17)
        assert model is not None


def test_parse_feature_columns():
    df = make_split_dataset()
    features = parse_feature_columns(df)
    assert features == ["dfm_score_simple", "downside_mismatch_score"]


def test_build_baseline_predictions_and_diagnostics(tmp_path: Path):
    df = make_split_dataset()
    df.to_csv(tmp_path / "model_dataset_with_splits.csv", index=False)

    predictions, diagnostics = build_baseline_predictions_and_diagnostics(config(tmp_path, models=("ridge",), min_train_rows=10))
    assert not predictions.empty
    assert set(predictions["walk_forward_role"]) == {"train", "validation", "test"}
    assert set(predictions["model_name"]) == {"ridge"}
    assert "y_pred" in predictions.columns
    assert "prediction_error" in predictions.columns
    assert "input_rows" in set(diagnostics["diagnostic"].dropna())
    assert "success" in set(diagnostics["status"].dropna())


def test_insufficient_train_rows_skips(tmp_path: Path):
    df = make_split_dataset()
    df.to_csv(tmp_path / "model_dataset_with_splits.csv", index=False)

    predictions, diagnostics = build_baseline_predictions_and_diagnostics(config(tmp_path, models=("ridge",), min_train_rows=100))
    assert predictions.empty
    assert "skipped" in set(diagnostics["status"].dropna())
    assert any("insufficient_train_rows" in str(x) for x in diagnostics["notes"].dropna())
