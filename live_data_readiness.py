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


COMPARABLE_DELTA_VERSION = "COMPARABLE_PERIOD_DELTAS_V0"

RAW_VALUE_COLUMNS = [
    "revenue",
    "net_income",
    "cfo",
    "assets",
    "liabilities",
    "debt",
    "cash",
    "receivables",
    "inventory",
    "capex",
    "shares",
]

RATIO_COLUMNS = [
    "net_margin",
    "cfo_to_net_income",
    "cfo_to_revenue",
    "liabilities_to_assets",
    "debt_to_assets",
    "cash_to_assets",
    "receivables_to_assets",
    "inventory_to_assets",
    "capex_to_revenue",
    "asset_turnover",
    "cash_minus_debt_to_assets",
    "working_capital_proxy_to_assets",
]

CORE_DELTA_COLUMNS = [
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
    "delta_feature_version",
]


@dataclass(frozen=True)
class ComparableDeltasConfig:
    fundamental_features_asof_path: Path
    output_table_path: Path
    output_csv_path: Path
    diagnostics_path: Path
    delta_version: str = COMPARABLE_DELTA_VERSION


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


def _to_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    clean = str(value).strip()
    if clean == "":
        return None
    try:
        return int(float(clean))
    except Exception:
        return None


def _period_year(value: Any) -> int | None:
    period = str(value or "").strip()
    if len(period) >= 4 and period[:4].isdigit():
        return int(period[:4])
    return None


def normalize_fp(value: Any, form: Any = "") -> str:
    fp = str(value or "").strip().upper()
    if fp in {"FY", "Q1", "Q2", "Q3", "Q4"}:
        return fp
    form_upper = str(form or "").strip().upper()
    if form_upper == "10-K":
        return "FY"
    return ""


def comparable_period_key(row: dict[str, Any]) -> str:
    """Return the comparable fiscal period bucket.

    Policy v0:
    - FY filings compare to prior FY
    - Q1/Q2/Q3/Q4 filings compare to same fiscal quarter prior year
    - Missing/unknown FP is not linked
    """
    return normalize_fp(row.get("fp"), row.get("form"))


def _round_delta(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 12)


def _abs_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None:
        return None
    return _round_delta(current - prior)


def _pct_change(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None:
        return None
    if prior == 0:
        return None
    return _round_delta((current - prior) / abs(prior))


def _signed_log_change(current: float | None, prior: float | None) -> float | None:
    """Symmetric-ish log change for signed accounting values."""
    if current is None or prior is None:
        return None
    return _round_delta(math.copysign(math.log1p(abs(current)), current) - math.copysign(math.log1p(abs(prior)), prior))


def _ratio_delta(current: float | None, prior: float | None) -> float | None:
    if current is None or prior is None:
        return None
    return _round_delta(current - prior)


def _quality_flag_for_link(current: pd.Series, prior: pd.Series | None, period_gap_years: int | None) -> tuple[str, str]:
    notes: list[str] = []

    if prior is None:
        return "RED", "missing_prior_comparable_filing"

    if period_gap_years is None:
        notes.append("missing_or_invalid_period_year")
    elif period_gap_years != 1:
        notes.append(f"nonstandard_period_gap_years={period_gap_years}")

    current_quality = str(current.get("fundamental_quality_flag", "") or "")
    prior_quality = str(prior.get("fundamental_quality_flag", "") or "")
    if current_quality == "RED":
        notes.append("current_fundamental_quality_red")
    elif current_quality == "YELLOW":
        notes.append("current_fundamental_quality_yellow")

    if prior_quality == "RED":
        notes.append("prior_fundamental_quality_red")
    elif prior_quality == "YELLOW":
        notes.append("prior_fundamental_quality_yellow")

    current_key = comparable_period_key(current.to_dict())
    prior_key = comparable_period_key(prior.to_dict())
    if current_key != prior_key:
        notes.append("comparable_period_key_mismatch")

    if current.get("cik10", "") != prior.get("cik10", ""):
        notes.append("cik_mismatch")

    if any("red" in note for note in notes):
        return "RED", ";".join(notes)
    if notes:
        return "YELLOW", ";".join(notes)
    return "GREEN", ""


def _base_output_row(current: pd.Series, prior: pd.Series | None, delta_version: str) -> dict[str, Any]:
    current_dict = current.to_dict()
    key = comparable_period_key(current_dict)

    if prior is None:
        prior_period = prior_fy = prior_fp = prior_asof = prior_quality = prior_accession = prior_lineage = ""
        gap = None
    else:
        prior_period = prior.get("period", "")
        prior_fy = prior.get("fy", "")
        prior_fp = prior.get("fp", "")
        prior_asof = prior.get("feature_asof_date", "")
        prior_quality = prior.get("fundamental_quality_flag", "")
        prior_accession = prior.get("accession_number", "")
        prior_lineage = prior.get("accession_lineage_key", "")
        current_year = _period_year(current.get("period", ""))
        prior_year = _period_year(prior_period)
        gap = current_year - prior_year if current_year is not None and prior_year is not None else None

    qflag, qnotes = _quality_flag_for_link(current, prior, gap)

    row = {
        "cik": current.get("cik", ""),
        "cik10": current.get("cik10", ""),
        "accession_number": current.get("accession_number", ""),
        "accession_lineage_key": current.get("accession_lineage_key", ""),
        "form": current.get("form", ""),
        "period": current.get("period", ""),
        "fy": current.get("fy", ""),
        "fp": current.get("fp", ""),
        "feature_asof_date": current.get("feature_asof_date", ""),
        "accepted_at_edgar": current.get("accepted_at_edgar", ""),
        "timestamp_quality_flag": current.get("timestamp_quality_flag", ""),
        "fundamental_quality_flag": current.get("fundamental_quality_flag", ""),
        "fundamental_coverage_count": current.get("fundamental_coverage_count", ""),
        "fundamental_coverage_ratio": current.get("fundamental_coverage_ratio", ""),
        "comparable_period_key": key,
        "prior_accession_number": prior_accession,
        "prior_accession_lineage_key": prior_lineage,
        "prior_period": prior_period,
        "prior_fy": prior_fy,
        "prior_fp": prior_fp,
        "prior_feature_asof_date": prior_asof,
        "prior_fundamental_quality_flag": prior_quality,
        "period_gap_years": gap,
        "comparable_link_quality_flag": qflag,
        "comparable_link_quality_notes": qnotes,
        "delta_feature_version": delta_version,
    }
    return row


def build_delta_row(current: pd.Series, prior: pd.Series | None, delta_version: str) -> dict[str, Any]:
    row = _base_output_row(current, prior, delta_version)

    for col in RAW_VALUE_COLUMNS:
        current_value = _to_float(current.get(col, None))
        prior_value = _to_float(prior.get(col, None)) if prior is not None else None
        row[f"{col}_current"] = current_value
        row[f"{col}_prior"] = prior_value
        row[f"{col}_yoy_abs_change"] = _abs_change(current_value, prior_value)
        row[f"{col}_yoy_pct_change"] = _pct_change(current_value, prior_value)
        row[f"{col}_yoy_signed_log_change"] = _signed_log_change(current_value, prior_value)

    for col in RATIO_COLUMNS:
        current_value = _to_float(current.get(col, None))
        prior_value = _to_float(prior.get(col, None)) if prior is not None else None
        row[f"{col}_current"] = current_value
        row[f"{col}_prior"] = prior_value
        row[f"{col}_yoy_delta"] = _ratio_delta(current_value, prior_value)

    # Explicit aliases for the mechanism language used in the protocol.
    row["margin_yoy_delta"] = row.get("net_margin_yoy_delta")
    row["cfo_quality_yoy_delta"] = row.get("cfo_to_net_income_yoy_delta")
    row["cash_conversion_yoy_delta"] = row.get("cfo_to_revenue_yoy_delta")
    row["leverage_yoy_delta"] = row.get("debt_to_assets_yoy_delta")
    row["liability_intensity_yoy_delta"] = row.get("liabilities_to_assets_yoy_delta")
    row["working_capital_proxy_yoy_delta"] = row.get("working_capital_proxy_to_assets_yoy_delta")
    row["capex_intensity_yoy_delta"] = row.get("capex_to_revenue_yoy_delta")
    return row


def _sort_input(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["_period_year"] = out["period"].map(_period_year) if "period" in out.columns else None
    out["_fy_int"] = out["fy"].map(_to_int) if "fy" in out.columns else None
    out["_period_sort"] = pd.to_numeric(out.get("period", ""), errors="coerce")
    out["_feature_asof_sort"] = pd.to_datetime(out.get("feature_asof_date", ""), errors="coerce")
    return out.sort_values(
        ["cik10", "_period_year", "fp", "_period_sort", "_feature_asof_sort", "accession_number"],
        na_position="last",
    ).reset_index(drop=True)


def build_comparable_period_deltas_dataframe(config: ComparableDeltasConfig) -> pd.DataFrame:
    source = read_table(config.fundamental_features_asof_path)
    if source.empty:
        return pd.DataFrame()

    source = _sort_input(source)
    rows: list[dict[str, Any]] = []

    previous_by_company_period: dict[tuple[str, str], pd.Series] = {}

    for _, current in source.iterrows():
        key = comparable_period_key(current.to_dict())
        cik10 = str(current.get("cik10", "") or "")
        lookup_key = (cik10, key)

        prior = previous_by_company_period.get(lookup_key)
        rows.append(build_delta_row(current, prior, config.delta_version))

        if cik10 and key:
            previous_by_company_period[lookup_key] = current

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["cik10", "period", "accession_number"]).reset_index(drop=True)
    return df


def build_comparable_delta_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame([{"diagnostic": "rows", "value": 0}])

    rows: list[dict[str, Any]] = [
        {"diagnostic": "rows", "value": len(df)},
        {"diagnostic": "distinct_cik10", "value": df["cik10"].nunique() if "cik10" in df else 0},
        {"diagnostic": "linked_rows", "value": int(df["prior_accession_number"].astype(str).str.len().gt(0).sum())},
    ]

    if "comparable_link_quality_flag" in df:
        for flag, count in df["comparable_link_quality_flag"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"link_quality_flag_{flag}", "value": int(count)})

    for key, count in df["comparable_period_key"].value_counts(dropna=False).items():
        rows.append({"diagnostic": f"comparable_period_key_{key}", "value": int(count)})

    return pd.DataFrame(rows)


def write_comparable_delta_outputs(
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


def build_comparable_period_deltas(config: ComparableDeltasConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.comparable_period_deltas",
        root() / "logs/pipeline/comparable_period_deltas.log",
    )
    logger.info("Building comparable-period deltas from %s", config.fundamental_features_asof_path)
    df = build_comparable_period_deltas_dataframe(config)
    diagnostics = build_comparable_delta_diagnostics(df)
    write_comparable_delta_outputs(
        df,
        diagnostics,
        output_table_path=config.output_table_path,
        output_csv_path=config.output_csv_path,
        diagnostics_path=config.diagnostics_path,
    )
    logger.info("Wrote %d comparable-period delta rows to %s", len(df), config.output_table_path)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Build comparable-period delta features.")
    parser.add_argument("--fundamental-features-path", default="data/processed/features/fundamental_features_asof.csv")
    parser.add_argument("--output-table", default="data/processed/features/fundamental_delta_features_asof.parquet")
    parser.add_argument("--output-csv", default="data/processed/features/fundamental_delta_features_asof.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/fundamental_delta_features_asof_diagnostics.csv")
    args = parser.parse_args()

    config = ComparableDeltasConfig(
        fundamental_features_asof_path=root() / args.fundamental_features_path,
        output_table_path=root() / args.output_table,
        output_csv_path=root() / args.output_csv,
        diagnostics_path=root() / args.diagnostics_path,
    )
    build_comparable_period_deltas(config)


if __name__ == "__main__":
    main()
