from __future__ import annotations

import argparse

from fvn_dfm.modeling.ablation_study import AblationStudyConfig, TARGET_COLUMN, build_ablation_study
from fvn_dfm.modeling.model_selection_report import (
    ModelSelectionConfig,
    PRIMARY_ROLE,
    SECONDARY_ROLE,
    build_model_selection_report,
)
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(description="Model evaluation entrypoint.")
    parser.add_argument(
        "--layer",
        choices=["model-selection-report-v0", "ablation-study-v0"],
        required=True,
        help="Evaluation layer to run.",
    )

    # Model selection args
    parser.add_argument("--baseline-diagnostics-path", default="outputs/diagnostics/baseline_model_diagnostics.csv")
    parser.add_argument("--baseline-predictions-path", default="data/processed/model/baseline_fold_predictions.csv")
    parser.add_argument("--output-table", default="data/processed/model/model_selection_report.parquet")
    parser.add_argument("--output-csv", default="data/processed/model/model_selection_report.csv")
    parser.add_argument("--markdown-report-path")
    parser.add_argument("--diagnostics-path")
    parser.add_argument("--primary-role", default=PRIMARY_ROLE)
    parser.add_argument("--secondary-role", default=SECONDARY_ROLE)
    parser.add_argument("--min-validation-folds", type=int, default=1)

    # Ablation args
    parser.add_argument("--model-dataset-with-splits-path", default="data/processed/model/model_dataset_with_splits.csv")
    parser.add_argument("--predictions-output-table", default="data/processed/model/ablation_predictions.parquet")
    parser.add_argument("--predictions-output-csv", default="data/processed/model/ablation_predictions.csv")
    parser.add_argument("--metrics-output-table", default="data/processed/model/ablation_metrics.parquet")
    parser.add_argument("--metrics-output-csv", default="data/processed/model/ablation_metrics.csv")
    parser.add_argument("--portfolio-returns-output-table", default="data/processed/portfolio/ablation_portfolio_returns.parquet")
    parser.add_argument("--portfolio-returns-output-csv", default="data/processed/portfolio/ablation_portfolio_returns.csv")
    parser.add_argument("--summary-output-table", default="data/processed/model/ablation_summary.parquet")
    parser.add_argument("--summary-output-csv", default="data/processed/model/ablation_summary.csv")
    parser.add_argument("--target-column", default=TARGET_COLUMN)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--min-names-per-rebalance", type=int, default=10)
    parser.add_argument("--min-eval-rows", type=int, default=2)

    args = parser.parse_args()

    if args.layer == "model-selection-report-v0":
        config = ModelSelectionConfig(
            baseline_diagnostics_path=root() / args.baseline_diagnostics_path,
            baseline_predictions_path=root() / args.baseline_predictions_path if args.baseline_predictions_path else None,
            output_table_path=root() / args.output_table,
            output_csv_path=root() / args.output_csv,
            markdown_report_path=root() / (args.markdown_report_path or "outputs/reports/model_selection_report.md"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/model_selection_report_diagnostics.csv"),
            primary_role=args.primary_role,
            secondary_role=args.secondary_role,
            min_validation_folds=args.min_validation_folds,
        )
        build_model_selection_report(config)
        return

    if args.layer == "ablation-study-v0":
        config = AblationStudyConfig(
            model_dataset_with_splits_path=root() / args.model_dataset_with_splits_path,
            predictions_output_table_path=root() / args.predictions_output_table,
            predictions_output_csv_path=root() / args.predictions_output_csv,
            metrics_output_table_path=root() / args.metrics_output_table,
            metrics_output_csv_path=root() / args.metrics_output_csv,
            portfolio_returns_output_table_path=root() / args.portfolio_returns_output_table,
            portfolio_returns_output_csv_path=root() / args.portfolio_returns_output_csv,
            summary_output_table_path=root() / args.summary_output_table,
            summary_output_csv_path=root() / args.summary_output_csv,
            markdown_report_path=root() / (args.markdown_report_path or "outputs/reports/ablation_study_report.md"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/ablation_study_diagnostics.csv"),
            target_column=args.target_column,
            transaction_cost_bps=args.transaction_cost_bps,
            min_names_per_rebalance=args.min_names_per_rebalance,
            min_eval_rows=args.min_eval_rows,
        )
        build_ablation_study(config)
        return


if __name__ == "__main__":
    main()
