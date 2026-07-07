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


PORTFOLIO_PERFORMANCE_REPORT_VERSION = "PORTFOLIO_PERFORMANCE_REPORT_V0"


@dataclass(frozen=True)
class PortfolioPerformanceConfig:
    portfolio_returns_path: Path
    summary_output_table_path: Path
    summary_output_csv_path: Path
    monthly_output_table_path: Path
    monthly_output_csv_path: Path
    markdown_report_path: Path
    diagnostics_path: Path
    annualization_periods: int = 12
    report_version: str = PORTFOLIO_PERFORMANCE_REPORT_VERSION


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


def _safe_std(series: pd.Series) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 2:
        return None
    value = clean.std(ddof=1)
    if pd.isna(value) or value == 0:
        return None
    return float(value)


def _annualized_return(period_returns: pd.Series, periods_per_year: int) -> float | None:
    clean = pd.to_numeric(period_returns, errors="coerce").dropna()
    if clean.empty:
        return None
    cumulative = (1.0 + clean).prod() - 1.0
    years = len(clean) / periods_per_year
    if years <= 0:
        return None
    if cumulative <= -1.0:
        return -1.0
    return (1.0 + cumulative) ** (1.0 / years) - 1.0


def _sharpe(period_returns: pd.Series, periods_per_year: int) -> float | None:
    clean = pd.to_numeric(period_returns, errors="coerce").dropna()
    if len(clean) < 2:
        return None
    std = clean.std(ddof=1)
    if pd.isna(std) or std == 0:
        return None
    return float(clean.mean() / std * math.sqrt(periods_per_year))


def _sortino(period_returns: pd.Series, periods_per_year: int) -> float | None:
    clean = pd.to_numeric(period_returns, errors="coerce").dropna()
    if len(clean) < 2:
        return None
    downside = clean[clean < 0]
    if len(downside) < 2:
        return None
    downside_std = downside.std(ddof=1)
    if pd.isna(downside_std) or downside_std == 0:
        return None
    return float(clean.mean() / downside_std * math.sqrt(periods_per_year))


def _max_drawdown(cumulative_index: pd.Series) -> float | None:
    clean = pd.to_numeric(cumulative_index, errors="coerce").dropna()
    if clean.empty:
        return None
    running_max = clean.cummax()
    drawdown = clean / running_max - 1.0
    return float(drawdown.min())


def _hit_rate(period_returns: pd.Series) -> float | None:
    clean = pd.to_numeric(period_returns, errors="coerce").dropna()
    if clean.empty:
        return None
    return float((clean > 0).mean())


def _profit_factor(period_returns: pd.Series) -> float | None:
    clean = pd.to_numeric(period_returns, errors="coerce").dropna()
    if clean.empty:
        return None
    gains = clean[clean > 0].sum()
    losses = -clean[clean < 0].sum()
    if losses == 0:
        return None
    return float(gains / losses)


def _round_or_none(value: float | int | None, digits: int = 12) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    return round(float(value), digits)


def prepare_portfolio_returns(df: pd.DataFrame) -> pd.DataFrame:
    required = {"rebalance_period", "portfolio_gross_return", "portfolio_net_return"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"portfolio_monthly_returns missing required columns: {sorted(missing)}")

    out = df.copy()
    out["portfolio_gross_return"] = pd.to_numeric(out["portfolio_gross_return"], errors="coerce")
    out["portfolio_net_return"] = pd.to_numeric(out["portfolio_net_return"], errors="coerce")

    optional_numeric = [
        "portfolio_turnover",
        "transaction_cost_return",
        "long_leg_contribution",
        "short_leg_contribution",
        "long_avg_forward_return",
        "short_avg_forward_return",
        "long_count",
        "short_count",
        "gross_exposure",
        "net_exposure",
    ]
    for col in optional_numeric:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        else:
            out[col] = pd.NA

    if "portfolio_quality_flag" not in out.columns:
        out["portfolio_quality_flag"] = ""
    if "primary_model_name" not in out.columns:
        out["primary_model_name"] = ""

    out = out.dropna(subset=["portfolio_gross_return", "portfolio_net_return"]).copy()
    out = out.sort_values("rebalance_period").reset_index(drop=True)
    return out


def build_monthly_diagnostics_dataframe(portfolio_returns: pd.DataFrame) -> pd.DataFrame:
    df = prepare_portfolio_returns(portfolio_returns)
    if df.empty:
        return pd.DataFrame()

    out = df.copy()
    out["gross_growth_multiplier"] = 1.0 + out["portfolio_gross_return"]
    out["net_growth_multiplier"] = 1.0 + out["portfolio_net_return"]
    out["cumulative_gross_index"] = out["gross_growth_multiplier"].cumprod()
    out["cumulative_net_index"] = out["net_growth_multiplier"].cumprod()
    out["cumulative_gross_return"] = out["cumulative_gross_index"] - 1.0
    out["cumulative_net_return"] = out["cumulative_net_index"] - 1.0

    out["gross_running_peak"] = out["cumulative_gross_index"].cummax()
    out["net_running_peak"] = out["cumulative_net_index"].cummax()
    out["gross_drawdown"] = out["cumulative_gross_index"] / out["gross_running_peak"] - 1.0
    out["net_drawdown"] = out["cumulative_net_index"] / out["net_running_peak"] - 1.0

    out["cost_drag_period"] = out["portfolio_gross_return"] - out["portfolio_net_return"]
    out["cumulative_cost_drag"] = out["cumulative_gross_return"] - out["cumulative_net_return"]
    out["net_return_positive"] = out["portfolio_net_return"] > 0
    out["gross_return_positive"] = out["portfolio_gross_return"] > 0
    out["performance_report_version"] = PORTFOLIO_PERFORMANCE_REPORT_VERSION

    ordered = [
        "rebalance_period",
        "primary_model_name",
        "portfolio_gross_return",
        "portfolio_net_return",
        "transaction_cost_return",
        "portfolio_turnover",
        "cost_drag_period",
        "cumulative_gross_return",
        "cumulative_net_return",
        "cumulative_cost_drag",
        "gross_drawdown",
        "net_drawdown",
        "net_return_positive",
        "long_leg_contribution",
        "short_leg_contribution",
        "long_avg_forward_return",
        "short_avg_forward_return",
        "long_count",
        "short_count",
        "gross_exposure",
        "net_exposure",
        "portfolio_quality_flag",
        "portfolio_quality_notes",
        "performance_report_version",
    ]
    float_cols_to_round = [
        "cumulative_gross_return",
        "cumulative_net_return",
        "cumulative_cost_drag",
        "gross_drawdown",
        "net_drawdown",
        "cost_drag_period",
        "gross_growth_multiplier",
        "net_growth_multiplier",
        "cumulative_gross_index",
        "cumulative_net_index",
        "gross_running_peak",
        "net_running_peak",
    ]
    for col in float_cols_to_round:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(12)

    for col in ordered:
        if col not in out.columns:
            out[col] = ""
    return out[ordered + [c for c in out.columns if c not in ordered]]


def build_performance_summary_dataframe(portfolio_returns: pd.DataFrame, config: PortfolioPerformanceConfig) -> pd.DataFrame:
    monthly = build_monthly_diagnostics_dataframe(portfolio_returns)
    if monthly.empty:
        return pd.DataFrame([{"metric": "period_count", "value": 0, "performance_report_version": config.report_version}])

    gross = pd.to_numeric(monthly["portfolio_gross_return"], errors="coerce")
    net = pd.to_numeric(monthly["portfolio_net_return"], errors="coerce")
    turnover = pd.to_numeric(monthly["portfolio_turnover"], errors="coerce")
    costs = pd.to_numeric(monthly["transaction_cost_return"], errors="coerce")
    gross_index = pd.to_numeric(monthly["cumulative_gross_return"], errors="coerce") + 1.0
    net_index = pd.to_numeric(monthly["cumulative_net_return"], errors="coerce") + 1.0

    first_period = str(monthly["rebalance_period"].iloc[0])
    last_period = str(monthly["rebalance_period"].iloc[-1])
    primary_models = sorted(set(monthly["primary_model_name"].dropna().astype(str)))
    quality_flags = sorted(set(monthly["portfolio_quality_flag"].dropna().astype(str)))

    metrics: list[dict[str, Any]] = [
        {"metric": "report_version", "value": config.report_version},
        {"metric": "primary_model_name", "value": ",".join([m for m in primary_models if m])},
        {"metric": "period_count", "value": int(len(monthly))},
        {"metric": "first_period", "value": first_period},
        {"metric": "last_period", "value": last_period},
        {"metric": "annualization_periods", "value": config.annualization_periods},

        {"metric": "cumulative_gross_return", "value": _round_or_none(gross_index.iloc[-1] - 1.0)},
        {"metric": "cumulative_net_return", "value": _round_or_none(net_index.iloc[-1] - 1.0)},
        {"metric": "cumulative_cost_drag", "value": _round_or_none((gross_index.iloc[-1] - 1.0) - (net_index.iloc[-1] - 1.0))},

        {"metric": "annualized_gross_return", "value": _round_or_none(_annualized_return(gross, config.annualization_periods))},
        {"metric": "annualized_net_return", "value": _round_or_none(_annualized_return(net, config.annualization_periods))},

        {"metric": "mean_gross_return", "value": _round_or_none(gross.mean())},
        {"metric": "mean_net_return", "value": _round_or_none(net.mean())},
        {"metric": "vol_gross_return", "value": _round_or_none(_safe_std(gross))},
        {"metric": "vol_net_return", "value": _round_or_none(_safe_std(net))},

        {"metric": "gross_sharpe", "value": _round_or_none(_sharpe(gross, config.annualization_periods))},
        {"metric": "net_sharpe", "value": _round_or_none(_sharpe(net, config.annualization_periods))},
        {"metric": "gross_sortino", "value": _round_or_none(_sortino(gross, config.annualization_periods))},
        {"metric": "net_sortino", "value": _round_or_none(_sortino(net, config.annualization_periods))},

        {"metric": "gross_max_drawdown", "value": _round_or_none(_max_drawdown(gross_index))},
        {"metric": "net_max_drawdown", "value": _round_or_none(_max_drawdown(net_index))},
        {"metric": "gross_hit_rate", "value": _hit_rate(gross)},
        {"metric": "net_hit_rate", "value": _hit_rate(net)},
        {"metric": "gross_profit_factor", "value": _round_or_none(_profit_factor(gross))},
        {"metric": "net_profit_factor", "value": _round_or_none(_profit_factor(net))},

        {"metric": "mean_turnover", "value": _round_or_none(turnover.mean())},
        {"metric": "median_turnover", "value": _round_or_none(turnover.median())},
        {"metric": "mean_transaction_cost_return", "value": _round_or_none(costs.mean())},
        {"metric": "total_transaction_cost_return", "value": _round_or_none(costs.sum())},

        {"metric": "mean_long_count", "value": _round_or_none(pd.to_numeric(monthly["long_count"], errors="coerce").mean())},
        {"metric": "mean_short_count", "value": _round_or_none(pd.to_numeric(monthly["short_count"], errors="coerce").mean())},
        {"metric": "mean_gross_exposure", "value": _round_or_none(pd.to_numeric(monthly["gross_exposure"], errors="coerce").mean())},
        {"metric": "mean_net_exposure", "value": _round_or_none(pd.to_numeric(monthly["net_exposure"], errors="coerce").mean())},
        {"metric": "portfolio_quality_flags", "value": ",".join([q for q in quality_flags if q])},
    ]

    return pd.DataFrame(metrics)


def build_performance_diagnostics(summary: pd.DataFrame, monthly: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "summary_rows", "value": len(summary)},
        {"diagnostic": "monthly_rows", "value": len(monthly)},
    ]

    if not monthly.empty:
        rows.append({"diagnostic": "first_period", "value": monthly["rebalance_period"].iloc[0]})
        rows.append({"diagnostic": "last_period", "value": monthly["rebalance_period"].iloc[-1]})
        for flag, count in monthly["portfolio_quality_flag"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"portfolio_quality_flag_{flag}", "value": int(count)})
        rows.append({"diagnostic": "net_positive_months", "value": int(monthly["net_return_positive"].astype(bool).sum())})
        rows.append({"diagnostic": "net_negative_months", "value": int((~monthly["net_return_positive"].astype(bool)).sum())})

    metric_lookup = dict(zip(summary.get("metric", []), summary.get("value", [])))
    for metric in [
        "cumulative_net_return",
        "net_sharpe",
        "net_sortino",
        "net_max_drawdown",
        "net_hit_rate",
        "mean_turnover",
        "total_transaction_cost_return",
    ]:
        if metric in metric_lookup:
            rows.append({"diagnostic": metric, "value": metric_lookup[metric]})

    return pd.DataFrame(rows)


def _metric_value(summary: pd.DataFrame, metric: str) -> Any:
    row = summary[summary["metric"] == metric]
    if row.empty:
        return ""
    return row.iloc[0]["value"]


def _fmt(value: Any, digits: int = 4) -> str:
    number = _to_float(value)
    if number is None:
        return str(value) if value is not None else ""
    return f"{number:.{digits}f}"


def render_markdown_report(summary: pd.DataFrame, monthly: pd.DataFrame, config: PortfolioPerformanceConfig) -> str:
    lines = [
        "# Portfolio Performance Report",
        "",
        f"Version: `{config.report_version}`",
        "",
        "## Headline metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]

    headline = [
        "primary_model_name",
        "period_count",
        "first_period",
        "last_period",
        "cumulative_net_return",
        "annualized_net_return",
        "net_sharpe",
        "net_sortino",
        "net_max_drawdown",
        "net_hit_rate",
        "mean_turnover",
        "total_transaction_cost_return",
        "cumulative_cost_drag",
    ]
    for metric in headline:
        lines.append(f"| {metric} | {_fmt(_metric_value(summary, metric))} |")

    lines.extend(
        [
            "",
            "## Monthly diagnostics",
            "",
            "| Period | Gross return | Net return | Turnover | Cost | Net drawdown |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )

    if not monthly.empty:
        for _, row in monthly.iterrows():
            lines.append(
                "| "
                + f"{row.get('rebalance_period', '')} | "
                + f"{_fmt(row.get('portfolio_gross_return'))} | "
                + f"{_fmt(row.get('portfolio_net_return'))} | "
                + f"{_fmt(row.get('portfolio_turnover'))} | "
                + f"{_fmt(row.get('transaction_cost_return'))} | "
                + f"{_fmt(row.get('net_drawdown'))} |"
            )

    lines.append("")
    return "\n".join(lines)


def write_performance_outputs(
    summary: pd.DataFrame,
    monthly: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    summary_output_table_path: str | Path,
    summary_output_csv_path: str | Path,
    monthly_output_table_path: str | Path,
    monthly_output_csv_path: str | Path,
    markdown_report_path: str | Path,
    diagnostics_path: str | Path,
    config: PortfolioPerformanceConfig,
) -> None:
    safe_write_table(summary, parquet_path=summary_output_table_path, csv_path=summary_output_csv_path)
    safe_write_table(monthly, parquet_path=monthly_output_table_path, csv_path=monthly_output_csv_path)

    diagnostics_path = Path(diagnostics_path)
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(diagnostics_path, index=False)

    markdown_report_path = Path(markdown_report_path)
    markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_report_path.write_text(render_markdown_report(summary, monthly, config), encoding="utf-8")


def build_portfolio_performance_report(config: PortfolioPerformanceConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger = get_logger(
        "fvn_dfm.portfolio_performance_report",
        root() / "logs/pipeline/portfolio_performance_report.log",
    )
    logger.info("Building portfolio performance report from %s", config.portfolio_returns_path)

    raw_returns = read_table(config.portfolio_returns_path)
    monthly = build_monthly_diagnostics_dataframe(raw_returns)
    summary = build_performance_summary_dataframe(raw_returns, config)
    diagnostics = build_performance_diagnostics(summary, monthly)

    write_performance_outputs(
        summary,
        monthly,
        diagnostics,
        summary_output_table_path=config.summary_output_table_path,
        summary_output_csv_path=config.summary_output_csv_path,
        monthly_output_table_path=config.monthly_output_table_path,
        monthly_output_csv_path=config.monthly_output_csv_path,
        markdown_report_path=config.markdown_report_path,
        diagnostics_path=config.diagnostics_path,
        config=config,
    )
    logger.info("Wrote portfolio performance report with %d summary rows and %d monthly rows", len(summary), len(monthly))
    return summary, monthly


def main() -> None:
    parser = argparse.ArgumentParser(description="Build portfolio performance report.")
    parser.add_argument("--portfolio-returns-path", default="data/processed/portfolio/portfolio_monthly_returns.csv")
    parser.add_argument("--summary-output-table", default="data/processed/portfolio/portfolio_performance_summary.parquet")
    parser.add_argument("--summary-output-csv", default="data/processed/portfolio/portfolio_performance_summary.csv")
    parser.add_argument("--monthly-output-table", default="data/processed/portfolio/portfolio_monthly_diagnostics.parquet")
    parser.add_argument("--monthly-output-csv", default="data/processed/portfolio/portfolio_monthly_diagnostics.csv")
    parser.add_argument("--markdown-report-path", default="outputs/reports/portfolio_performance_report.md")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/portfolio_performance_report_diagnostics.csv")
    parser.add_argument("--annualization-periods", type=int, default=12)
    args = parser.parse_args()

    config = PortfolioPerformanceConfig(
        portfolio_returns_path=root() / args.portfolio_returns_path,
        summary_output_table_path=root() / args.summary_output_table,
        summary_output_csv_path=root() / args.summary_output_csv,
        monthly_output_table_path=root() / args.monthly_output_table,
        monthly_output_csv_path=root() / args.monthly_output_csv,
        markdown_report_path=root() / args.markdown_report_path,
        diagnostics_path=root() / args.diagnostics_path,
        annualization_periods=args.annualization_periods,
    )
    build_portfolio_performance_report(config)


if __name__ == "__main__":
    main()
