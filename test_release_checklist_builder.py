from pathlib import Path

import pandas as pd

from fvn_dfm.portfolio.performance_report import PortfolioPerformanceConfig, build_portfolio_performance_report


def test_build_portfolio_performance_report_outputs(tmp_path: Path):
    returns = pd.DataFrame(
        [
            {
                "rebalance_period": "2021-01",
                "primary_model_name": "gradient_boosting",
                "portfolio_gross_return": 0.05,
                "portfolio_turnover": 1.0,
                "transaction_cost_return": 0.001,
                "portfolio_net_return": 0.049,
                "long_count": 3,
                "short_count": 3,
                "gross_exposure": 2.0,
                "net_exposure": 0.0,
                "portfolio_quality_flag": "GREEN",
                "portfolio_quality_notes": "",
            },
            {
                "rebalance_period": "2021-02",
                "primary_model_name": "gradient_boosting",
                "portfolio_gross_return": -0.01,
                "portfolio_turnover": 0.7,
                "transaction_cost_return": 0.0007,
                "portfolio_net_return": -0.0107,
                "long_count": 3,
                "short_count": 3,
                "gross_exposure": 2.0,
                "net_exposure": 0.0,
                "portfolio_quality_flag": "GREEN",
                "portfolio_quality_notes": "",
            },
            {
                "rebalance_period": "2021-03",
                "primary_model_name": "gradient_boosting",
                "portfolio_gross_return": 0.02,
                "portfolio_turnover": 0.5,
                "transaction_cost_return": 0.0005,
                "portfolio_net_return": 0.0195,
                "long_count": 3,
                "short_count": 3,
                "gross_exposure": 2.0,
                "net_exposure": 0.0,
                "portfolio_quality_flag": "GREEN",
                "portfolio_quality_notes": "",
            },
        ]
    )
    returns_path = tmp_path / "portfolio_monthly_returns.csv"
    returns.to_csv(returns_path, index=False)

    config = PortfolioPerformanceConfig(
        portfolio_returns_path=returns_path,
        summary_output_table_path=tmp_path / "portfolio_performance_summary.parquet",
        summary_output_csv_path=tmp_path / "portfolio_performance_summary.csv",
        monthly_output_table_path=tmp_path / "portfolio_monthly_diagnostics.parquet",
        monthly_output_csv_path=tmp_path / "portfolio_monthly_diagnostics.csv",
        markdown_report_path=tmp_path / "portfolio_performance_report.md",
        diagnostics_path=tmp_path / "portfolio_performance_report_diagnostics.csv",
    )
    summary, monthly = build_portfolio_performance_report(config)

    assert not summary.empty
    assert len(monthly) == 3
    assert (tmp_path / "portfolio_performance_summary.csv").exists()
    assert (tmp_path / "portfolio_monthly_diagnostics.csv").exists()
    assert (tmp_path / "portfolio_performance_report.md").exists()
    assert (tmp_path / "portfolio_performance_report_diagnostics.csv").exists()
    lookup = dict(zip(summary["metric"], summary["value"]))
    assert lookup["primary_model_name"] == "gradient_boosting"
    assert float(lookup["cumulative_net_return"]) > 0
