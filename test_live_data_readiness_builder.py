from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.final_research_verdict import FinalResearchVerdictConfig, build_final_research_verdict


def test_build_final_research_verdict_outputs(tmp_path: Path):
    performance = pd.DataFrame(
        [
            {"metric": "primary_model_name", "value": "ridge"},
            {"metric": "period_count", "value": 24},
            {"metric": "cumulative_net_return", "value": 0.3},
            {"metric": "annualized_net_return", "value": 0.14},
            {"metric": "net_sharpe", "value": 1.2},
            {"metric": "net_sortino", "value": 1.8},
            {"metric": "net_max_drawdown", "value": -0.12},
            {"metric": "net_hit_rate", "value": 0.62},
            {"metric": "mean_turnover", "value": 0.7},
            {"metric": "total_transaction_cost_return", "value": 0.03},
        ]
    )
    model_selection = pd.DataFrame(
        [
            {
                "model_name": "ridge",
                "is_primary_model": True,
                "model_selection_rank": 1,
                "validation_mean_spearman_ic": 0.06,
                "validation_mean_mae": 0.05,
                "validation_mean_rmse": 0.07,
                "test_mean_spearman_ic": 0.04,
            }
        ]
    )
    ablation = pd.DataFrame(
        [
            {"ablation_name": "dfm_score", "mean_spearman_ic": 0.07, "mean_mae": 0.04, "mean_rmse": 0.06, "portfolio_cumulative_net_return": 0.25, "ablation_score_rank": 1},
            {"ablation_name": "fundamentals_only", "mean_spearman_ic": 0.03, "mean_mae": 0.05, "mean_rmse": 0.07, "portfolio_cumulative_net_return": 0.10, "ablation_score_rank": 2},
            {"ablation_name": "text_only", "mean_spearman_ic": 0.01, "mean_mae": 0.06, "mean_rmse": 0.08, "portfolio_cumulative_net_return": 0.02, "ablation_score_rank": 3},
        ]
    )

    performance_path = tmp_path / "portfolio_performance_summary.csv"
    model_selection_path = tmp_path / "model_selection_report.csv"
    ablation_path = tmp_path / "ablation_summary.csv"
    performance.to_csv(performance_path, index=False)
    model_selection.to_csv(model_selection_path, index=False)
    ablation.to_csv(ablation_path, index=False)

    config = FinalResearchVerdictConfig(
        portfolio_performance_summary_path=performance_path,
        model_selection_report_path=model_selection_path,
        ablation_summary_path=ablation_path,
        verdict_output_table_path=tmp_path / "final_research_verdict.parquet",
        verdict_output_csv_path=tmp_path / "final_research_verdict.csv",
        evidence_output_table_path=tmp_path / "final_research_evidence.parquet",
        evidence_output_csv_path=tmp_path / "final_research_evidence.csv",
        criteria_output_table_path=tmp_path / "final_research_criteria.parquet",
        criteria_output_csv_path=tmp_path / "final_research_criteria.csv",
        markdown_report_path=tmp_path / "final_research_verdict.md",
        diagnostics_path=tmp_path / "final_research_verdict_diagnostics.csv",
        min_period_count=12,
        min_net_sharpe=0.5,
        max_net_drawdown_abs=0.25,
    )
    verdict = build_final_research_verdict(config)

    assert verdict.iloc[0]["final_verdict"] == "PASS"
    assert (tmp_path / "final_research_verdict.csv").exists()
    assert (tmp_path / "final_research_evidence.csv").exists()
    assert (tmp_path / "final_research_criteria.csv").exists()
    assert (tmp_path / "final_research_verdict.md").exists()
    assert (tmp_path / "final_research_verdict_diagnostics.csv").exists()
