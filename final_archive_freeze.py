from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


MODEL_SELECTION_REPORT_VERSION = "MODEL_SELECTION_REPORT_V0"

PRIMARY_ROLE = "validation"
SECONDARY_ROLE = "test"
IC_COLUMN = "spearman_corr"


@dataclass(frozen=True)
class ModelSelectionConfig:
    baseline_diagnostics_path: Path
    baseline_predictions_path: Path | None
    output_table_path: Path
    output_csv_path: Path
    markdown_report_path: Path
    diagnostics_path: Path
    report_version: str = MODEL_SELECTION_REPORT_VERSION
    primary_role: str = PRIMARY_ROLE
    secondary_role: str = SECONDARY_ROLE
    min_validation_folds: int = 1


def read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input table not found: {p}")
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    return pd.read_csv(p, dtype=str).fillna("")


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


def _metrics_rows(diagnostics: pd.DataFrame) -> pd.DataFrame:
    required = {"model_name", "walk_forward_role", "status"}
    missing = required.difference(diagnostics.columns)
    if missing:
        raise ValueError(f"Baseline diagnostics missing required metric columns: {sorted(missing)}")

    metrics = diagnostics[
        diagnostics["model_name"].astype(str).str.len().gt(0)
        & diagnostics["walk_forward_role"].astype(str).str.len().gt(0)
    ].copy()

    numeric_cols = [
        "n_rows",
        "feature_count",
        "mse",
        "rmse",
        "mae",
        "r2",
        "pearson_corr",
        "spearman_corr",
        "mean_y_true",
        "mean_y_pred",
    ]
    for col in numeric_cols:
        if col in metrics.columns:
            metrics[col] = pd.to_numeric(metrics[col], errors="coerce")

    return metrics


def _predictions_summary(predictions: pd.DataFrame | None) -> pd.DataFrame:
    if predictions is None or predictions.empty:
        return pd.DataFrame(columns=["model_name", "walk_forward_role", "prediction_rows", "prediction_folds"])

    required = {"model_name", "walk_forward_role", "walk_forward_fold_id"}
    if not required.issubset(predictions.columns):
        return pd.DataFrame(columns=["model_name", "walk_forward_role", "prediction_rows", "prediction_folds"])

    return (
        predictions.groupby(["model_name", "walk_forward_role"])
        .agg(
            prediction_rows=("model_name", "size"),
            prediction_folds=("walk_forward_fold_id", "nunique"),
        )
        .reset_index()
    )


def _aggregate_role_metrics(metrics: pd.DataFrame) -> pd.DataFrame:
    success = metrics[metrics["status"].astype(str) == "success"].copy()
    if success.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for (model_name, role), group in success.groupby(["model_name", "walk_forward_role"]):
        rows.append(
            {
                "model_name": model_name,
                "walk_forward_role": role,
                "folds_success": group["walk_forward_fold_id"].nunique() if "walk_forward_fold_id" in group.columns else len(group),
                "rows_total": int(group["n_rows"].sum()) if "n_rows" in group.columns else None,
                "mean_spearman_ic": group["spearman_corr"].mean() if "spearman_corr" in group.columns else None,
                "median_spearman_ic": group["spearman_corr"].median() if "spearman_corr" in group.columns else None,
                "mean_pearson_ic": group["pearson_corr"].mean() if "pearson_corr" in group.columns else None,
                "median_pearson_ic": group["pearson_corr"].median() if "pearson_corr" in group.columns else None,
                "mean_mae": group["mae"].mean() if "mae" in group.columns else None,
                "median_mae": group["mae"].median() if "mae" in group.columns else None,
                "mean_rmse": group["rmse"].mean() if "rmse" in group.columns else None,
                "median_rmse": group["rmse"].median() if "rmse" in group.columns else None,
                "mean_r2": group["r2"].mean() if "r2" in group.columns else None,
                "mean_y_true": group["mean_y_true"].mean() if "mean_y_true" in group.columns else None,
                "mean_y_pred": group["mean_y_pred"].mean() if "mean_y_pred" in group.columns else None,
            }
        )

    return pd.DataFrame(rows)


def _wide_model_report(role_metrics: pd.DataFrame, predictions_summary: pd.DataFrame, config: ModelSelectionConfig) -> pd.DataFrame:
    if role_metrics.empty:
        return pd.DataFrame()

    merged = role_metrics.merge(predictions_summary, on=["model_name", "walk_forward_role"], how="left")
    merged["prediction_rows"] = merged["prediction_rows"].fillna(0).astype(int) if "prediction_rows" in merged else 0
    merged["prediction_folds"] = merged["prediction_folds"].fillna(0).astype(int) if "prediction_folds" in merged else 0

    roles = sorted(set(merged["walk_forward_role"]))
    models = sorted(set(merged["model_name"]))

    rows: list[dict[str, Any]] = []
    for model in models:
        out: dict[str, Any] = {
            "model_name": model,
            "model_selection_report_version": config.report_version,
        }
        model_metrics = merged[merged["model_name"] == model]
        for role in roles:
            role_row = model_metrics[model_metrics["walk_forward_role"] == role]
            prefix = role
            if role_row.empty:
                out[f"{prefix}_folds_success"] = 0
                out[f"{prefix}_rows_total"] = 0
                out[f"{prefix}_mean_spearman_ic"] = None
                out[f"{prefix}_mean_pearson_ic"] = None
                out[f"{prefix}_mean_mae"] = None
                out[f"{prefix}_mean_rmse"] = None
                out[f"{prefix}_mean_r2"] = None
                out[f"{prefix}_prediction_rows"] = 0
                out[f"{prefix}_prediction_folds"] = 0
                continue

            rr = role_row.iloc[0]
            for col in [
                "folds_success",
                "rows_total",
                "mean_spearman_ic",
                "median_spearman_ic",
                "mean_pearson_ic",
                "median_pearson_ic",
                "mean_mae",
                "median_mae",
                "mean_rmse",
                "median_rmse",
                "mean_r2",
                "mean_y_true",
                "mean_y_pred",
                "prediction_rows",
                "prediction_folds",
            ]:
                out[f"{prefix}_{col}"] = rr.get(col, None)
        rows.append(out)

    df = pd.DataFrame(rows)
    return df


def _rank_series(series: pd.Series, *, ascending: bool) -> pd.Series:
    # Missing values rank last.
    filled = pd.to_numeric(series, errors="coerce")
    if ascending:
        sentinel = filled.max(skipna=True)
        sentinel = 1e9 if pd.isna(sentinel) else sentinel + abs(sentinel) + 1e6
    else:
        sentinel = filled.min(skipna=True)
        sentinel = -1e9 if pd.isna(sentinel) else sentinel - abs(sentinel) - 1e6
    return filled.fillna(sentinel).rank(method="min", ascending=ascending)


def add_selection_ranks(report: pd.DataFrame, config: ModelSelectionConfig) -> pd.DataFrame:
    if report.empty:
        return report

    out = report.copy()
    role = config.primary_role
    test_role = config.secondary_role

    ic_col = f"{role}_mean_spearman_ic"
    mae_col = f"{role}_mean_mae"
    rmse_col = f"{role}_mean_rmse"
    folds_col = f"{role}_folds_success"

    for col in [ic_col, mae_col, rmse_col, folds_col]:
        if col not in out.columns:
            out[col] = None

    out["rank_validation_ic"] = _rank_series(out[ic_col], ascending=False)
    out["rank_validation_mae"] = _rank_series(out[mae_col], ascending=True)
    out["rank_validation_rmse"] = _rank_series(out[rmse_col], ascending=True)
    out["validation_folds_ok"] = pd.to_numeric(out[folds_col], errors="coerce").fillna(0) >= config.min_validation_folds

    # Composite rank: primary priority is validation IC; MAE/RMSE break ties.
    out["model_selection_score"] = (
        out["rank_validation_ic"] * 10.0
        + out["rank_validation_mae"] * 2.0
        + out["rank_validation_rmse"] * 1.0
    )

    # Penalize models without enough validation folds.
    out.loc[~out["validation_folds_ok"], "model_selection_score"] = out["model_selection_score"] + 1_000_000

    out = out.sort_values(
        ["model_selection_score", "rank_validation_ic", "rank_validation_mae", "rank_validation_rmse", "model_name"]
    ).reset_index(drop=True)
    out["model_selection_rank"] = range(1, len(out) + 1)
    out["is_primary_model"] = out["model_selection_rank"] == 1

    if f"{test_role}_mean_spearman_ic" not in out.columns:
        out[f"{test_role}_mean_spearman_ic"] = None
    if f"{test_role}_mean_mae" not in out.columns:
        out[f"{test_role}_mean_mae"] = None
    if f"{test_role}_mean_rmse" not in out.columns:
        out[f"{test_role}_mean_rmse"] = None

    return out


def build_model_selection_report_dataframe(config: ModelSelectionConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    diagnostics = read_table(config.baseline_diagnostics_path)
    predictions = read_table(config.baseline_predictions_path) if config.baseline_predictions_path and Path(config.baseline_predictions_path).exists() else None

    metrics = _metrics_rows(diagnostics)
    role_metrics = _aggregate_role_metrics(metrics)
    pred_summary = _predictions_summary(predictions)

    report = _wide_model_report(role_metrics, pred_summary, config)
    report = add_selection_ranks(report, config)

    audit = build_selection_diagnostics(report, metrics, predictions, config)
    return report, audit


def build_selection_diagnostics(
    report: pd.DataFrame,
    metrics: pd.DataFrame,
    predictions: pd.DataFrame | None,
    config: ModelSelectionConfig,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "report_rows", "value": len(report)},
        {"diagnostic": "metric_rows", "value": len(metrics)},
        {"diagnostic": "prediction_rows", "value": 0 if predictions is None else len(predictions)},
        {"diagnostic": "models_ranked", "value": report["model_name"].nunique() if "model_name" in report else 0},
        {"diagnostic": "primary_role", "value": config.primary_role},
        {"diagnostic": "secondary_role", "value": config.secondary_role},
        {"diagnostic": "min_validation_folds", "value": config.min_validation_folds},
    ]

    if not report.empty and "is_primary_model" in report:
        primary = report[report["is_primary_model"] == True]
        if not primary.empty:
            rows.append({"diagnostic": "primary_model", "value": primary.iloc[0]["model_name"]})
            rows.append({"diagnostic": "primary_validation_ic", "value": primary.iloc[0].get(f"{config.primary_role}_mean_spearman_ic")})
            rows.append({"diagnostic": "primary_validation_mae", "value": primary.iloc[0].get(f"{config.primary_role}_mean_mae")})
            rows.append({"diagnostic": "primary_validation_rmse", "value": primary.iloc[0].get(f"{config.primary_role}_mean_rmse")})
            rows.append({"diagnostic": "primary_test_ic", "value": primary.iloc[0].get(f"{config.secondary_role}_mean_spearman_ic")})

    if "status" in metrics.columns:
        for status, count in metrics["status"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"metric_status_{status}", "value": int(count)})

    return pd.DataFrame(rows)


def _fmt(value: Any, digits: int = 6) -> str:
    number = _to_float(value)
    if number is None:
        return ""
    return f"{number:.{digits}f}"


def render_markdown_report(report: pd.DataFrame, diagnostics: pd.DataFrame, config: ModelSelectionConfig) -> str:
    lines: list[str] = [
        "# Model Selection Report",
        "",
        f"Version: `{config.report_version}`",
        "",
    ]

    if report.empty:
        lines.extend(["No models were ranked.", ""])
        return "\n".join(lines)

    primary = report[report["is_primary_model"] == True].iloc[0]
    lines.extend(
        [
            "## Primary model",
            "",
            f"Selected model: `{primary['model_name']}`",
            "",
            "Selection rule v0: rank by validation Spearman IC descending, then validation MAE ascending, then validation RMSE ascending.",
            "",
            "## Ranked models",
            "",
            "| Rank | Model | Val Spearman IC | Val MAE | Val RMSE | Test Spearman IC | Test MAE | Test RMSE |",
            "|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
    )

    for _, row in report.iterrows():
        lines.append(
            "| "
            + f"{int(row['model_selection_rank'])} | "
            + f"{row['model_name']} | "
            + f"{_fmt(row.get(f'{config.primary_role}_mean_spearman_ic'))} | "
            + f"{_fmt(row.get(f'{config.primary_role}_mean_mae'))} | "
            + f"{_fmt(row.get(f'{config.primary_role}_mean_rmse'))} | "
            + f"{_fmt(row.get(f'{config.secondary_role}_mean_spearman_ic'))} | "
            + f"{_fmt(row.get(f'{config.secondary_role}_mean_mae'))} | "
            + f"{_fmt(row.get(f'{config.secondary_role}_mean_rmse'))} |"
        )

    lines.extend(
        [
            "",
            "## Diagnostics",
            "",
            "| Diagnostic | Value |",
            "|---|---:|",
        ]
    )

    for _, row in diagnostics.iterrows():
        lines.append(f"| {row.get('diagnostic', '')} | {row.get('value', '')} |")

    lines.append("")
    return "\n".join(lines)


def write_model_selection_outputs(
    report: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    output_table_path: str | Path,
    output_csv_path: str | Path,
    markdown_report_path: str | Path,
    diagnostics_path: str | Path,
    config: ModelSelectionConfig,
) -> None:
    safe_write_table(report, parquet_path=output_table_path, csv_path=output_csv_path)
    diagnostics_path = Path(diagnostics_path)
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(diagnostics_path, index=False)

    markdown_report_path = Path(markdown_report_path)
    markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_report_path.write_text(render_markdown_report(report, diagnostics, config), encoding="utf-8")


def build_model_selection_report(config: ModelSelectionConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.model_selection_report",
        root() / "logs/pipeline/model_selection_report.log",
    )
    logger.info("Building model selection report from %s", config.baseline_diagnostics_path)
    report, diagnostics = build_model_selection_report_dataframe(config)
    write_model_selection_outputs(
        report,
        diagnostics,
        output_table_path=config.output_table_path,
        output_csv_path=config.output_csv_path,
        markdown_report_path=config.markdown_report_path,
        diagnostics_path=config.diagnostics_path,
        config=config,
    )
    logger.info("Wrote %d model selection rows to %s", len(report), config.output_table_path)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Build baseline model comparison and selection report.")
    parser.add_argument("--baseline-diagnostics-path", default="outputs/diagnostics/baseline_model_diagnostics.csv")
    parser.add_argument("--baseline-predictions-path", default="data/processed/model/baseline_fold_predictions.csv")
    parser.add_argument("--output-table", default="data/processed/model/model_selection_report.parquet")
    parser.add_argument("--output-csv", default="data/processed/model/model_selection_report.csv")
    parser.add_argument("--markdown-report-path", default="outputs/reports/model_selection_report.md")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/model_selection_report_diagnostics.csv")
    parser.add_argument("--primary-role", default=PRIMARY_ROLE)
    parser.add_argument("--secondary-role", default=SECONDARY_ROLE)
    parser.add_argument("--min-validation-folds", type=int, default=1)
    args = parser.parse_args()

    config = ModelSelectionConfig(
        baseline_diagnostics_path=root() / args.baseline_diagnostics_path,
        baseline_predictions_path=root() / args.baseline_predictions_path if args.baseline_predictions_path else None,
        output_table_path=root() / args.output_table,
        output_csv_path=root() / args.output_csv,
        markdown_report_path=root() / args.markdown_report_path,
        diagnostics_path=root() / args.diagnostics_path,
        primary_role=args.primary_role,
        secondary_role=args.secondary_role,
        min_validation_folds=args.min_validation_folds,
    )
    build_model_selection_report(config)


if __name__ == "__main__":
    main()
