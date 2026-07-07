from pathlib import Path

import pandas as pd

from fvn_dfm.modeling.model_selection_report import (
    ModelSelectionConfig,
    add_selection_ranks,
    build_model_selection_report_dataframe,
    render_markdown_report,
)


def make_diagnostics() -> pd.DataFrame:
    rows = []
    for model, val_ic, val_mae, val_rmse, test_ic, test_mae, test_rmse in [
        ("ridge", 0.10, 0.050, 0.070, 0.08, 0.055, 0.075),
        ("elastic_net", 0.20, 0.045, 0.065, 0.12, 0.050, 0.070),
        ("gradient_boosting", 0.15, 0.060, 0.080, 0.10, 0.070, 0.090),
    ]:
        for fold in ["WF0001_202101", "WF0002_202102"]:
            rows.append(
                {
                    "walk_forward_fold_id": fold,
                    "model_name": model,
                    "walk_forward_role": "validation",
                    "status": "success",
                    "notes": "",
                    "n_rows": 5,
                    "feature_count": 3,
                    "target_column": "y_forward_63d_sector_adjusted_return",
                    "mse": val_rmse ** 2,
                    "rmse": val_rmse,
                    "mae": val_mae,
                    "r2": 0.01,
                    "pearson_corr": val_ic + 0.01,
                    "spearman_corr": val_ic,
                    "mean_y_true": 0.0,
                    "mean_y_pred": 0.0,
                }
            )
            rows.append(
                {
                    "walk_forward_fold_id": fold,
                    "model_name": model,
                    "walk_forward_role": "test",
                    "status": "success",
                    "notes": "",
                    "n_rows": 5,
                    "feature_count": 3,
                    "target_column": "y_forward_63d_sector_adjusted_return",
                    "mse": test_rmse ** 2,
                    "rmse": test_rmse,
                    "mae": test_mae,
                    "r2": 0.01,
                    "pearson_corr": test_ic + 0.01,
                    "spearman_corr": test_ic,
                    "mean_y_true": 0.0,
                    "mean_y_pred": 0.0,
                }
            )
    rows.append({"diagnostic": "input_rows", "value": 100})
    return pd.DataFrame(rows)


def make_predictions() -> pd.DataFrame:
    rows = []
    for model in ["ridge", "elastic_net", "gradient_boosting"]:
        for role in ["train", "validation", "test"]:
            for fold in ["WF0001_202101", "WF0002_202102"]:
                rows.append(
                    {
                        "walk_forward_fold_id": fold,
                        "walk_forward_role": role,
                        "model_name": model,
                        "model_row_id": f"{model}_{role}_{fold}",
                        "y_true": 0.01,
                        "y_pred": 0.02,
                    }
                )
    return pd.DataFrame(rows)


def config(tmp_path: Path) -> ModelSelectionConfig:
    return ModelSelectionConfig(
        baseline_diagnostics_path=tmp_path / "baseline_model_diagnostics.csv",
        baseline_predictions_path=tmp_path / "baseline_fold_predictions.csv",
        output_table_path=tmp_path / "model_selection_report.parquet",
        output_csv_path=tmp_path / "model_selection_report.csv",
        markdown_report_path=tmp_path / "model_selection_report.md",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )


def test_add_selection_ranks_selects_best_validation_ic(tmp_path: Path):
    report = pd.DataFrame(
        [
            {"model_name": "ridge", "validation_mean_spearman_ic": 0.10, "validation_mean_mae": 0.05, "validation_mean_rmse": 0.07, "validation_folds_success": 2},
            {"model_name": "elastic_net", "validation_mean_spearman_ic": 0.20, "validation_mean_mae": 0.06, "validation_mean_rmse": 0.08, "validation_folds_success": 2},
        ]
    )
    ranked = add_selection_ranks(report, config(tmp_path))
    assert ranked.iloc[0]["model_name"] == "elastic_net"
    assert ranked.iloc[0]["is_primary_model"] is True or ranked.iloc[0]["is_primary_model"] == True


def test_build_model_selection_report_dataframe(tmp_path: Path):
    make_diagnostics().to_csv(tmp_path / "baseline_model_diagnostics.csv", index=False)
    make_predictions().to_csv(tmp_path / "baseline_fold_predictions.csv", index=False)

    report, diagnostics = build_model_selection_report_dataframe(config(tmp_path))
    assert len(report) == 3
    assert report.iloc[0]["model_name"] == "elastic_net"
    assert report.iloc[0]["is_primary_model"] is True or report.iloc[0]["is_primary_model"] == True
    assert report.iloc[0]["validation_mean_spearman_ic"] == 0.2
    assert report.iloc[0]["test_mean_spearman_ic"] == 0.12
    assert "primary_model" in set(diagnostics["diagnostic"])


def test_render_markdown_report(tmp_path: Path):
    make_diagnostics().to_csv(tmp_path / "baseline_model_diagnostics.csv", index=False)
    make_predictions().to_csv(tmp_path / "baseline_fold_predictions.csv", index=False)
    report, diagnostics = build_model_selection_report_dataframe(config(tmp_path))
    md = render_markdown_report(report, diagnostics, config(tmp_path))
    assert "# Model Selection Report" in md
    assert "Selected model: `elastic_net`" in md
    assert "| Rank | Model |" in md
