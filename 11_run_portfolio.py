from __future__ import annotations

import argparse

from fvn_dfm.portfolio.performance_report import PortfolioPerformanceConfig, build_portfolio_performance_report
from fvn_dfm.portfolio.portfolio_construction import PortfolioConstructionConfig, build_long_short_decile_portfolio
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(description="Portfolio construction/evaluation entrypoint.")
    parser.add_argument(
        "--layer",
        choices=["long-short-decile-v0", "portfolio-performance-report-v0"],
        required=True,
        help="Portfolio layer to build.",
    )

    # Portfolio construction args
    parser.add_argument("--baseline-predictions-path", default="data/processed/model/baseline_fold_predictions.csv")
    parser.add_argument("--model-selection-report-path", default="data/processed/model/model_selection_report.csv")
    parser.add_argument("--holdings-output-table", default="data/processed/portfolio/portfolio_holdings.parquet")
    parser.add_argument("--holdings-output-csv", default="data/processed/portfolio/portfolio_holdings.csv")
    parser.add_argument("--returns-output-table", default="data/processed/portfolio/portfolio_monthly_returns.parquet")
    parser.add_argument("--returns-output-csv", default="data/processed/portfolio/portfolio_monthly_returns.csv")
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--min-names-per-rebalance", type=int, default=10)
    parser.add_argument("--prediction-role", default="test")
    parser.add_argument("--long-quantile", type=float, default=0.9)
    parser.add_argument("--short-quantile", type=float, default=0.1)

    # Performance report args
    parser.add_argument("--portfolio-returns-path", default="data/processed/portfolio/portfolio_monthly_returns.csv")
    parser.add_argument("--summary-output-table", default="data/processed/portfolio/portfolio_performance_summary.parquet")
    parser.add_argument("--summary-output-csv", default="data/processed/portfolio/portfolio_performance_summary.csv")
    parser.add_argument("--monthly-output-table", default="data/processed/portfolio/portfolio_monthly_diagnostics.parquet")
    parser.add_argument("--monthly-output-csv", default="data/processed/portfolio/portfolio_monthly_diagnostics.csv")
    parser.add_argument("--markdown-report-path", default="outputs/reports/portfolio_performance_report.md")
    parser.add_argument("--annualization-periods", type=int, default=12)

    # Shared diagnostics
    parser.add_argument("--diagnostics-path")

    args = parser.parse_args()

    if args.layer == "long-short-decile-v0":
        config = PortfolioConstructionConfig(
            baseline_predictions_path=root() / args.baseline_predictions_path,
            model_selection_report_path=root() / args.model_selection_report_path,
            holdings_output_table_path=root() / args.holdings_output_table,
            holdings_output_csv_path=root() / args.holdings_output_csv,
            returns_output_table_path=root() / args.returns_output_table,
            returns_output_csv_path=root() / args.returns_output_csv,
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/portfolio_construction_diagnostics.csv"),
            transaction_cost_bps=args.transaction_cost_bps,
            min_names_per_rebalance=args.min_names_per_rebalance,
            prediction_role=args.prediction_role,
            long_quantile=args.long_quantile,
            short_quantile=args.short_quantile,
        )
        build_long_short_decile_portfolio(config)
        return

    if args.layer == "portfolio-performance-report-v0":
        config = PortfolioPerformanceConfig(
            portfolio_returns_path=root() / args.portfolio_returns_path,
            summary_output_table_path=root() / args.summary_output_table,
            summary_output_csv_path=root() / args.summary_output_csv,
            monthly_output_table_path=root() / args.monthly_output_table,
            monthly_output_csv_path=root() / args.monthly_output_csv,
            markdown_report_path=root() / args.markdown_report_path,
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/portfolio_performance_report_diagnostics.csv"),
            annualization_periods=args.annualization_periods,
        )
        build_portfolio_performance_report(config)
        return


if __name__ == "__main__":
    main()
