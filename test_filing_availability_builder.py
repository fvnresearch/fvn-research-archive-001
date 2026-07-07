from pathlib import Path

import pandas as pd

from fvn_dfm.modeling.baseline_trainer import BaselineTrainerConfig, train_baseline_models


def test_train_baseline_models_outputs(tmp_path: Path):
    rows = []
    for fold_id in ["WF0001_202101", "WF0002_202102"]:
        for idx in range(30):
            if idx < 20:
                role = "train"
            elif idx < 25:
                role = "validation"
            else:
                role = "test"
            x1 = idx / 10
            x2 = (idx % 4) / 4
            y = 0.3 * x1 - 0.2 * x2
            rows.append(
                {
                    "model_row_id": f"{fold_id}_row_{idx}",
                    "panel_row_id": f"{fold_id}_row_{idx}",
                    "cik": str(1000 + idx),
                    "cik10": str(1000 + idx).zfill(10),
                    "ticker": f"T{idx}",
                    "sector": "Tech",
                    "accession_number": f"000000{idx}",
                    "primary_document": "doc.htm",
                    "feature_asof_date": f"2021-01-{(idx % 28) + 1:02d}",
                    "walk_forward_fold_id": fold_id,
                    "walk_forward_role": role,
                    "model_dataset_eligible": True,
                    "y_forward_63d_sector_adjusted_return": y,
                    "dfm_score_simple": x1,
                    "downside_mismatch_score": x2,
                    "text_full_lm_positive_share": x1 * 0.01,
                    "model_feature_columns": "dfm_score_simple,downside_mismatch_score,text_full_lm_positive_share",
                }
            )
    dataset = pd.DataFrame(rows)
    dataset_path = tmp_path / "model_dataset_with_splits.csv"
    dataset.to_csv(dataset_path, index=False)

    config = BaselineTrainerConfig(
        model_dataset_with_splits_path=dataset_path,
        predictions_output_table_path=tmp_path / "baseline_fold_predictions.parquet",
        predictions_output_csv_path=tmp_path / "baseline_fold_predictions.csv",
        diagnostics_path=tmp_path / "baseline_model_diagnostics.csv",
        model_names=("ridge", "elastic_net", "gradient_boosting"),
        min_train_rows=10,
        min_eval_rows=1,
        random_state=17,
    )
    predictions = train_baseline_models(config)

    assert not predictions.empty
    assert (tmp_path / "baseline_fold_predictions.csv").exists()
    assert (tmp_path / "baseline_model_diagnostics.csv").exists()
    assert set(predictions["model_name"]) == {"ridge", "elastic_net", "gradient_boosting"}
    assert set(predictions["walk_forward_fold_id"]) == {"WF0001_202101", "WF0002_202102"}
    assert {"train", "validation", "test"}.issubset(set(predictions["walk_forward_role"]))
