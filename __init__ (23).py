from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import ElasticNet, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


BASELINE_MODEL_VERSION = "BASELINE_MODEL_TRAINER_V0"

DEFAULT_MODEL_NAMES = ("ridge", "elastic_net", "gradient_boosting")
DEFAULT_TARGET_COLUMN = "y_forward_63d_sector_adjusted_return"


@dataclass(frozen=True)
class BaselineTrainerConfig:
    model_dataset_with_splits_path: Path
    predictions_output_table_path: Path
    predictions_output_csv_path: Path
    diagnostics_path: Path
    target_column: str = DEFAULT_TARGET_COLUMN
    model_names: tuple[str, ...] = DEFAULT_MODEL_NAMES
    min_train_rows: int = 20
    min_eval_rows: int = 1
    random_state: int = 17
    model_version: str = BASELINE_MODEL_VERSION


def read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input table not found: {p}")
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    return pd.read_csv(p, dtype=str).fillna("")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    clean = str(value).strip()
    if clean == "":
        return None
    try:
        number = float(clean)
    except Exception:
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def parse_feature_columns(df: pd.DataFrame) -> list[str]:
    if "model_feature_columns" not in df.columns:
        raise ValueError("model_dataset_with_splits requires model_feature_columns.")

    candidates: list[str] = []
    for value in df["model_feature_columns"].dropna().astype(str):
        if value.strip():
            candidates = [c.strip() for c in value.split(",") if c.strip()]
            break

    if not candidates:
        raise ValueError("No model feature columns found in model_feature_columns.")

    missing = [c for c in candidates if c not in df.columns]
    if missing:
        # Keep present columns, but report via diagnostics later by preserving feature count.
        candidates = [c for c in candidates if c in df.columns]
    if not candidates:
        raise ValueError("None of the declared model feature columns exist in dataset.")

    numeric_candidates = []
    for col in candidates:
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().any():
            numeric_candidates.append(col)
    if not numeric_candidates:
        raise ValueError("Declared model features contain no numeric values.")
    return numeric_candidates


def make_model(name: str, *, random_state: int) -> Pipeline:
    name = name.strip().lower()
    if name == "ridge":
        estimator = Ridge(alpha=1.0, random_state=random_state)
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", estimator),
            ]
        )

    if name == "elastic_net":
        estimator = ElasticNet(alpha=0.001, l1_ratio=0.25, max_iter=10_000, random_state=random_state)
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("scaler", StandardScaler()),
                ("model", estimator),
            ]
        )

    if name == "gradient_boosting":
        estimator = GradientBoostingRegressor(
            n_estimators=100,
            learning_rate=0.03,
            max_depth=2,
            min_samples_leaf=5,
            random_state=random_state,
        )
        return Pipeline(
            steps=[
                ("imputer", SimpleImputer(strategy="median")),
                ("model", estimator),
            ]
        )

    raise ValueError(f"Unknown baseline model name: {name}")


def _prepare_xy(df: pd.DataFrame, feature_columns: list[str], target_column: str) -> tuple[pd.DataFrame, pd.Series]:
    x = df[feature_columns].apply(pd.to_numeric, errors="coerce")
    y = pd.to_numeric(df[target_column], errors="coerce")
    return x, y


def _eligible_training_rows(df: pd.DataFrame, target_column: str) -> pd.DataFrame:
    out = df.copy()
    if "model_dataset_eligible" in out.columns:
        out = out[out["model_dataset_eligible"].map(_as_bool)].copy()
    out[target_column] = pd.to_numeric(out[target_column], errors="coerce")
    out = out.dropna(subset=[target_column])
    return out


def _prediction_rows(
    *,
    fold_id: str,
    model_name: str,
    role: str,
    rows: pd.DataFrame,
    predictions: np.ndarray,
    target_column: str,
    feature_columns: list[str],
    model_version: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for (_, row), pred in zip(rows.iterrows(), predictions):
        y_true = _to_float(row.get(target_column))
        out.append(
            {
                "walk_forward_fold_id": fold_id,
                "walk_forward_role": role,
                "model_name": model_name,
                "model_version": model_version,
                "model_row_id": row.get("model_row_id", ""),
                "panel_row_id": row.get("panel_row_id", ""),
                "cik": row.get("cik", ""),
                "cik10": row.get("cik10", ""),
                "ticker": row.get("ticker", ""),
                "sector": row.get("sector", ""),
                "accession_number": row.get("accession_number", ""),
                "primary_document": row.get("primary_document", ""),
                "feature_asof_date": row.get("feature_asof_date", ""),
                "target_column": target_column,
                "y_true": y_true,
                "y_pred": float(pred),
                "prediction_error": float(pred - y_true) if y_true is not None else None,
                "feature_count": len(feature_columns),
                "feature_columns": ",".join(feature_columns),
            }
        )
    return out


def _safe_corr(y_true: pd.Series, y_pred: pd.Series, method: str) -> float | None:
    if len(y_true) < 2:
        return None
    value = y_true.corr(y_pred, method=method)
    if pd.isna(value):
        return None
    return float(value)


def _metrics_row(
    *,
    fold_id: str,
    model_name: str,
    role: str,
    rows: pd.DataFrame,
    predictions: np.ndarray | None,
    target_column: str,
    feature_count: int,
    status: str = "success",
    notes: str = "",
) -> dict[str, Any]:
    if predictions is None or rows.empty:
        return {
            "walk_forward_fold_id": fold_id,
            "model_name": model_name,
            "walk_forward_role": role,
            "status": status,
            "notes": notes,
            "n_rows": len(rows),
            "feature_count": feature_count,
            "target_column": target_column,
            "mse": None,
            "rmse": None,
            "mae": None,
            "r2": None,
            "pearson_corr": None,
            "spearman_corr": None,
            "mean_y_true": None,
            "mean_y_pred": None,
        }

    y_true = pd.to_numeric(rows[target_column], errors="coerce")
    y_pred = pd.Series(predictions, index=rows.index, dtype=float)
    valid = y_true.notna() & y_pred.notna()
    y_true_valid = y_true[valid]
    y_pred_valid = y_pred[valid]

    if len(y_true_valid) == 0:
        return _metrics_row(
            fold_id=fold_id,
            model_name=model_name,
            role=role,
            rows=rows,
            predictions=None,
            target_column=target_column,
            feature_count=feature_count,
            status="skipped",
            notes="no_valid_targets",
        )

    mse = mean_squared_error(y_true_valid, y_pred_valid)
    rmse = math.sqrt(mse)
    mae = mean_absolute_error(y_true_valid, y_pred_valid)
    r2 = r2_score(y_true_valid, y_pred_valid) if len(y_true_valid) >= 2 else None

    return {
        "walk_forward_fold_id": fold_id,
        "model_name": model_name,
        "walk_forward_role": role,
        "status": status,
        "notes": notes,
        "n_rows": int(len(y_true_valid)),
        "feature_count": feature_count,
        "target_column": target_column,
        "mse": float(mse),
        "rmse": float(rmse),
        "mae": float(mae),
        "r2": float(r2) if r2 is not None and not pd.isna(r2) else None,
        "pearson_corr": _safe_corr(y_true_valid, y_pred_valid, "pearson"),
        "spearman_corr": _safe_corr(y_true_valid, y_pred_valid, "spearman"),
        "mean_y_true": float(y_true_valid.mean()),
        "mean_y_pred": float(y_pred_valid.mean()),
    }


def train_one_fold(
    *,
    fold_df: pd.DataFrame,
    fold_id: str,
    model_name: str,
    feature_columns: list[str],
    config: BaselineTrainerConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train_rows = _eligible_training_rows(
        fold_df[fold_df["walk_forward_role"] == "train"].copy(),
        config.target_column,
    )

    prediction_records: list[dict[str, Any]] = []
    metric_records: list[dict[str, Any]] = []

    if len(train_rows) < config.min_train_rows:
        note = f"insufficient_train_rows={len(train_rows)}<min_train_rows={config.min_train_rows}"
        for role in ["train", "validation", "test"]:
            role_rows = _eligible_training_rows(
                fold_df[fold_df["walk_forward_role"] == role].copy(),
                config.target_column,
            )
            metric_records.append(
                _metrics_row(
                    fold_id=fold_id,
                    model_name=model_name,
                    role=role,
                    rows=role_rows,
                    predictions=None,
                    target_column=config.target_column,
                    feature_count=len(feature_columns),
                    status="skipped",
                    notes=note,
                )
            )
        return prediction_records, metric_records

    x_train, y_train = _prepare_xy(train_rows, feature_columns, config.target_column)
    model = make_model(model_name, random_state=config.random_state)
    model.fit(x_train, y_train)

    for role in ["train", "validation", "test"]:
        role_rows = _eligible_training_rows(
            fold_df[fold_df["walk_forward_role"] == role].copy(),
            config.target_column,
        )
        if len(role_rows) < config.min_eval_rows:
            metric_records.append(
                _metrics_row(
                    fold_id=fold_id,
                    model_name=model_name,
                    role=role,
                    rows=role_rows,
                    predictions=None,
                    target_column=config.target_column,
                    feature_count=len(feature_columns),
                    status="skipped",
                    notes=f"insufficient_eval_rows={len(role_rows)}<min_eval_rows={config.min_eval_rows}",
                )
            )
            continue

        x_role, _ = _prepare_xy(role_rows, feature_columns, config.target_column)
        predictions = model.predict(x_role)
        prediction_records.extend(
            _prediction_rows(
                fold_id=fold_id,
                model_name=model_name,
                role=role,
                rows=role_rows,
                predictions=predictions,
                target_column=config.target_column,
                feature_columns=feature_columns,
                model_version=config.model_version,
            )
        )
        metric_records.append(
            _metrics_row(
                fold_id=fold_id,
                model_name=model_name,
                role=role,
                rows=role_rows,
                predictions=predictions,
                target_column=config.target_column,
                feature_count=len(feature_columns),
            )
        )

    return prediction_records, metric_records


def build_baseline_predictions_and_diagnostics(config: BaselineTrainerConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = read_table(config.model_dataset_with_splits_path)
    if data.empty:
        return pd.DataFrame(), pd.DataFrame([{"diagnostic": "rows", "value": 0}])

    if "walk_forward_fold_id" not in data.columns or "walk_forward_role" not in data.columns:
        raise ValueError("Input requires walk_forward_fold_id and walk_forward_role columns.")
    if config.target_column not in data.columns:
        raise ValueError(f"Input missing target column: {config.target_column}")

    feature_columns = parse_feature_columns(data)

    all_predictions: list[dict[str, Any]] = []
    all_metrics: list[dict[str, Any]] = []

    for fold_id, fold_df in data.groupby("walk_forward_fold_id", sort=True):
        for model_name in config.model_names:
            predictions, metrics = train_one_fold(
                fold_df=fold_df.copy(),
                fold_id=str(fold_id),
                model_name=model_name,
                feature_columns=feature_columns,
                config=config,
            )
            all_predictions.extend(predictions)
            all_metrics.extend(metrics)

    pred_df = pd.DataFrame(all_predictions)
    metrics_df = pd.DataFrame(all_metrics)

    summary_rows = [
        {"diagnostic": "input_rows", "value": len(data)},
        {"diagnostic": "folds", "value": data["walk_forward_fold_id"].nunique()},
        {"diagnostic": "models", "value": len(config.model_names)},
        {"diagnostic": "feature_count", "value": len(feature_columns)},
        {"diagnostic": "prediction_rows", "value": len(pred_df)},
    ]
    if not metrics_df.empty:
        for status, count in metrics_df["status"].value_counts(dropna=False).items():
            summary_rows.append({"diagnostic": f"metric_status_{status}", "value": int(count)})

    summary_df = pd.DataFrame(summary_rows)
    diagnostics = pd.concat([summary_df, metrics_df], ignore_index=True, sort=False)

    if not pred_df.empty:
        pred_df = pred_df.sort_values(
            ["walk_forward_fold_id", "model_name", "walk_forward_role", "feature_asof_date", "model_row_id"]
        ).reset_index(drop=True)

    return pred_df, diagnostics


def write_baseline_outputs(
    predictions: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    predictions_output_table_path: str | Path,
    predictions_output_csv_path: str | Path,
    diagnostics_path: str | Path,
) -> None:
    safe_write_table(predictions, parquet_path=predictions_output_table_path, csv_path=predictions_output_csv_path)
    diagnostics_path = Path(diagnostics_path)
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(diagnostics_path, index=False)


def train_baseline_models(config: BaselineTrainerConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.baseline_model_trainer",
        root() / "logs/pipeline/baseline_model_trainer.log",
    )
    logger.info("Training baseline models from %s", config.model_dataset_with_splits_path)
    predictions, diagnostics = build_baseline_predictions_and_diagnostics(config)
    write_baseline_outputs(
        predictions,
        diagnostics,
        predictions_output_table_path=config.predictions_output_table_path,
        predictions_output_csv_path=config.predictions_output_csv_path,
        diagnostics_path=config.diagnostics_path,
    )
    logger.info("Wrote %d baseline prediction rows to %s", len(predictions), config.predictions_output_table_path)
    return predictions


def parse_model_names(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_MODEL_NAMES
    return tuple(part.strip() for part in value.split(",") if part.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Train baseline walk-forward models.")
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
