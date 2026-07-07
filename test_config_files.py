from pathlib import Path

import pandas as pd

from fvn_dfm.modeling.ablation_study import (
    AblationStudyConfig,
    build_ablation_metrics_dataframe,
    build_ablation_portfolio_returns_dataframe,
    build_ablation_predictions_dataframe,
    build_ablation_summary_dataframe,
    render_markdown_report,
)


def make_dataset() -> pd.DataFrame:
    rows = []
    for fold in ["WF0001_202101", "WF0002_202102"]:
        for month in ["2021-01", "2021-02"]:
            for i in range(20):
                dfm = i / 100
                fund = (20 - i) / 100
                text = i / 200
                y = dfm * 0.5 - 0.02
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
    return pd.DataFrame(rows)


def config(tmp_path: Path) -> AblationStudyConfig:
    return AblationStudyConfig(
        model_dataset_with_splits_path=tmp_path / "model_dataset_with_splits.csv",
        predictions_output_table_path=tmp_path / "ablation_predictions.parquet",
        predictions_output_csv_path=tmp_path / "ablation_predictions.csv",
        metrics_output_table_path=tmp_path / "ablation_metrics.parquet",
        metrics_output_csv_path=tmp_path / "ablation_metrics.csv",
        portfolio_returns_output_table_path=tmp_path / "ablation_portfolio_returns.parquet",
        portfolio_returns_output_csv_path=tmp_path / "ablation_portfolio_returns.csv",
        summary_output_table_path=tmp_path / "ablation_summary.parquet",
        summary_output_csv_path=tmp_path / "ablation_summary.csv",
        markdown_report_path=tmp_path / "ablation_study_report.md",
        diagnostics_path=tmp_path / "diagnostics.csv",
        min_names_per_rebalance=10,
    )


def test_build_ablation_predictions_dataframe(tmp_path: Path):
    make_dataset().to_csv(tmp_path / "model_dataset_with_splits.csv", index=False)
    predictions = build_ablation_predictions_dataframe(config(tmp_path))
    assert set(predictions["ablation_name"]) == {"dfm_score", "fundamentals_only", "text_only", "naive_baseline"}
    assert len(predictions) == len(make_dataset()) * 4
    dfm = predictions[predictions["ablation_name"] == "dfm_score"].iloc[0]
    assert dfm["ablation_source_column"] == "dfm_score_simple"


def test_build_ablation_metrics_dataframe(tmp_path: Path):
    make_dataset().to_csv(tmp_path / "model_dataset_with_splits.csv", index=False)
    predictions = build_ablation_predictions_dataframe(config(tmp_path))
    metrics = build_ablation_metrics_dataframe(predictions, config(tmp_path))
    assert not metrics.empty
    assert set(metrics["ablation_name"]) == {"dfm_score", "fundamentals_only", "text_only", "naive_baseline"}
    dfm_ic = metrics[metrics["ablation_name"] == "dfm_score"]["spearman_ic"].mean()
    assert dfm_ic > 0.9


def test_build_ablation_portfolio_and_summary(tmp_path: Path):
    make_dataset().to_csv(tmp_path / "model_dataset_with_splits.csv", index=False)
    cfg = config(tmp_path)
    predictions = build_ablation_predictions_dataframe(cfg)
    metrics = build_ablation_metrics_dataframe(predictions, cfg)
    portfolio = build_ablation_portfolio_returns_dataframe(predictions, cfg)
    summary = build_ablation_summary_dataframe(metrics, portfolio, cfg)

    assert not portfolio.empty
    assert set(portfolio["ablation_name"]) == {"dfm_score", "fundamentals_only", "text_only", "naive_baseline"}
    assert not summary.empty
    assert "mean_spearman_ic" in summary.columns
    assert "portfolio_cumulative_net_return" in summary.columns


def test_render_markdown_report(tmp_path: Path):
    make_dataset().to_csv(tmp_path / "model_dataset_with_splits.csv", index=False)
    cfg = config(tmp_path)
    predictions = build_ablation_predictions_dataframe(cfg)
    metrics = build_ablation_metrics_dataframe(predictions, cfg)
    portfolio = build_ablation_portfolio_returns_dataframe(predictions, cfg)
    summary = build_ablation_summary_dataframe(metrics, portfolio, cfg)
    diagnostics = pd.DataFrame([{"diagnostic": "prediction_rows", "value": len(predictions)}])
    md = render_markdown_report(summary, diagnostics, cfg)
    assert "# Ablation Study Report" in md
    assert "dfm_score" in md
    assert "| Rank | Ablation |" in md
