from pathlib import Path

import pandas as pd

from fvn_dfm.modeling.model_selection_report import ModelSelectionConfig, build_model_selection_report


def test_build_model_selection_report_outputs(tmp_path: Path):
    diagnostics_rows = []
    specs = [
        ("ridge", 0.05, 0.060, 0.080, 0.03),
        ("elastic_net", 0.12, 0.050, 0.070, 0.08),
        ("gradient_boosting", 0.09, 0.055, 0.075, 0.10),
    ]
    for model, val_ic, val_mae, val_rmse, test_ic in specs:
        for fold in ["WF0001_202101", "WF0002_202102"]:
            diagnostics_rows.append(
                {
                    "walk_forward_fold_id": fold,
                    "model_name": model,
                    "walk_forward_role": "validation",
                    "status": "success",
                    "notes": "",
                    "n_rows": 10,
                    "feature_count": 4,
                    "target_column": "y_forward_63d_sector_adjusted_return",
                    "mse": val_rmse ** 2,
                    "rmse": val_rmse,
                    "mae": val_mae,
                    "r2": 0.01,
                    "pearson_corr": val_ic,
                    "spearman_corr": val_ic,
                    "mean_y_true": 0.0,
                    "mean_y_pred": 0.0,
                }
            )
            diagnostics_rows.append(
                {
                    "walk_forward_fold_id": fold,
                    "model_name": model,
                    "walk_forward_role": "test",
                    "status": "success",
                    "notes": "",
                    "n_rows": 10,
                    "feature_count": 4,
                    "target_column": "y_forward_63d_sector_adjusted_return",
                    "mse": 0.01,
                    "rmse": 0.1,
                    "mae": 0.07,
                    "r2": 0.01,
                    "pearson_corr": test_ic,
                    "spearman_corr": test_ic,
                    "mean_y_true": 0.0,
                    "mean_y_pred": 0.0,
                }
            )
    diagnostics = pd.DataFrame(diagnostics_rows)
    predictions = pd.DataFrame(
        [
            {
                "walk_forward_fold_id": "WF0001_202101",
                "walk_forward_role": "validation",
                "model_name": "elastic_net",
                "model_row_id": "row_1",
                "y_true": 0.01,
                "y_pred": 0.02,
            }
        ]
    )

    diag_path = tmp_path / "baseline_model_diagnostics.csv"
    pred_path = tmp_path / "baseline_fold_predictions.csv"
    diagnostics.to_csv(diag_path, index=False)
    predictions.to_csv(pred_path, index=False)

    config = ModelSelectionConfig(
        baseline_diagnostics_path=diag_path,
        baseline_predictions_path=pred_path,
        output_table_path=tmp_path / "model_selection_report.parquet",
        output_csv_path=tmp_path / "model_selection_report.csv",
        markdown_report_path=tmp_path / "model_selection_report.md",
        diagnostics_path=tmp_path / "model_selection_report_diagnostics.csv",
    )
    report = build_model_selection_report(config)

    assert len(report) == 3
    assert (tmp_path / "model_selection_report.csv").exists()
    assert (tmp_path / "model_selection_report.md").exists()
    assert (tmp_path / "model_selection_report_diagnostics.csv").exists()
    assert report.iloc[0]["model_name"] == "elastic_net"
    assert report.iloc[0]["is_primary_model"] is True or report.iloc[0]["is_primary_model"] == True
