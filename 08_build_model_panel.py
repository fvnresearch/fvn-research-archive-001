from __future__ import annotations

import argparse

from fvn_dfm.features.research_panel import ResearchPanelConfig, build_model_research_panel
from fvn_dfm.modeling.model_dataset import ModelDatasetConfig, build_model_dataset_v0
from fvn_dfm.modeling.walk_forward_splits import WalkForwardSplitConfig, build_model_dataset_with_splits
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(description="Model matrix / research panel entrypoint.")
    parser.add_argument(
        "--layer",
        choices=["model-research-panel", "model-dataset-v0", "model-dataset-with-splits"],
        required=True,
        help="Model layer to build.",
    )

    # Research panel args
    parser.add_argument("--mismatch-features-path", default="data/processed/features/mismatch_features_asof.csv")
    parser.add_argument("--fundamental-features-path", default="data/processed/features/fundamental_features_asof.csv")
    parser.add_argument("--text-features-path", default="data/processed/features/text_features_asof.csv")
    parser.add_argument("--filing-availability-path", default="data/processed/point_in_time/filing_availability.csv")

    # Final dataset args
    parser.add_argument("--model-research-panel-path", default="data/processed/model/model_research_panel.csv")
    parser.add_argument("--return-targets-path", default="data/processed/targets/return_targets_asof.csv")
    parser.add_argument("--model-dataset-path", default="data/processed/model/model_dataset_v0.csv")

    # Walk-forward split args
    parser.add_argument("--min-train-months", type=int, default=24)
    parser.add_argument("--validation-months", type=int, default=12)
    parser.add_argument("--test-months", type=int, default=1)
    parser.add_argument("--step-months", type=int, default=1)
    parser.add_argument("--embargo-days", type=int, default=63)
    parser.add_argument("--first-test-month")
    parser.add_argument("--max-folds", type=int)
    parser.add_argument("--include-ineligible-rows", action="store_true")

    # Shared output args
    parser.add_argument("--output-table")
    parser.add_argument("--output-csv")
    parser.add_argument("--diagnostics-path")

    # Quality gate args
    parser.add_argument("--allow-red-mismatch-quality", action="store_true")
    parser.add_argument("--allow-missing-asof-date", action="store_true")
    parser.add_argument("--allow-red-timestamp-quality", action="store_true")
    parser.add_argument("--allow-red-panel-quality", action="store_true")
    parser.add_argument("--allow-red-target-quality", action="store_true")
    parser.add_argument("--allow-missing-label", action="store_true")
    args = parser.parse_args()

    if args.layer == "model-research-panel":
        config = ResearchPanelConfig(
            mismatch_features_path=root() / args.mismatch_features_path,
            fundamental_features_path=root() / args.fundamental_features_path,
            text_features_path=root() / args.text_features_path,
            filing_availability_path=root() / args.filing_availability_path if args.filing_availability_path else None,
            output_table_path=root() / (args.output_table or "data/processed/model/model_research_panel.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/model/model_research_panel.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/model_research_panel_diagnostics.csv"),
            require_mismatch_quality_green_or_yellow=not args.allow_red_mismatch_quality,
            require_feature_asof_date=not args.allow_missing_asof_date,
            require_timestamp_quality_green_or_yellow=not args.allow_red_timestamp_quality,
        )
        build_model_research_panel(config)
        return

    if args.layer == "model-dataset-v0":
        config = ModelDatasetConfig(
            model_research_panel_path=root() / args.model_research_panel_path,
            return_targets_path=root() / args.return_targets_path,
            output_table_path=root() / (args.output_table or "data/processed/model/model_dataset_v0.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/model/model_dataset_v0.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/model_dataset_v0_diagnostics.csv"),
            allow_yellow_panel_quality=True,
            allow_yellow_target_quality=True,
            require_nonmissing_label=not args.allow_missing_label,
        )
        build_model_dataset_v0(config)
        return

    if args.layer == "model-dataset-with-splits":
        config = WalkForwardSplitConfig(
            model_dataset_path=root() / args.model_dataset_path,
            output_table_path=root() / (args.output_table or "data/processed/model/model_dataset_with_splits.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/model/model_dataset_with_splits.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/model_dataset_with_splits_diagnostics.csv"),
            min_train_months=args.min_train_months,
            validation_months=args.validation_months,
            test_months=args.test_months,
            step_months=args.step_months,
            embargo_days=args.embargo_days,
            first_test_month=args.first_test_month,
            max_folds=args.max_folds,
            require_eligible_rows=not args.include_ineligible_rows,
        )
        build_model_dataset_with_splits(config)
        return


if __name__ == "__main__":
    main()
