from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.portfolio.portfolio_construction import (
    PortfolioConstructionConfig,
    build_portfolio_diagnostics,
    build_portfolio_returns_dataframe,
)
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


ABLATION_STUDY_VERSION = "ABLATION_STUDY_V0"

TARGET_COLUMN = "y_forward_63d_sector_adjusted_return"

ABLATION_DEFINITIONS: dict[str, dict[str, Any]] = {
    "dfm_score": {
        "description": "Disclosure-Fundamental Mismatch score.",
        "candidate_columns": ["dfm_score_simple", "net_mismatch_score"],
        "direction": 1.0,
    },
    "fundamentals_only": {
        "description": "Hard-accounting reality signal without disclosure text interactions.",
        "candidate_columns": [
            "fundamental_reality_score",
            "fund_net_improvement_score",
            "fund_improve_score",
            "fund_stress_score",
        ],
        "direction": 1.0,
        "negative_columns": ["fund_stress_score"],
    },
    "text_only": {
        "description": "Disclosure text tone proxy without hard-accounting interaction.",
        "candidate_columns": [
            "text_full_lm_pos_neg_balance",
            "full_lm_pos_neg_balance",
            "text_mda_lm_pos_neg_balance",
            "mda_lm_pos_neg_balance",
            "text_full_lm_positive_share",
            "full_lm_positive_share",
        ],
        "direction": 1.0,
    },
    "naive_baseline": {
        "description": "Naive zero prediction baseline.",
        "candidate_columns": [],
        "direction": 0.0,
    },
}


@dataclass(frozen=True)
class AblationStudyConfig:
    model_dataset_with_splits_path: Path
    predictions_output_table_path: Path
    predictions_output_csv_path: Path
    metrics_output_table_path: Path
    metrics_output_csv_path: Path
    portfolio_returns_output_table_path: Path
    portfolio_returns_output_csv_path: Path
    summary_output_table_path: Path
    summary_output_csv_path: Path
    markdown_report_path: Path
    diagnostics_path: Path
    target_column: str = TARGET_COLUMN
    prediction_role: str = "test"
    transaction_cost_bps: float = 10.0
    min_names_per_rebalance: int = 10
    long_quantile: float = 0.9
    short_quantile: float = 0.1
    min_eval_rows: int = 2
    ablation_version: str = ABLATION_STUDY_VERSION


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


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _first_existing_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _prediction_series(df: pd.DataFrame, ablation_name: str) -> tuple[pd.Series, str, str]:
    definition = ABLATION_DEFINITIONS[ablation_name]
    if ablation_name == "naive_baseline":
        return pd.Series(0.0, index=df.index), "constant_zero", ""

    selected = _first_existing_column(df, definition["candidate_columns"])
    if selected is None:
        return pd.Series(np.nan, index=df.index), "", "missing_ablation_source_column"

    values = pd.to_numeric(df[selected], errors="coerce")

    # Invert explicitly negative source columns when they are used as the only available proxy.
    direction = float(definition.get("direction", 1.0))
    if selected in set(definition.get("negative_columns", [])):
        direction *= -1.0

    return values * direction, selected, ""


def _safe_corr(y_true: pd.Series, y_pred: pd.Series, method: str) -> float | None:
    valid = y_true.notna() & y_pred.notna()
    if valid.sum() < 2:
        return None
    value = y_true[valid].corr(y_pred[valid], method=method)
    if pd.isna(value):
        return None
    return float(value)


def _rank_ic(y_true: pd.Series, y_pred: pd.Series) -> float | None:
    return _safe_corr(y_true, y_pred, "spearman")


def _pearson_ic(y_true: pd.Series, y_pred: pd.Series) -> float | None:
    return _safe_corr(y_true, y_pred, "pearson")


def _error_metrics(y_true: pd.Series, y_pred: pd.Series) -> tuple[float | None, float | None]:
    valid = y_true.notna() & y_pred.notna()
    if valid.sum() == 0:
        return None, None
    err = y_pred[valid] - y_true[valid]
    mae = float(err.abs().mean())
    rmse = float(math.sqrt((err ** 2).mean()))
    return mae, rmse


def _prepare_source(df: pd.DataFrame, config: AblationStudyConfig) -> pd.DataFrame:
    out = df.copy()
    if "walk_forward_role" not in out.columns:
        raise ValueError("model_dataset_with_splits requires walk_forward_role.")
    if "walk_forward_fold_id" not in out.columns:
        raise ValueError("model_dataset_with_splits requires walk_forward_fold_id.")
    if config.target_column not in out.columns:
        raise ValueError(f"model_dataset_with_splits missing target column: {config.target_column}")

    out = out[out["walk_forward_role"].astype(str) == config.prediction_role].copy()
    if "model_dataset_eligible" in out.columns:
        out = out[out["model_dataset_eligible"].map(_as_bool)].copy()
    out[config.target_column] = pd.to_numeric(out[config.target_column], errors="coerce")
    out = out.dropna(subset=[config.target_column]).copy()
    return out.reset_index(drop=True)


def build_ablation_predictions_dataframe(config: AblationStudyConfig) -> pd.DataFrame:
    source = _prepare_source(read_table(config.model_dataset_with_splits_path), config)
    if source.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for ablation_name, definition in ABLATION_DEFINITIONS.items():
        preds, source_col, warning = _prediction_series(source, ablation_name)
        for idx, row in source.iterrows():
            pred = _to_float(preds.loc[idx])
            y_true = _to_float(row.get(config.target_column))
            rows.append(
                {
                    "ablation_name": ablation_name,
                    "ablation_description": definition["description"],
                    "ablation_source_column": source_col,
                    "ablation_warning": warning,
                    "ablation_version": config.ablation_version,
                    "walk_forward_fold_id": row.get("walk_forward_fold_id", ""),
                    "walk_forward_role": row.get("walk_forward_role", ""),
                    "model_row_id": row.get("model_row_id", ""),
                    "panel_row_id": row.get("panel_row_id", ""),
                    "cik": row.get("cik", ""),
                    "cik10": row.get("cik10", ""),
                    "ticker": row.get("ticker", ""),
                    "sector": row.get("sector", ""),
                    "accession_number": row.get("accession_number", ""),
                    "primary_document": row.get("primary_document", ""),
                    "feature_asof_date": row.get("feature_asof_date", ""),
                    "target_column": config.target_column,
                    "y_true": y_true,
                    "y_pred": pred,
                    "prediction_error": pred - y_true if pred is not None and y_true is not None else None,
                }
            )

    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["ablation_name", "walk_forward_fold_id", "feature_asof_date", "model_row_id"]).reset_index(drop=True)
    return out


def build_ablation_metrics_dataframe(predictions: pd.DataFrame, config: AblationStudyConfig) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for (ablation_name, fold_id), group in predictions.groupby(["ablation_name", "walk_forward_fold_id"], sort=True):
        y_true = pd.to_numeric(group["y_true"], errors="coerce")
        y_pred = pd.to_numeric(group["y_pred"], errors="coerce")
        valid = y_true.notna() & y_pred.notna()
        n_valid = int(valid.sum())

        mae, rmse = _error_metrics(y_true, y_pred)
        rows.append(
            {
                "ablation_name": ablation_name,
                "walk_forward_fold_id": fold_id,
                "walk_forward_role": config.prediction_role,
                "status": "success" if n_valid >= config.min_eval_rows else "skipped",
                "notes": "" if n_valid >= config.min_eval_rows else f"insufficient_eval_rows={n_valid}<min_eval_rows={config.min_eval_rows}",
                "n_rows": n_valid,
                "target_column": config.target_column,
                "spearman_ic": _rank_ic(y_true, y_pred),
                "pearson_ic": _pearson_ic(y_true, y_pred),
                "mae": mae,
                "rmse": rmse,
                "mean_y_true": float(y_true[valid].mean()) if n_valid else None,
                "mean_y_pred": float(y_pred[valid].mean()) if n_valid else None,
                "ablation_version": config.ablation_version,
            }
        )

    return pd.DataFrame(rows)


def _convert_predictions_to_portfolio_input(predictions: pd.DataFrame, ablation_name: str) -> pd.DataFrame:
    subset = predictions[predictions["ablation_name"] == ablation_name].copy()
    if subset.empty:
        return subset
    subset["model_name"] = ablation_name
    subset["primary_model_name"] = ablation_name
    return subset


def build_ablation_portfolio_returns_dataframe(predictions: pd.DataFrame, config: AblationStudyConfig) -> pd.DataFrame:
    if predictions.empty:
        return pd.DataFrame()

    all_returns: list[pd.DataFrame] = []
    for ablation_name in sorted(predictions["ablation_name"].unique()):
        subset = _convert_predictions_to_portfolio_input(predictions, ablation_name)
        if subset.empty:
            continue

        # Reuse the same long/short decile return engine by constructing holdings-equivalent fields.
        temp_holdings = _build_ablation_holdings(subset, config)
        temp_returns = build_portfolio_returns_dataframe(
            temp_holdings,
            PortfolioConstructionConfig(
                baseline_predictions_path=Path("unused.csv"),
                model_selection_report_path=Path("unused.csv"),
                holdings_output_table_path=Path("unused.parquet"),
                holdings_output_csv_path=Path("unused.csv"),
                returns_output_table_path=Path("unused.parquet"),
                returns_output_csv_path=Path("unused.csv"),
                diagnostics_path=Path("unused.csv"),
                transaction_cost_bps=config.transaction_cost_bps,
                min_names_per_rebalance=config.min_names_per_rebalance,
                long_quantile=config.long_quantile,
                short_quantile=config.short_quantile,
            ),
        )
        if not temp_returns.empty:
            temp_returns["ablation_name"] = ablation_name
            all_returns.append(temp_returns)

    if not all_returns:
        return pd.DataFrame()
    out = pd.concat(all_returns, ignore_index=True)
    return out.sort_values(["ablation_name", "rebalance_period"]).reset_index(drop=True)


def _rebalance_period(date_series: pd.Series) -> pd.Series:
    dates = pd.to_datetime(date_series, errors="coerce")
    return dates.dt.to_period("M").astype(str)


def _build_ablation_holdings(predictions: pd.DataFrame, config: AblationStudyConfig) -> pd.DataFrame:
    out = predictions.copy()
    out["feature_asof_date"] = pd.to_datetime(out["feature_asof_date"], errors="coerce")
    out["rebalance_period"] = _rebalance_period(out["feature_asof_date"])
    out["portfolio_leg"] = "excluded"
    out["portfolio_weight"] = 0.0
    out["portfolio_selection_quality_flag"] = "GREEN"
    out["portfolio_selection_quality_notes"] = ""

    parts: list[pd.DataFrame] = []
    for _, group in out.groupby("rebalance_period", sort=True):
        g = group.copy()
        n = len(g)
        if n < config.min_names_per_rebalance:
            g["portfolio_selection_quality_flag"] = "RED"
            g["portfolio_selection_quality_notes"] = f"insufficient_names={n}<min_names_per_rebalance={config.min_names_per_rebalance}"
            parts.append(g)
            continue

        g = g.sort_values(["y_pred", "model_row_id"]).reset_index(drop=True)
        short_count = max(1, int(math.ceil(n * config.short_quantile)))
        long_count = max(1, int(math.ceil(n * (1.0 - config.long_quantile))))
        short_idx = g.index[:short_count]
        long_idx = g.index[-long_count:]

        g.loc[short_idx, "portfolio_leg"] = "short"
        g.loc[short_idx, "portfolio_weight"] = -1.0 / short_count
        g.loc[long_idx, "portfolio_leg"] = "long"
        g.loc[long_idx, "portfolio_weight"] = 1.0 / long_count
        g["portfolio_rank_pct"] = g["y_pred"].rank(method="first", pct=True)
        parts.append(g)

    holdings = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if holdings.empty:
        return holdings

    holdings["primary_model_name"] = holdings["ablation_name"]
    holdings["transaction_cost_bps"] = config.transaction_cost_bps
    holdings["portfolio_version"] = f"{config.ablation_version}_PORTFOLIO"
    holdings["gross_position_abs"] = holdings["portfolio_weight"].abs()
    holdings["weighted_forward_return"] = holdings["portfolio_weight"] * holdings["y_true"]
    return holdings


def build_ablation_summary_dataframe(
    metrics: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    config: AblationStudyConfig,
) -> pd.DataFrame:
    if metrics.empty:
        return pd.DataFrame()

    success = metrics[metrics["status"] == "success"].copy()
    rows: list[dict[str, Any]] = []

    for ablation_name in sorted(metrics["ablation_name"].unique()):
        m = success[success["ablation_name"] == ablation_name]
        p = portfolio_returns[portfolio_returns["ablation_name"] == ablation_name].copy() if not portfolio_returns.empty else pd.DataFrame()

        net = pd.to_numeric(p["portfolio_net_return"], errors="coerce") if not p.empty and "portfolio_net_return" in p else pd.Series(dtype=float)
        gross = pd.to_numeric(p["portfolio_gross_return"], errors="coerce") if not p.empty and "portfolio_gross_return" in p else pd.Series(dtype=float)
        turnover = pd.to_numeric(p["portfolio_turnover"], errors="coerce") if not p.empty and "portfolio_turnover" in p else pd.Series(dtype=float)
        costs = pd.to_numeric(p["transaction_cost_return"], errors="coerce") if not p.empty and "transaction_cost_return" in p else pd.Series(dtype=float)

        cumulative_net = (1.0 + net.dropna()).prod() - 1.0 if not net.dropna().empty else None
        cumulative_gross = (1.0 + gross.dropna()).prod() - 1.0 if not gross.dropna().empty else None

        rows.append(
            {
                "ablation_name": ablation_name,
                "ablation_description": ABLATION_DEFINITIONS[ablation_name]["description"],
                "folds_success": int(m["walk_forward_fold_id"].nunique()) if not m.empty else 0,
                "mean_spearman_ic": m["spearman_ic"].mean() if not m.empty else None,
                "median_spearman_ic": m["spearman_ic"].median() if not m.empty else None,
                "mean_pearson_ic": m["pearson_ic"].mean() if not m.empty else None,
                "mean_mae": m["mae"].mean() if not m.empty else None,
                "mean_rmse": m["rmse"].mean() if not m.empty else None,
                "portfolio_periods": int(len(p)),
                "portfolio_cumulative_gross_return": cumulative_gross,
                "portfolio_cumulative_net_return": cumulative_net,
                "portfolio_mean_net_return": net.mean() if not net.empty else None,
                "portfolio_hit_rate": float((net > 0).mean()) if not net.empty else None,
                "portfolio_mean_turnover": turnover.mean() if not turnover.empty else None,
                "portfolio_total_transaction_cost": costs.sum() if not costs.empty else None,
                "ablation_version": config.ablation_version,
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return out

    out["rank_ic"] = pd.to_numeric(out["mean_spearman_ic"], errors="coerce").fillna(-1e9).rank(method="min", ascending=False)
    out["rank_mae"] = pd.to_numeric(out["mean_mae"], errors="coerce").fillna(1e9).rank(method="min", ascending=True)
    out["rank_portfolio_net"] = pd.to_numeric(out["portfolio_cumulative_net_return"], errors="coerce").fillna(-1e9).rank(method="min", ascending=False)
    out["ablation_score_rank"] = (out["rank_ic"] * 10.0 + out["rank_mae"] * 2.0 + out["rank_portfolio_net"]).rank(method="first", ascending=True)
    out = out.sort_values(["ablation_score_rank", "ablation_name"]).reset_index(drop=True)
    return out


def build_ablation_diagnostics(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    summary: pd.DataFrame,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "prediction_rows", "value": len(predictions)},
        {"diagnostic": "metric_rows", "value": len(metrics)},
        {"diagnostic": "portfolio_return_rows", "value": len(portfolio_returns)},
        {"diagnostic": "summary_rows", "value": len(summary)},
    ]

    if not predictions.empty:
        rows.append({"diagnostic": "ablation_count", "value": predictions["ablation_name"].nunique()})
        for ablation, count in predictions["ablation_name"].value_counts().items():
            rows.append({"diagnostic": f"prediction_rows_{ablation}", "value": int(count)})

    if not metrics.empty and "status" in metrics:
        for status, count in metrics["status"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"metric_status_{status}", "value": int(count)})

    if not summary.empty:
        top = summary.iloc[0]
        rows.append({"diagnostic": "top_ablation_by_score", "value": top["ablation_name"]})
        rows.append({"diagnostic": "dfm_mean_spearman_ic", "value": summary.loc[summary["ablation_name"] == "dfm_score", "mean_spearman_ic"].iloc[0] if "dfm_score" in set(summary["ablation_name"]) else None})
        rows.append({"diagnostic": "dfm_portfolio_cumulative_net_return", "value": summary.loc[summary["ablation_name"] == "dfm_score", "portfolio_cumulative_net_return"].iloc[0] if "dfm_score" in set(summary["ablation_name"]) else None})

    return pd.DataFrame(rows)


def _fmt(value: Any, digits: int = 6) -> str:
    number = _to_float(value)
    if number is None:
        return "" if value is None else str(value)
    return f"{number:.{digits}f}"


def render_markdown_report(summary: pd.DataFrame, diagnostics: pd.DataFrame, config: AblationStudyConfig) -> str:
    lines = [
        "# Ablation Study Report",
        "",
        f"Version: `{config.ablation_version}`",
        "",
        "## Ranked ablations",
        "",
        "| Rank | Ablation | Mean Spearman IC | Mean MAE | Mean RMSE | Portfolio cumulative net | Hit rate | Mean turnover |",
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]

    if not summary.empty:
        for _, row in summary.iterrows():
            lines.append(
                "| "
                + f"{int(row['ablation_score_rank'])} | "
                + f"{row['ablation_name']} | "
                + f"{_fmt(row.get('mean_spearman_ic'))} | "
                + f"{_fmt(row.get('mean_mae'))} | "
                + f"{_fmt(row.get('mean_rmse'))} | "
                + f"{_fmt(row.get('portfolio_cumulative_net_return'))} | "
                + f"{_fmt(row.get('portfolio_hit_rate'))} | "
                + f"{_fmt(row.get('portfolio_mean_turnover'))} |"
            )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "This v0 report compares the DFM score against fundamentals-only, text-only, and naive baselines using the same test rows and the same long-short decile construction rule.",
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


def write_ablation_outputs(
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    portfolio_returns: pd.DataFrame,
    summary: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    config: AblationStudyConfig,
) -> None:
    safe_write_table(predictions, parquet_path=config.predictions_output_table_path, csv_path=config.predictions_output_csv_path)
    safe_write_table(metrics, parquet_path=config.metrics_output_table_path, csv_path=config.metrics_output_csv_path)
    safe_write_table(portfolio_returns, parquet_path=config.portfolio_returns_output_table_path, csv_path=config.portfolio_returns_output_csv_path)
    safe_write_table(summary, parquet_path=config.summary_output_table_path, csv_path=config.summary_output_csv_path)

    config.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(config.diagnostics_path, index=False)

    config.markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
    config.markdown_report_path.write_text(render_markdown_report(summary, diagnostics, config), encoding="utf-8")


def build_ablation_study(config: AblationStudyConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.ablation_study",
        root() / "logs/pipeline/ablation_study.log",
    )
    logger.info("Building ablation study from %s", config.model_dataset_with_splits_path)

    predictions = build_ablation_predictions_dataframe(config)
    metrics = build_ablation_metrics_dataframe(predictions, config)
    portfolio_returns = build_ablation_portfolio_returns_dataframe(predictions, config)
    summary = build_ablation_summary_dataframe(metrics, portfolio_returns, config)
    diagnostics = build_ablation_diagnostics(predictions, metrics, portfolio_returns, summary)

    write_ablation_outputs(
        predictions,
        metrics,
        portfolio_returns,
        summary,
        diagnostics,
        config=config,
    )

    logger.info("Wrote ablation study with %d summary rows", len(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ablation study v0.")
    parser.add_argument("--model-dataset-with-splits-path", default="data/processed/model/model_dataset_with_splits.csv")
    parser.add_argument("--predictions-output-table", default="data/processed/model/ablation_predictions.parquet")
    parser.add_argument("--predictions-output-csv", default="data/processed/model/ablation_predictions.csv")
    parser.add_argument("--metrics-output-table", default="data/processed/model/ablation_metrics.parquet")
    parser.add_argument("--metrics-output-csv", default="data/processed/model/ablation_metrics.csv")
    parser.add_argument("--portfolio-returns-output-table", default="data/processed/portfolio/ablation_portfolio_returns.parquet")
    parser.add_argument("--portfolio-returns-output-csv", default="data/processed/portfolio/ablation_portfolio_returns.csv")
    parser.add_argument("--summary-output-table", default="data/processed/model/ablation_summary.parquet")
    parser.add_argument("--summary-output-csv", default="data/processed/model/ablation_summary.csv")
    parser.add_argument("--markdown-report-path", default="outputs/reports/ablation_study_report.md")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/ablation_study_diagnostics.csv")
    parser.add_argument("--target-column", default=TARGET_COLUMN)
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--min-names-per-rebalance", type=int, default=10)
    parser.add_argument("--min-eval-rows", type=int, default=2)
    args = parser.parse_args()

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
        markdown_report_path=root() / args.markdown_report_path,
        diagnostics_path=root() / args.diagnostics_path,
        target_column=args.target_column,
        transaction_cost_bps=args.transaction_cost_bps,
        min_names_per_rebalance=args.min_names_per_rebalance,
        min_eval_rows=args.min_eval_rows,
    )
    build_ablation_study(config)


if __name__ == "__main__":
    main()
