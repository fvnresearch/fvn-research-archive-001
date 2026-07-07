from __future__ import annotations

import argparse

from fvn_dfm.modeling.baseline_trainer import (
    BaselineTrainerConfig,
    DEFAULT_TARGET_COLUMN,
    parse_model_names,
    train_baseline_models,
)
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(description="Model training entrypoint.")
    parser.add_argument(
        "--layer",
        choices=["baseline-models-v0"],
        required=True,
        help="Training layer to run.",
    )
    parser.add_argument("--model-dataset-with-splits-path", default="data/processed/model/model_dataset_with_splits.csv")
    parser.add_argument("--predictions-output-table", default="data/processed/model/baseline_fold_predictions.parquet")
    parser.add_argument("--predictions-output-csv", default="data/processed/model/baseline_fold_predictions.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/baseline_model_diagnostics.csv")
    parser.add_argument("--target-column", default=DEFAULT_TARGET_COLUMN)
    parser.add_argument("--models", default="ridge,elastic_net,gradient_boosting")
    parser.add_argument("--min-train-rows", type=int, default=20)
    parser.add_argument("--min-eval-rows", type=int, default=1)
    parser.add_argument("--random-state", type=int, default=17)
    args = parser.parse_args()

    if args.layer == "baseline-models-v0":
        config = BaselineTrainerConfig(
            model_dataset_with_splits_path=root() / args.model_dataset_with_splits_path,
            predictions_output_table_path=root() / args.predictions_output_table,
            predictions_output_csv_path=root() / args.predictions_output_csv,
            diagnostics_path=root() / args.diagnostics_path,
            target_column=args.target_column,
            model_names=parse_model_names(args.models),
            min_train_rows=args.min_train_rows,
            min_eval_rows=args.min_eval_rows,
            random_state=args.random_state,
        )
        train_baseline_models(config)


if __name__ == "__main__":
    main()
