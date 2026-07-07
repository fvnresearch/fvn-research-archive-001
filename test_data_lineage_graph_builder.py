from pathlib import Path

import pandas as pd

from fvn_dfm.modeling.ablation_study import AblationStudyConfig, build_ablation_study


def test_build_ablation_study_outputs(tmp_path: Path):
    rows = []
    for fold in ["WF0001_202101", "WF0002_202102"]:
        for month in ["2021-01", "2021-02"]:
            for i in range(20):
                dfm = i / 100
                fund = (20 - i) / 100
                text = i / 200
                y = dfm * 0.4 - 0.01
                rows.append(
                    {
                        "model_row_id": f"{fold}_{month}_{i}",
                        "panel_row_id": f"{fold}_{month}_{i}",
                        "cik": str(1000 + i),
                        "cik10": str(1000 + i).zfill(10),
                        "ticker": f"T{i}",
                        "sector": "Tech",
                        "accession_number": f"acc_{fold}_{month}_{i}",
                        "primary_document": "doc.htm",
                        "feature_asof_date": f"{month}-15",
                        "walk_forward_fold_id": fold,
                        "walk_forward_role": "test",
                        "model_dataset_eligible": True,
                        "y_forward_63d_sector_adjusted_return": y,
                        "dfm_score_simple": dfm,
                        "fundamental_reality_score": fund,
                        "text_full_lm_pos_neg_balance": text,
                    }
                )
    source = pd.DataFrame(rows)
    source_path = tmp_path / "model_dataset_with_splits.csv"
    source.to_csv(source_path, index=False)

    config = AblationStudyConfig(
        model_dataset_with_splits_path=source_path,
        predictions_output_table_path=tmp_path / "ablation_predictions.parquet",
        predictions_output_csv_path=tmp_path / "ablation_predictions.csv",
        metrics_output_table_path=tmp_path / "ablation_metrics.parquet",
        metrics_output_csv_path=tmp_path / "ablation_metrics.csv",
        portfolio_returns_output_table_path=tmp_path / "ablation_portfolio_returns.parquet",
        portfolio_returns_output_csv_path=tmp_path / "ablation_portfolio_returns.csv",
        summary_output_table_path=tmp_path / "ablation_summary.parquet",
        summary_output_csv_path=tmp_path / "ablation_summary.csv",
        markdown_report_path=tmp_path / "ablation_study_report.md",
        diagnostics_path=tmp_path / "ablation_study_diagnostics.csv",
        min_names_per_rebalance=10,
    )
    summary = build_ablation_study(config)

    assert not summary.empty
    assert (tmp_path / "ablation_predictions.csv").exists()
    assert (tmp_path / "ablation_metrics.csv").exists()
    assert (tmp_path / "ablation_portfolio_returns.csv").exists()
    assert (tmp_path / "ablation_summary.csv").exists()
    assert (tmp_path / "ablation_study_report.md").exists()
    assert (tmp_path / "ablation_study_diagnostics.csv").exists()
    assert set(summary["ablation_name"]) == {"dfm_score", "fundamentals_only", "text_only", "naive_baseline"}
