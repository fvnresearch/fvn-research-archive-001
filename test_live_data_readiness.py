from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.final_research_verdict import (
    FinalResearchVerdictConfig,
    build_criteria_table,
    build_evidence_table,
    build_verdict_table,
    render_markdown_report,
)


def config(tmp_path: Path, **kwargs) -> FinalResearchVerdictConfig:
    params = dict(
        portfolio_performance_summary_path=tmp_path / "portfolio_performance_summary.csv",
        model_selection_report_path=tmp_path / "model_selection_report.csv",
        ablation_summary_path=tmp_path / "ablation_summary.csv",
        verdict_output_table_path=tmp_path / "final_research_verdict.parquet",
        verdict_output_csv_path=tmp_path / "final_research_verdict.csv",
        evidence_output_table_path=tmp_path / "final_research_evidence.parquet",
        evidence_output_csv_path=tmp_path / "final_research_evidence.csv",
        criteria_output_table_path=tmp_path / "final_research_criteria.parquet",
        criteria_output_csv_path=tmp_path / "final_research_criteria.csv",
        markdown_report_path=tmp_path / "final_research_verdict.md",
        diagnostics_path=tmp_path / "diagnostics.csv",
        min_period_count=12,
        min_net_sharpe=0.5,
        max_net_drawdown_abs=0.25,
    )
    params.update(kwargs)
    return FinalResearchVerdictConfig(**params)


def performance_summary(periods=24, sharpe=1.1, cumulative=0.2, drawdown=-0.1):
    return pd.DataFrame(
        [
            {"metric": "primary_model_name", "value": "elastic_net"},
            {"metric": "period_count", "value": periods},
            {"metric": "cumulative_net_return", "value": cumulative},
            {"metric": "annualized_net_return", "value": 0.1},
            {"metric": "net_sharpe", "value": sharpe},
            {"metric": "net_sortino", "value": 1.5},
            {"metric": "net_max_drawdown", "value": drawdown},
            {"metric": "net_hit_rate", "value": 0.6},
            {"metric": "mean_turnover", "value": 0.8},
            {"metric": "total_transaction_cost_return", "value": 0.02},
        ]
    )


def model_selection(validation_ic=0.05):
    return pd.DataFrame(
        [
            {
                "model_name": "elastic_net",
                "is_primary_model": True,
                "model_selection_rank": 1,
                "validation_mean_spearman_ic": validation_ic,
                "validation_mean_mae": 0.05,
                "validation_mean_rmse": 0.07,
                "test_mean_spearman_ic": 0.04,
            }
        ]
    )


def ablation(dfm_ic=0.06, fund_ic=0.02, text_ic=0.01):
    return pd.DataFrame(
        [
            {"ablation_name": "dfm_score", "mean_spearman_ic": dfm_ic, "mean_mae": 0.04, "mean_rmse": 0.06, "portfolio_cumulative_net_return": 0.2, "ablation_score_rank": 1},
            {"ablation_name": "fundamentals_only", "mean_spearman_ic": fund_ic, "mean_mae": 0.05, "mean_rmse": 0.07, "portfolio_cumulative_net_return": 0.1, "ablation_score_rank": 2},
            {"ablation_name": "text_only", "mean_spearman_ic": text_ic, "mean_mae": 0.06, "mean_rmse": 0.08, "portfolio_cumulative_net_return": 0.02, "ablation_score_rank": 3},
        ]
    )


def test_build_evidence_table(tmp_path: Path):
    evidence = build_evidence_table(performance_summary(), model_selection(), ablation(), config(tmp_path))
    assert not evidence.empty
    assert "portfolio_performance_summary" in set(evidence["evidence_source"])
    assert "ablation_summary" in set(evidence["evidence_source"])
    assert "dfm_mean_spearman_ic" in set(evidence["evidence_metric"])


def test_criteria_pass_and_verdict_pass(tmp_path: Path):
    criteria = build_criteria_table(performance_summary(), model_selection(), ablation(), config(tmp_path))
    verdict = build_verdict_table(criteria, config(tmp_path))
    assert criteria["passed"].all()
    assert verdict.iloc[0]["final_verdict"] == "PASS"


def test_criteria_fail_when_sharpe_too_low(tmp_path: Path):
    criteria = build_criteria_table(performance_summary(sharpe=0.1), model_selection(), ablation(), config(tmp_path))
    verdict = build_verdict_table(criteria, config(tmp_path))
    assert not criteria[criteria["criterion"] == "minimum_net_sharpe"].iloc[0]["passed"]
    assert verdict.iloc[0]["final_verdict"] == "FAIL"
    assert "minimum_net_sharpe" in verdict.iloc[0]["verdict_notes"]


def test_criteria_fail_when_dfm_not_best(tmp_path: Path):
    criteria = build_criteria_table(performance_summary(), model_selection(), ablation(dfm_ic=0.01, fund_ic=0.05), config(tmp_path))
    verdict = build_verdict_table(criteria, config(tmp_path))
    assert not criteria[criteria["criterion"] == "dfm_best_or_tied_ablation"].iloc[0]["passed"]
    assert verdict.iloc[0]["final_verdict"] == "FAIL"


def test_render_markdown_report(tmp_path: Path):
    cfg = config(tmp_path)
    evidence = build_evidence_table(performance_summary(), model_selection(), ablation(), cfg)
    criteria = build_criteria_table(performance_summary(), model_selection(), ablation(), cfg)
    verdict = build_verdict_table(criteria, cfg)
    md = render_markdown_report(verdict, evidence, criteria)
    assert "# Final Research Verdict" in md
    assert "Final verdict: **PASS**" in md
    assert "| Criterion | Threshold | Observed |" in md
