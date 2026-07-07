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


FUNDAMENTAL_COMPOSITE_VERSION = "FUNDAMENTAL_STRESS_IMPROVEMENT_V0"

# Directional component spec.
# Each value is (source_delta_column, sign), where component_raw = sign * source_delta.
# Higher component_raw means more of the named stress/improvement mechanism.
STRESS_COMPONENTS: dict[str, tuple[str, float]] = {
    "revenue_decline": ("revenue_yoy_pct_change", -1.0),
    "net_income_decline": ("net_income_yoy_pct_change", -1.0),
    "margin_deterioration": ("margin_yoy_delta", -1.0),
    "cfo_quality_deterioration": ("cfo_quality_yoy_delta", -1.0),
    "cash_conversion_deterioration": ("cash_conversion_yoy_delta", -1.0),
    "asset_growth_pressure": ("assets_yoy_pct_change", 1.0),
    "liability_intensity_increase": ("liability_intensity_yoy_delta", 1.0),
    "leverage_increase": ("leverage_yoy_delta", 1.0),
    "cash_buffer_decline": ("cash_to_assets_yoy_delta", -1.0),
    "receivables_intensity_increase": ("receivables_to_assets_yoy_delta", 1.0),
    "inventory_intensity_increase": ("inventory_to_assets_yoy_delta", 1.0),
    "capex_intensity_increase": ("capex_intensity_yoy_delta", 1.0),
    "share_dilution": ("shares_yoy_pct_change", 1.0),
    "working_capital_proxy_deterioration": ("working_capital_proxy_yoy_delta", -1.0),
}

IMPROVEMENT_COMPONENTS: dict[str, tuple[str, float]] = {
    "revenue_growth": ("revenue_yoy_pct_change", 1.0),
    "net_income_growth": ("net_income_yoy_pct_change", 1.0),
    "margin_improvement": ("margin_yoy_delta", 1.0),
    "cfo_quality_improvement": ("cfo_quality_yoy_delta", 1.0),
    "cash_conversion_improvement": ("cash_conversion_yoy_delta", 1.0),
    "asset_contraction_or_efficiency": ("assets_yoy_pct_change", -1.0),
    "liability_intensity_decline": ("liability_intensity_yoy_delta", -1.0),
    "leverage_decline": ("leverage_yoy_delta", -1.0),
    "cash_buffer_improvement": ("cash_to_assets_yoy_delta", 1.0),
    "receivables_intensity_decline": ("receivables_to_assets_yoy_delta", -1.0),
    "inventory_intensity_decline": ("inventory_to_assets_yoy_delta", -1.0),
    "capex_intensity_decline": ("capex_intensity_yoy_delta", -1.0),
    "share_count_decline": ("shares_yoy_pct_change", -1.0),
    "working_capital_proxy_improvement": ("working_capital_proxy_yoy_delta", 1.0),
}

CORE_COLUMNS = [
    "cik",
    "cik10",
    "accession_number",
    "accession_lineage_key",
    "form",
    "period",
    "fy",
    "fp",
    "feature_asof_date",
    "accepted_at_edgar",
    "timestamp_quality_flag",
    "fundamental_quality_flag",
    "fundamental_coverage_count",
    "fundamental_coverage_ratio",
    "comparable_period_key",
    "prior_accession_number",
    "prior_accession_lineage_key",
    "prior_period",
    "prior_fy",
    "prior_fp",
    "prior_feature_asof_date",
    "prior_fundamental_quality_flag",
    "period_gap_years",
    "comparable_link_quality_flag",
    "comparable_link_quality_notes",
]


@dataclass(frozen=True)
class FundamentalCompositeConfig:
    fundamental_delta_features_path: Path
    output_table_path: Path
    output_csv_path: Path
    diagnostics_path: Path
    composite_version: str = FUNDAMENTAL_COMPOSITE_VERSION
    min_valid_stress_components: int = 6
    min_valid_improvement_components: int = 6
    component_clip_abs: float = 5.0


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


def _clip(value: float | None, clip_abs: float) -> float | None:
    if value is None:
        return None
    return max(-clip_abs, min(clip_abs, value))


def _positive_part(value: float | None) -> float | None:
    if value is None:
        return None
    return max(value, 0.0)


def _mean_nonmissing(values: list[float | None]) -> float | None:
    valid = [v for v in values if v is not None]
    if not valid:
        return None
    return sum(valid) / len(valid)


def _round_or_none(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 12)


def _component_values(row: pd.Series, spec: dict[str, tuple[str, float]], prefix: str, clip_abs: float) -> tuple[dict[str, Any], list[float | None], list[float | None]]:
    out: dict[str, Any] = {}
    raw_values: list[float | None] = []
    pos_values: list[float | None] = []

    for component_name, (source_col, sign) in spec.items():
        source_value = _to_float(row.get(source_col, None))
        raw = _clip(sign * source_value, clip_abs) if source_value is not None else None
        pos = _positive_part(raw)

        out[f"{prefix}_{component_name}_raw"] = _round_or_none(raw)
        out[f"{prefix}_{component_name}_pos"] = _round_or_none(pos)
        out[f"{prefix}_{component_name}_source_col"] = source_col

        raw_values.append(raw)
        pos_values.append(pos)

    return out, raw_values, pos_values


def _quality_flag(row: pd.Series, stress_valid: int, improve_valid: int, config: FundamentalCompositeConfig) -> tuple[str, str]:
    notes: list[str] = []

    link_flag = str(row.get("comparable_link_quality_flag", "") or "").upper()
    fundamental_flag = str(row.get("fundamental_quality_flag", "") or "").upper()
    prior_fundamental_flag = str(row.get("prior_fundamental_quality_flag", "") or "").upper()

    if link_flag == "RED":
        notes.append("comparable_link_quality_red")
    elif link_flag == "YELLOW":
        notes.append("comparable_link_quality_yellow")

    if fundamental_flag == "RED":
        notes.append("current_fundamental_quality_red")
    elif fundamental_flag == "YELLOW":
        notes.append("current_fundamental_quality_yellow")

    if prior_fundamental_flag == "RED":
        notes.append("prior_fundamental_quality_red")
    elif prior_fundamental_flag == "YELLOW":
        notes.append("prior_fundamental_quality_yellow")

    if stress_valid < config.min_valid_stress_components:
        notes.append(f"low_valid_stress_components={stress_valid}")
    if improve_valid < config.min_valid_improvement_components:
        notes.append(f"low_valid_improvement_components={improve_valid}")

    if any("red" in note for note in notes) or link_flag == "RED":
        return "RED", ";".join(notes)
    if notes:
        return "YELLOW", ";".join(notes)
    return "GREEN", ""


def build_fundamental_composite_row(row: pd.Series, config: FundamentalCompositeConfig) -> dict[str, Any]:
    out: dict[str, Any] = {col: row.get(col, "") for col in CORE_COLUMNS}
    out["fundamental_composite_version"] = config.composite_version

    stress_component_data, stress_raw_values, stress_pos_values = _component_values(
        row,
        STRESS_COMPONENTS,
        "stress",
        config.component_clip_abs,
    )
    improve_component_data, improve_raw_values, improve_pos_values = _component_values(
        row,
        IMPROVEMENT_COMPONENTS,
        "improve",
        config.component_clip_abs,
    )
    out.update(stress_component_data)
    out.update(improve_component_data)

    stress_valid = sum(v is not None for v in stress_pos_values)
    improve_valid = sum(v is not None for v in improve_pos_values)

    stress_score = _mean_nonmissing(stress_pos_values)
    improve_score = _mean_nonmissing(improve_pos_values)
    stress_signed_mean = _mean_nonmissing(stress_raw_values)
    improve_signed_mean = _mean_nonmissing(improve_raw_values)

    out["fund_stress_score"] = _round_or_none(stress_score)
    out["fund_improve_score"] = _round_or_none(improve_score)
    out["fund_stress_signed_mean"] = _round_or_none(stress_signed_mean)
    out["fund_improve_signed_mean"] = _round_or_none(improve_signed_mean)
    out["fund_net_stress_score"] = _round_or_none((stress_score or 0.0) - (improve_score or 0.0)) if stress_score is not None or improve_score is not None else None
    out["fund_net_improvement_score"] = _round_or_none((improve_score or 0.0) - (stress_score or 0.0)) if stress_score is not None or improve_score is not None else None
    out["fund_stress_component_valid_count"] = stress_valid
    out["fund_improve_component_valid_count"] = improve_valid
    out["fund_stress_component_total_count"] = len(STRESS_COMPONENTS)
    out["fund_improve_component_total_count"] = len(IMPROVEMENT_COMPONENTS)
    out["fund_stress_component_coverage_ratio"] = stress_valid / len(STRESS_COMPONENTS)
    out["fund_improve_component_coverage_ratio"] = improve_valid / len(IMPROVEMENT_COMPONENTS)

    qflag, qnotes = _quality_flag(row, stress_valid, improve_valid, config)
    out["fundamental_composite_quality_flag"] = qflag
    out["fundamental_composite_quality_notes"] = qnotes

    # Protocol-facing aliases for the next mismatch module.
    out["fund_stress"] = out["fund_stress_score"]
    out["fund_improve"] = out["fund_improve_score"]
    out["fundamental_reality_score"] = out["fund_net_improvement_score"]
    return out


def build_fundamental_composites_dataframe(config: FundamentalCompositeConfig) -> pd.DataFrame:
    source = read_table(config.fundamental_delta_features_path)
    if source.empty:
        return pd.DataFrame()

    rows = [build_fundamental_composite_row(row, config) for _, row in source.iterrows()]
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["cik10", "period", "accession_number"]).reset_index(drop=True)
    return df


def build_fundamental_composite_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame([{"diagnostic": "rows", "value": 0}])

    rows: list[dict[str, Any]] = [
        {"diagnostic": "rows", "value": len(df)},
        {"diagnostic": "distinct_cik10", "value": df["cik10"].nunique() if "cik10" in df else 0},
        {"diagnostic": "mean_fund_stress_score", "value": pd.to_numeric(df["fund_stress_score"], errors="coerce").mean()},
        {"diagnostic": "mean_fund_improve_score", "value": pd.to_numeric(df["fund_improve_score"], errors="coerce").mean()},
        {"diagnostic": "mean_fund_net_improvement_score", "value": pd.to_numeric(df["fund_net_improvement_score"], errors="coerce").mean()},
    ]

    if "fundamental_composite_quality_flag" in df:
        for flag, count in df["fundamental_composite_quality_flag"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"composite_quality_flag_{flag}", "value": int(count)})

    return pd.DataFrame(rows)


def write_fundamental_composite_outputs(
    df: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    output_table_path: str | Path,
    output_csv_path: str | Path,
    diagnostics_path: str | Path,
) -> None:
    safe_write_table(df, parquet_path=output_table_path, csv_path=output_csv_path)
    diagnostics_path = Path(diagnostics_path)
    diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(diagnostics_path, index=False)


def build_fundamental_stress_improvement(config: FundamentalCompositeConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.fundamental_stress_improvement",
        root() / "logs/pipeline/fundamental_stress_improvement.log",
    )
    logger.info("Building Fundamental Stress / Improvement composites from %s", config.fundamental_delta_features_path)
    df = build_fundamental_composites_dataframe(config)
    diagnostics = build_fundamental_composite_diagnostics(df)
    write_fundamental_composite_outputs(
        df,
        diagnostics,
        output_table_path=config.output_table_path,
        output_csv_path=config.output_csv_path,
        diagnostics_path=config.diagnostics_path,
    )
    logger.info("Wrote %d fundamental composite rows to %s", len(df), config.output_table_path)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Fundamental Stress / Improvement composite features.")
    parser.add_argument("--fundamental-delta-features-path", default="data/processed/features/fundamental_delta_features_asof.csv")
    parser.add_argument("--output-table", default="data/processed/features/fundamental_composite_features_asof.parquet")
    parser.add_argument("--output-csv", default="data/processed/features/fundamental_composite_features_asof.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/fundamental_composite_features_asof_diagnostics.csv")
    parser.add_argument("--min-valid-stress-components", type=int, default=6)
    parser.add_argument("--min-valid-improvement-components", type=int, default=6)
    parser.add_argument("--component-clip-abs", type=float, default=5.0)
    args = parser.parse_args()

    config = FundamentalCompositeConfig(
        fundamental_delta_features_path=root() / args.fundamental_delta_features_path,
        output_table_path=root() / args.output_table,
        output_csv_path=root() / args.output_csv,
        diagnostics_path=root() / args.diagnostics_path,
        min_valid_stress_components=args.min_valid_stress_components,
        min_valid_improvement_components=args.min_valid_improvement_components,
        component_clip_abs=args.component_clip_abs,
    )
    build_fundamental_stress_improvement(config)


if __name__ == "__main__":
    main()
