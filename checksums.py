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


PORTFOLIO_CONSTRUCTION_VERSION = "PORTFOLIO_CONSTRUCTION_V0"


@dataclass(frozen=True)
class PortfolioConstructionConfig:
    baseline_predictions_path: Path
    model_selection_report_path: Path
    holdings_output_table_path: Path
    holdings_output_csv_path: Path
    returns_output_table_path: Path
    returns_output_csv_path: Path
    diagnostics_path: Path
    rebalance_frequency: str = "M"
    long_quantile: float = 0.9
    short_quantile: float = 0.1
    transaction_cost_bps: float = 10.0
    min_names_per_rebalance: int = 10
    prediction_role: str = "test"
    portfolio_version: str = PORTFOLIO_CONSTRUCTION_VERSION


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


def select_primary_model(model_selection_report: pd.DataFrame) -> str:
    if model_selection_report.empty:
        raise ValueError("model_selection_report is empty.")

    if "is_primary_model" in model_selection_report.columns:
        primary = model_selection_report[
            model_selection_report["is_primary_model"].astype(str).str.lower().isin({"true", "1", "yes"})
        ]
        if not primary.empty:
            return str(primary.iloc[0]["model_name"])

    if "model_selection_rank" in model_selection_report.columns:
        ranked = model_selection_report.copy()
        ranked["model_selection_rank"] = pd.to_numeric(ranked["model_selection_rank"], errors="coerce")
        ranked = ranked.sort_values(["model_selection_rank", "model_name"])
        if not ranked.empty:
            return str(ranked.iloc[0]["model_name"])

    if "model_name" in model_selection_report.columns and not model_selection_report.empty:
        return str(model_selection_report.iloc[0]["model_name"])

    raise ValueError("Could not select primary model.")


def _rebalance_period(date_series: pd.Series, frequency: str) -> pd.Series:
    dates = pd.to_datetime(date_series, errors="coerce")
    freq = frequency.upper()
    if freq == "M":
        return dates.dt.to_period("M").astype(str)
    if freq == "Q":
        return dates.dt.to_period("Q").astype(str)
    raise ValueError(f"Unsupported rebalance frequency: {frequency}")


def _prepare_predictions(predictions: pd.DataFrame, primary_model: str, config: PortfolioConstructionConfig) -> pd.DataFrame:
    required = {"model_name", "walk_forward_role", "y_true", "y_pred", "feature_asof_date"}
    missing = required.difference(predictions.columns)
    if missing:
        raise ValueError(f"baseline_fold_predictions missing required columns: {sorted(missing)}")

    out = predictions.copy()
    out = out[
        (out["model_name"].astype(str) == primary_model)
        & (out["walk_forward_role"].astype(str) == config.prediction_role)
    ].copy()

    out["feature_asof_date"] = pd.to_datetime(out["feature_asof_date"], errors="coerce")
    out["y_true"] = pd.to_numeric(out["y_true"], errors="coerce")
    out["y_pred"] = pd.to_numeric(out["y_pred"], errors="coerce")
    out = out.dropna(subset=["feature_asof_date", "y_true", "y_pred"]).copy()

    if "model_row_id" not in out.columns:
        out["model_row_id"] = out.index.astype(str)
    if "ticker" not in out.columns:
        out["ticker"] = ""
    if "sector" not in out.columns:
        out["sector"] = ""

    out["rebalance_period"] = _rebalance_period(out["feature_asof_date"], config.rebalance_frequency)
    return out.sort_values(["rebalance_period", "y_pred", "model_row_id"]).reset_index(drop=True)


def _assign_rebalance_holdings(group: pd.DataFrame, config: PortfolioConstructionConfig) -> pd.DataFrame:
    out = group.copy()
    n = len(out)
    out["portfolio_leg"] = "excluded"
    out["portfolio_weight"] = 0.0
    out["portfolio_selection_quality_flag"] = "GREEN" if n >= config.min_names_per_rebalance else "RED"
    out["portfolio_selection_quality_notes"] = "" if n >= config.min_names_per_rebalance else f"insufficient_names={n}<min_names_per_rebalance={config.min_names_per_rebalance}"

    if n < config.min_names_per_rebalance:
        return out

    short_count = max(1, int(math.ceil(n * config.short_quantile)))
    long_count = max(1, int(math.ceil(n * (1.0 - config.long_quantile))))
    out = out.sort_values(["y_pred", "model_row_id"]).reset_index(drop=True)

    short_idx = out.index[:short_count]
    long_idx = out.index[-long_count:]

    out.loc[short_idx, "portfolio_leg"] = "short"
    out.loc[short_idx, "portfolio_weight"] = -1.0 / short_count
    out.loc[long_idx, "portfolio_leg"] = "long"
    out.loc[long_idx, "portfolio_weight"] = 1.0 / long_count

    out["portfolio_rank_pct"] = out["y_pred"].rank(method="first", pct=True)
    return out


def build_portfolio_holdings_dataframe(config: PortfolioConstructionConfig) -> pd.DataFrame:
    predictions = read_table(config.baseline_predictions_path)
    selection_report = read_table(config.model_selection_report_path)
    primary_model = select_primary_model(selection_report)
    prepared = _prepare_predictions(predictions, primary_model, config)

    if prepared.empty:
        return pd.DataFrame()

    parts = []
    for _, group in prepared.groupby("rebalance_period", sort=True):
        parts.append(_assign_rebalance_holdings(group, config))

    holdings = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if holdings.empty:
        return holdings

    holdings["primary_model_name"] = primary_model
    holdings["transaction_cost_bps"] = config.transaction_cost_bps
    holdings["portfolio_version"] = config.portfolio_version
    holdings["gross_position_abs"] = holdings["portfolio_weight"].abs()
    holdings["weighted_forward_return"] = holdings["portfolio_weight"] * holdings["y_true"]

    core = [
        "rebalance_period",
        "walk_forward_fold_id",
        "primary_model_name",
        "model_name",
        "model_row_id",
        "panel_row_id",
        "cik",
        "cik10",
        "ticker",
        "sector",
        "accession_number",
        "primary_document",
        "feature_asof_date",
        "y_pred",
        "y_true",
        "portfolio_rank_pct",
        "portfolio_leg",
        "portfolio_weight",
        "gross_position_abs",
        "weighted_forward_return",
        "portfolio_selection_quality_flag",
        "portfolio_selection_quality_notes",
        "transaction_cost_bps",
        "portfolio_version",
    ]
    for col in core:
        if col not in holdings.columns:
            holdings[col] = ""
    return holdings[core + [c for c in holdings.columns if c not in core]].sort_values(
        ["rebalance_period", "portfolio_leg", "y_pred", "model_row_id"]
    ).reset_index(drop=True)


def _turnover_for_period(current: pd.DataFrame, previous_weights: dict[str, float]) -> float:
    current_weights = dict(zip(current["model_row_id"].astype(str), current["portfolio_weight"].astype(float)))
    keys = set(current_weights).union(previous_weights)
    if not keys:
        return 0.0
    gross_change = sum(abs(current_weights.get(k, 0.0) - previous_weights.get(k, 0.0)) for k in keys)
    return 0.5 * gross_change


def build_portfolio_returns_dataframe(holdings: pd.DataFrame, config: PortfolioConstructionConfig) -> pd.DataFrame:
    if holdings.empty:
        return pd.DataFrame()

    investable = holdings[holdings["portfolio_leg"].isin(["long", "short"])].copy()
    if investable.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    previous_weights: dict[str, float] = {}

    for period, group in investable.groupby("rebalance_period", sort=True):
        group = group.copy()
        turnover = _turnover_for_period(group, previous_weights)
        cost = turnover * (config.transaction_cost_bps / 10_000.0)

        gross_return = group["weighted_forward_return"].sum()
        net_return = gross_return - cost

        long = group[group["portfolio_leg"] == "long"]
        short = group[group["portfolio_leg"] == "short"]

        long_return = (long["portfolio_weight"] * long["y_true"]).sum() if not long.empty else None
        short_return = (short["portfolio_weight"] * short["y_true"]).sum() if not short.empty else None
        # Since short weights are negative, positive short_return means short leg made money.
        long_avg_forward_return = long["y_true"].mean() if not long.empty else None
        short_avg_forward_return = short["y_true"].mean() if not short.empty else None

        quality_flags = sorted(set(group["portfolio_selection_quality_flag"].astype(str)))
        quality_flag = "RED" if "RED" in quality_flags else ("YELLOW" if "YELLOW" in quality_flags else "GREEN")
        quality_notes = ";".join(sorted(set(group["portfolio_selection_quality_notes"].astype(str)) - {""}))

        rows.append(
            {
                "rebalance_period": period,
                "primary_model_name": group["primary_model_name"].iloc[0],
                "portfolio_gross_return": round(float(gross_return), 12),
                "portfolio_turnover": round(float(turnover), 12),
                "transaction_cost_bps": config.transaction_cost_bps,
                "transaction_cost_return": round(float(cost), 12),
                "portfolio_net_return": round(float(net_return), 12),
                "long_leg_contribution": round(float(long_return), 12) if long_return is not None else None,
                "short_leg_contribution": round(float(short_return), 12) if short_return is not None else None,
                "long_avg_forward_return": round(float(long_avg_forward_return), 12) if long_avg_forward_return is not None else None,
                "short_avg_forward_return": round(float(short_avg_forward_return), 12) if short_avg_forward_return is not None else None,
                "long_count": int(len(long)),
                "short_count": int(len(short)),
                "gross_exposure": round(float(group["portfolio_weight"].abs().sum()), 12),
                "net_exposure": round(float(group["portfolio_weight"].sum()), 12),
                "portfolio_quality_flag": quality_flag,
                "portfolio_quality_notes": quality_notes,
                "portfolio_version": config.portfolio_version,
            }
        )
        previous_weights = dict(zip(group["model_row_id"].astype(str), group["portfolio_weight"].astype(float)))

    return pd.DataFrame(rows)


def build_portfolio_diagnostics(holdings: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "holding_rows", "value": len(holdings)},
        {"diagnostic": "return_rows", "value": len(returns)},
    ]

    if not holdings.empty:
        rows.extend(
            [
                {"diagnostic": "rebalance_periods", "value": holdings["rebalance_period"].nunique()},
                {"diagnostic": "primary_model_name", "value": holdings["primary_model_name"].iloc[0]},
                {"diagnostic": "long_holdings", "value": int((holdings["portfolio_leg"] == "long").sum())},
                {"diagnostic": "short_holdings", "value": int((holdings["portfolio_leg"] == "short").sum())},
                {"diagnostic": "excluded_holdings", "value": int((holdings["portfolio_leg"] == "excluded").sum())},
            ]
        )
        for flag, count in holdings["portfolio_selection_quality_flag"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"holding_quality_flag_{flag}", "value": int(count)})

    if not returns.empty:
        rows.extend(
            [
                {"diagnostic": "mean_gross_return", "value": returns["portfolio_gross_return"].mean()},
                {"diagnostic": "mean_net_return", "value": returns["portfolio_net_return"].mean()},
                {"diagnostic": "mean_turnover", "value": returns["portfolio_turnover"].mean()},
                {"diagnostic": "mean_transaction_cost_return", "value": returns["transaction_cost_return"].mean()},
            ]
        )
        for flag, count in returns["portfolio_quality_flag"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"portfolio_quality_flag_{flag}", "value": int(count)})

    return pd.DataFrame(rows)


def write_portfolio_outputs(
    holdings: pd.DataFrame,
    returns: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    holdings_output_table_path: str | Path,
    holdings_output_csv_path: str | Path,
    returns_output_table_path: str | Path,
    returns_output_csv_path: str | Path,
    diagnostics_path: str | Path,
) -> None:
    safe_write_table(holdings, parquet_path=holdings_output_table_path, csv_path=holdings_output_csv_path)
    safe_write_table(returns, parquet_path=returns_output_table_path, csv_path=returns_output_csv_path)
    diagnostics_path = Path(diagnostics_path)
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(diagnostics_path, index=False)


def build_long_short_decile_portfolio(config: PortfolioConstructionConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger = get_logger(
        "fvn_dfm.portfolio_construction",
        root() / "logs/pipeline/portfolio_construction.log",
    )
    logger.info("Building portfolio from %s", config.baseline_predictions_path)
    holdings = build_portfolio_holdings_dataframe(config)
    returns = build_portfolio_returns_dataframe(holdings, config)
    diagnostics = build_portfolio_diagnostics(holdings, returns)
    write_portfolio_outputs(
        holdings,
        returns,
        diagnostics,
        holdings_output_table_path=config.holdings_output_table_path,
        holdings_output_csv_path=config.holdings_output_csv_path,
        returns_output_table_path=config.returns_output_table_path,
        returns_output_csv_path=config.returns_output_csv_path,
        diagnostics_path=config.diagnostics_path,
    )
    logger.info("Wrote %d holdings and %d return rows", len(holdings), len(returns))
    return holdings, returns


def main() -> None:
    parser = argparse.ArgumentParser(description="Build long-short decile portfolios from primary-model predictions.")
    parser.add_argument("--baseline-predictions-path", default="data/processed/model/baseline_fold_predictions.csv")
    parser.add_argument("--model-selection-report-path", default="data/processed/model/model_selection_report.csv")
    parser.add_argument("--holdings-output-table", default="data/processed/portfolio/portfolio_holdings.parquet")
    parser.add_argument("--holdings-output-csv", default="data/processed/portfolio/portfolio_holdings.csv")
    parser.add_argument("--returns-output-table", default="data/processed/portfolio/portfolio_monthly_returns.parquet")
    parser.add_argument("--returns-output-csv", default="data/processed/portfolio/portfolio_monthly_returns.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/portfolio_construction_diagnostics.csv")
    parser.add_argument("--transaction-cost-bps", type=float, default=10.0)
    parser.add_argument("--min-names-per-rebalance", type=int, default=10)
    parser.add_argument("--prediction-role", default="test")
    parser.add_argument("--long-quantile", type=float, default=0.9)
    parser.add_argument("--short-quantile", type=float, default=0.1)
    args = parser.parse_args()

    config = PortfolioConstructionConfig(
        baseline_predictions_path=root() / args.baseline_predictions_path,
        model_selection_report_path=root() / args.model_selection_report_path,
        holdings_output_table_path=root() / args.holdings_output_table,
        holdings_output_csv_path=root() / args.holdings_output_csv,
        returns_output_table_path=root() / args.returns_output_table,
        returns_output_csv_path=root() / args.returns_output_csv,
        diagnostics_path=root() / args.diagnostics_path,
        transaction_cost_bps=args.transaction_cost_bps,
        min_names_per_rebalance=args.min_names_per_rebalance,
        prediction_role=args.prediction_role,
        long_quantile=args.long_quantile,
        short_quantile=args.short_quantile,
    )
    build_long_short_decile_portfolio(config)


if __name__ == "__main__":
    main()
