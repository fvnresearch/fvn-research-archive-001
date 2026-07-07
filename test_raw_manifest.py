from pathlib import Path

import pandas as pd

from fvn_dfm.portfolio.performance_report import (
    PortfolioPerformanceConfig,
    build_monthly_diagnostics_dataframe,
    build_performance_diagnostics,
    build_performance_summary_dataframe,
    render_markdown_report,
)


def make_returns() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "rebalance_period": "2021-01",
                "primary_model_name": "elastic_net",
                "portfolio_gross_return": 0.04,
                "portfolio_turnover": 1.0,
                "transaction_cost_return": 0.001,
                "portfolio_net_return": 0.039,
                "long_leg_contribution": 0.03,
                "short_leg_contribution": 0.01,
                "long_avg_forward_return": 0.05,
                "short_avg_forward_return": -0.02,
                "long_count": 5,
                "short_count": 5,
                "gross_exposure": 2.0,
                "net_exposure": 0.0,
                "portfolio_quality_flag": "GREEN",
                "portfolio_quality_notes": "",
            },
            {
                "rebalance_period": "2021-02",
                "primary_model_name": "elastic_net",
                "portfolio_gross_return": -0.02,
                "portfolio_turnover": 0.8,
                "transaction_cost_return": 0.0008,
                "portfolio_net_return": -0.0208,
                "long_leg_contribution": -0.01,
                "short_leg_contribution": -0.01,
                "long_avg_forward_return": -0.03,
                "short_avg_forward_return": 0.01,
                "long_count": 5,
                "short_count": 5,
                "gross_exposure": 2.0,
                "net_exposure": 0.0,
                "portfolio_quality_flag": "GREEN",
                "portfolio_quality_notes": "",
            },
            {
                "rebalance_period": "2021-03",
                "primary_model_name": "elastic_net",
                "portfolio_gross_return": 0.03,
                "portfolio_turnover": 0.6,
                "transaction_cost_return": 0.0006,
                "portfolio_net_return": 0.0294,
                "long_leg_contribution": 0.02,
                "short_leg_contribution": 0.01,
                "long_avg_forward_return": 0.04,
                "short_avg_forward_return": -0.01,
                "long_count": 5,
                "short_count": 5,
                "gross_exposure": 2.0,
                "net_exposure": 0.0,
                "portfolio_quality_flag": "GREEN",
                "portfolio_quality_notes": "",
            },
        ]
    )


def config(tmp_path: Path) -> PortfolioPerformanceConfig:
    return PortfolioPerformanceConfig(
        portfolio_returns_path=tmp_path / "portfolio_monthly_returns.csv",
        summary_output_table_path=tmp_path / "portfolio_performance_summary.parquet",
        summary_output_csv_path=tmp_path / "portfolio_performance_summary.csv",
        monthly_output_table_path=tmp_path / "portfolio_monthly_diagnostics.parquet",
        monthly_output_csv_path=tmp_path / "portfolio_monthly_diagnostics.csv",
        markdown_report_path=tmp_path / "portfolio_performance_report.md",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )


def test_build_monthly_diagnostics_dataframe():
    monthly = build_monthly_diagnostics_dataframe(make_returns())
    assert len(monthly) == 3
    assert monthly.iloc[0]["cumulative_net_return"] == 0.039
    assert monthly.iloc[1]["net_drawdown"] < 0
    assert "cumulative_cost_drag" in monthly.columns
    assert "net_return_positive" in monthly.columns


def test_build_performance_summary_dataframe(tmp_path: Path):
    summary = build_performance_summary_dataframe(make_returns(), config(tmp_path))
    lookup = dict(zip(summary["metric"], summary["value"]))
    assert lookup["period_count"] == 3
    assert lookup["primary_model_name"] == "elastic_net"
    assert float(lookup["cumulative_net_return"]) > 0
    assert "net_sharpe" in lookup
    assert "net_sortino" in lookup
    assert "net_max_drawdown" in lookup
    assert lookup["net_hit_rate"] == 2 / 3


def test_build_performance_diagnostics(tmp_path: Path):
    monthly = build_monthly_diagnostics_dataframe(make_returns())
    summary = build_performance_summary_dataframe(make_returns(), config(tmp_path))
    diagnostics = build_performance_diagnostics(summary, monthly)
    assert "summary_rows" in set(diagnostics["diagnostic"])
    assert "monthly_rows" in set(diagnostics["diagnostic"])
    assert "net_sharpe" in set(diagnostics["diagnostic"])


def test_render_markdown_report(tmp_path: Path):
    monthly = build_monthly_diagnostics_dataframe(make_returns())
    summary = build_performance_summary_dataframe(make_returns(), config(tmp_path))
    md = render_markdown_report(summary, monthly, config(tmp_path))
    assert "# Portfolio Performance Report" in md
    assert "cumulative_net_return" in md
    assert "| Period | Gross return | Net return |" in md
