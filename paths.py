from __future__ import annotations

import argparse
import math
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


FINAL_RESEARCH_VERDICT_VERSION = "FINAL_RESEARCH_VERDICT_V0"


@dataclass(frozen=True)
class FinalResearchVerdictConfig:
    portfolio_performance_summary_path: Path
    model_selection_report_path: Path
    ablation_summary_path: Path
    verdict_output_table_path: Path
    verdict_output_csv_path: Path
    evidence_output_table_path: Path
    evidence_output_csv_path: Path
    criteria_output_table_path: Path
    criteria_output_csv_path: Path
    markdown_report_path: Path
    diagnostics_path: Path
    min_period_count: int = 12
    min_net_sharpe: float = 0.5
    min_cumulative_net_return: float = 0.0
    max_net_drawdown_abs: float = 0.25
    min_validation_ic: float = 0.0
    require_dfm_ablation_best_or_tied: bool = True
    verdict_version: str = FINAL_RESEARCH_VERDICT_VERSION


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


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _metric(summary: pd.DataFrame, name: str) -> Any:
    if "metric" not in summary.columns or "value" not in summary.columns:
        return ""
    rows = summary[summary["metric"].astype(str) == name]
    if rows.empty:
        return ""
    return rows.iloc[0]["value"]


def _round_or_none(value: float | None, digits: int = 12) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def extract_primary_model(model_selection_report: pd.DataFrame) -> pd.Series | None:
    if model_selection_report.empty:
        return None
    if "is_primary_model" in model_selection_report.columns:
        primary = model_selection_report[
            model_selection_report["is_primary_model"].map(_to_bool)
        ]
        if not primary.empty:
            return primary.iloc[0]
    if "model_selection_rank" in model_selection_report.columns:
        tmp = model_selection_report.copy()
        tmp["model_selection_rank"] = pd.to_numeric(tmp["model_selection_rank"], errors="coerce")
        tmp = tmp.sort_values(["model_selection_rank", "model_name"])
        if not tmp.empty:
            return tmp.iloc[0]
    return model_selection_report.iloc[0]


def extract_dfm_ablation(ablation_summary: pd.DataFrame) -> pd.Series | None:
    if ablation_summary.empty or "ablation_name" not in ablation_summary.columns:
        return None
    rows = ablation_summary[ablation_summary["ablation_name"].astype(str) == "dfm_score"]
    if rows.empty:
        return None
    return rows.iloc[0]


def _best_ablation_by_ic(ablation_summary: pd.DataFrame) -> str:
    if ablation_summary.empty or "ablation_name" not in ablation_summary.columns:
        return ""
    if "mean_spearman_ic" not in ablation_summary.columns:
        return ""
    tmp = ablation_summary.copy()
    tmp["mean_spearman_ic"] = pd.to_numeric(tmp["mean_spearman_ic"], errors="coerce")
    tmp = tmp.sort_values(["mean_spearman_ic", "ablation_name"], ascending=[False, True])
    if tmp.empty:
        return ""
    return str(tmp.iloc[0]["ablation_name"])


def _dfm_is_best_or_tied(ablation_summary: pd.DataFrame) -> bool:
    if ablation_summary.empty or "mean_spearman_ic" not in ablation_summary.columns:
        return False
    dfm = extract_dfm_ablation(ablation_summary)
    if dfm is None:
        return False
    dfm_ic = _to_float(dfm.get("mean_spearman_ic"))
    if dfm_ic is None:
        return False
    values = pd.to_numeric(ablation_summary["mean_spearman_ic"], errors="coerce").dropna()
    if values.empty:
        return False
    return dfm_ic >= values.max() - 1e-12


def build_evidence_table(
    performance_summary: pd.DataFrame,
    model_selection_report: pd.DataFrame,
    ablation_summary: pd.DataFrame,
    config: FinalResearchVerdictConfig,
) -> pd.DataFrame:
    primary = extract_primary_model(model_selection_report)
    dfm = extract_dfm_ablation(ablation_summary)

    rows: list[dict[str, Any]] = []

    def add(source: str, metric: str, value: Any, note: str = "") -> None:
        rows.append(
            {
                "evidence_source": source,
                "evidence_metric": metric,
                "evidence_value": value,
                "evidence_note": note,
                "verdict_version": config.verdict_version,
            }
        )

    add("portfolio_performance_summary", "primary_model_name", _metric(performance_summary, "primary_model_name"))
    add("portfolio_performance_summary", "period_count", _metric(performance_summary, "period_count"))
    add("portfolio_performance_summary", "cumulative_net_return", _metric(performance_summary, "cumulative_net_return"))
    add("portfolio_performance_summary", "annualized_net_return", _metric(performance_summary, "annualized_net_return"))
    add("portfolio_performance_summary", "net_sharpe", _metric(performance_summary, "net_sharpe"))
    add("portfolio_performance_summary", "net_sortino", _metric(performance_summary, "net_sortino"))
    add("portfolio_performance_summary", "net_max_drawdown", _metric(performance_summary, "net_max_drawdown"))
    add("portfolio_performance_summary", "net_hit_rate", _metric(performance_summary, "net_hit_rate"))
    add("portfolio_performance_summary", "mean_turnover", _metric(performance_summary, "mean_turnover"))
    add("portfolio_performance_summary", "total_transaction_cost_return", _metric(performance_summary, "total_transaction_cost_return"))

    if primary is not None:
        add("model_selection_report", "primary_model_name", primary.get("model_name", ""))
        add("model_selection_report", "validation_mean_spearman_ic", primary.get("validation_mean_spearman_ic", ""))
        add("model_selection_report", "validation_mean_mae", primary.get("validation_mean_mae", ""))
        add("model_selection_report", "validation_mean_rmse", primary.get("validation_mean_rmse", ""))
        add("model_selection_report", "test_mean_spearman_ic", primary.get("test_mean_spearman_ic", ""))
        add("model_selection_report", "model_selection_rank", primary.get("model_selection_rank", ""))

    if dfm is not None:
        add("ablation_summary", "dfm_mean_spearman_ic", dfm.get("mean_spearman_ic", ""))
        add("ablation_summary", "dfm_mean_mae", dfm.get("mean_mae", ""))
        add("ablation_summary", "dfm_mean_rmse", dfm.get("mean_rmse", ""))
        add("ablation_summary", "dfm_portfolio_cumulative_net_return", dfm.get("portfolio_cumulative_net_return", ""))
        add("ablation_summary", "dfm_ablation_score_rank", dfm.get("ablation_score_rank", ""))
        add("ablation_summary", "best_ablation_by_ic", _best_ablation_by_ic(ablation_summary))

    return pd.DataFrame(rows)


def build_criteria_table(
    performance_summary: pd.DataFrame,
    model_selection_report: pd.DataFrame,
    ablation_summary: pd.DataFrame,
    config: FinalResearchVerdictConfig,
) -> pd.DataFrame:
    primary = extract_primary_model(model_selection_report)
    dfm = extract_dfm_ablation(ablation_summary)

    period_count = _to_float(_metric(performance_summary, "period_count"))
    cumulative_net = _to_float(_metric(performance_summary, "cumulative_net_return"))
    net_sharpe = _to_float(_metric(performance_summary, "net_sharpe"))
    net_drawdown = _to_float(_metric(performance_summary, "net_max_drawdown"))
    validation_ic = _to_float(primary.get("validation_mean_spearman_ic")) if primary is not None else None
    dfm_ic = _to_float(dfm.get("mean_spearman_ic")) if dfm is not None else None
    dfm_best_or_tied = _dfm_is_best_or_tied(ablation_summary)

    checks = [
        {
            "criterion": "minimum_oos_periods",
            "threshold": f">= {config.min_period_count}",
            "observed_value": period_count,
            "passed": period_count is not None and period_count >= config.min_period_count,
            "critical": True,
            "rationale": "Avoid declaring research success from too few OOS rebalance periods.",
        },
        {
            "criterion": "positive_cumulative_net_return",
            "threshold": f"> {config.min_cumulative_net_return}",
            "observed_value": cumulative_net,
            "passed": cumulative_net is not None and cumulative_net > config.min_cumulative_net_return,
            "critical": True,
            "rationale": "The audited portfolio return stream must be positive after costs.",
        },
        {
            "criterion": "minimum_net_sharpe",
            "threshold": f">= {config.min_net_sharpe}",
            "observed_value": net_sharpe,
            "passed": net_sharpe is not None and net_sharpe >= config.min_net_sharpe,
            "critical": True,
            "rationale": "The return stream must clear a conservative risk-adjusted performance bar.",
        },
        {
            "criterion": "max_drawdown_control",
            "threshold": f">= -{config.max_net_drawdown_abs}",
            "observed_value": net_drawdown,
            "passed": net_drawdown is not None and net_drawdown >= -abs(config.max_net_drawdown_abs),
            "critical": True,
            "rationale": "The strategy should not pass with excessive drawdown.",
        },
        {
            "criterion": "positive_primary_validation_ic",
            "threshold": f"> {config.min_validation_ic}",
            "observed_value": validation_ic,
            "passed": validation_ic is not None and validation_ic > config.min_validation_ic,
            "critical": True,
            "rationale": "The selected predictive model must show positive validation rank IC.",
        },
        {
            "criterion": "positive_dfm_ablation_ic",
            "threshold": "> 0",
            "observed_value": dfm_ic,
            "passed": dfm_ic is not None and dfm_ic > 0,
            "critical": True,
            "rationale": "The DFM score itself must have positive test rank IC.",
        },
        {
            "criterion": "dfm_best_or_tied_ablation",
            "threshold": "True",
            "observed_value": dfm_best_or_tied,
            "passed": bool(dfm_best_or_tied) if config.require_dfm_ablation_best_or_tied else True,
            "critical": bool(config.require_dfm_ablation_best_or_tied),
            "rationale": "The DFM claim requires the interaction score to beat or tie simpler baselines.",
        },
    ]

    out = pd.DataFrame(checks)
    out["verdict_version"] = config.verdict_version
    return out


def build_verdict_table(criteria: pd.DataFrame, config: FinalResearchVerdictConfig) -> pd.DataFrame:
    if criteria.empty:
        verdict = "FAIL"
        notes = "No criteria available."
        passed_critical = 0
        total_critical = 0
    else:
        critical = criteria[criteria["critical"].astype(bool)]
        passed_critical = int(critical["passed"].astype(bool).sum())
        total_critical = int(len(critical))
        verdict = "PASS" if total_critical > 0 and passed_critical == total_critical else "FAIL"
        failed = criteria[(criteria["critical"].astype(bool)) & (~criteria["passed"].astype(bool))]
        if failed.empty:
            notes = "All critical criteria passed."
        else:
            notes = "Failed critical criteria: " + ", ".join(failed["criterion"].astype(str).tolist())

    return pd.DataFrame(
        [
            {
                "final_verdict": verdict,
                "passed_critical_criteria": passed_critical,
                "total_critical_criteria": total_critical,
                "verdict_notes": notes,
                "verdict_timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "verdict_version": config.verdict_version,
            }
        ]
    )


def build_verdict_diagnostics(
    verdict: pd.DataFrame,
    evidence: pd.DataFrame,
    criteria: pd.DataFrame,
) -> pd.DataFrame:
    rows = [
        {"diagnostic": "verdict_rows", "value": len(verdict)},
        {"diagnostic": "evidence_rows", "value": len(evidence)},
        {"diagnostic": "criteria_rows", "value": len(criteria)},
    ]
    if not verdict.empty:
        rows.append({"diagnostic": "final_verdict", "value": verdict.iloc[0]["final_verdict"]})
        rows.append({"diagnostic": "passed_critical_criteria", "value": verdict.iloc[0]["passed_critical_criteria"]})
        rows.append({"diagnostic": "total_critical_criteria", "value": verdict.iloc[0]["total_critical_criteria"]})
    if not criteria.empty:
        rows.append({"diagnostic": "failed_critical_criteria", "value": int(((criteria["critical"].astype(bool)) & (~criteria["passed"].astype(bool))).sum())})
    return pd.DataFrame(rows)


def _fmt(value: Any, digits: int = 6) -> str:
    number = _to_float(value)
    if number is None:
        return str(value) if value is not None else ""
    return f"{number:.{digits}f}"


def render_markdown_report(verdict: pd.DataFrame, evidence: pd.DataFrame, criteria: pd.DataFrame) -> str:
    final = verdict.iloc[0] if not verdict.empty else {}
    lines = [
        "# Final Research Verdict",
        "",
        f"Version: `{FINAL_RESEARCH_VERDICT_VERSION}`",
        "",
        "## Verdict",
        "",
        f"Final verdict: **{final.get('final_verdict', 'FAIL')}**",
        "",
        f"Notes: {final.get('verdict_notes', '')}",
        "",
        "## Criteria",
        "",
        "| Criterion | Threshold | Observed | Passed | Critical |",
        "|---|---:|---:|---:|---:|",
    ]

    if not criteria.empty:
        for _, row in criteria.iterrows():
            lines.append(
                "| "
                + f"{row.get('criterion', '')} | "
                + f"{row.get('threshold', '')} | "
                + f"{_fmt(row.get('observed_value'))} | "
                + f"{row.get('passed', '')} | "
                + f"{row.get('critical', '')} |"
            )

    lines.extend(
        [
            "",
            "## Evidence",
            "",
            "| Source | Metric | Value |",
            "|---|---|---:|",
        ]
    )
    if not evidence.empty:
        for _, row in evidence.iterrows():
            lines.append(
                "| "
                + f"{row.get('evidence_source', '')} | "
                + f"{row.get('evidence_metric', '')} | "
                + f"{_fmt(row.get('evidence_value'))} |"
            )

    lines.extend(
        [
            "",
            "## Conservative interpretation",
            "",
            "A PASS means the current evidence clears all configured critical gates. A FAIL does not mean the hypothesis is false; it means the current research package is not strong enough for a positive verdict under the conservative v0 rule.",
            "",
        ]
    )
    return "\n".join(lines)


def write_final_verdict_outputs(
    verdict: pd.DataFrame,
    evidence: pd.DataFrame,
    criteria: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    config: FinalResearchVerdictConfig,
) -> None:
    safe_write_table(verdict, parquet_path=config.verdict_output_table_path, csv_path=config.verdict_output_csv_path)
    safe_write_table(evidence, parquet_path=config.evidence_output_table_path, csv_path=config.evidence_output_csv_path)
    safe_write_table(criteria, parquet_path=config.criteria_output_table_path, csv_path=config.criteria_output_csv_path)

    config.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(config.diagnostics_path, index=False)

    config.markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
    config.markdown_report_path.write_text(render_markdown_report(verdict, evidence, criteria), encoding="utf-8")


def build_final_research_verdict(config: FinalResearchVerdictConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.final_research_verdict",
        root() / "logs/pipeline/final_research_verdict.log",
    )
    logger.info("Building final research verdict.")

    performance = read_table(config.portfolio_performance_summary_path)
    model_selection = read_table(config.model_selection_report_path)
    ablation = read_table(config.ablation_summary_path)

    evidence = build_evidence_table(performance, model_selection, ablation, config)
    criteria = build_criteria_table(performance, model_selection, ablation, config)
    verdict = build_verdict_table(criteria, config)
    diagnostics = build_verdict_diagnostics(verdict, evidence, criteria)

    write_final_verdict_outputs(verdict, evidence, criteria, diagnostics, config=config)

    logger.info("Final verdict: %s", verdict.iloc[0]["final_verdict"] if not verdict.empty else "FAIL")
    return verdict


def main() -> None:
    parser = argparse.ArgumentParser(description="Build final research verdict v0.")
    parser.add_argument("--portfolio-performance-summary-path", default="data/processed/portfolio/portfolio_performance_summary.csv")
    parser.add_argument("--model-selection-report-path", default="data/processed/model/model_selection_report.csv")
    parser.add_argument("--ablation-summary-path", default="data/processed/model/ablation_summary.csv")
    parser.add_argument("--verdict-output-table", default="data/processed/reports/final_research_verdict.parquet")
    parser.add_argument("--verdict-output-csv", default="data/processed/reports/final_research_verdict.csv")
    parser.add_argument("--evidence-output-table", default="data/processed/reports/final_research_evidence.parquet")
    parser.add_argument("--evidence-output-csv", default="data/processed/reports/final_research_evidence.csv")
    parser.add_argument("--criteria-output-table", default="data/processed/reports/final_research_criteria.parquet")
    parser.add_argument("--criteria-output-csv", default="data/processed/reports/final_research_criteria.csv")
    parser.add_argument("--markdown-report-path", default="outputs/reports/final_research_verdict.md")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/final_research_verdict_diagnostics.csv")
    parser.add_argument("--min-period-count", type=int, default=12)
    parser.add_argument("--min-net-sharpe", type=float, default=0.5)
    parser.add_argument("--min-cumulative-net-return", type=float, default=0.0)
    parser.add_argument("--max-net-drawdown-abs", type=float, default=0.25)
    parser.add_argument("--min-validation-ic", type=float, default=0.0)
    parser.add_argument("--do-not-require-dfm-best-ablation", action="store_true")
    args = parser.parse_args()

    config = FinalResearchVerdictConfig(
        portfolio_performance_summary_path=root() / args.portfolio_performance_summary_path,
        model_selection_report_path=root() / args.model_selection_report_path,
        ablation_summary_path=root() / args.ablation_summary_path,
        verdict_output_table_path=root() / args.verdict_output_table,
        verdict_output_csv_path=root() / args.verdict_output_csv,
        evidence_output_table_path=root() / args.evidence_output_table,
        evidence_output_csv_path=root() / args.evidence_output_csv,
        criteria_output_table_path=root() / args.criteria_output_table,
        criteria_output_csv_path=root() / args.criteria_output_csv,
        markdown_report_path=root() / args.markdown_report_path,
        diagnostics_path=root() / args.diagnostics_path,
        min_period_count=args.min_period_count,
        min_net_sharpe=args.min_net_sharpe,
        min_cumulative_net_return=args.min_cumulative_net_return,
        max_net_drawdown_abs=args.max_net_drawdown_abs,
        min_validation_ic=args.min_validation_ic,
        require_dfm_ablation_best_or_tied=not args.do_not_require_dfm_best_ablation,
    )
    build_final_research_verdict(config)


if __name__ == "__main__":
    main()
