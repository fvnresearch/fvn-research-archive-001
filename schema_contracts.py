from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.xbrl.concept_map import canonical_concepts
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


FUNDAMENTAL_FEATURE_VERSION = "FUNDAMENTAL_FEATURES_ASOF_V0"

VALUE_CONCEPTS = tuple(canonical_concepts())

FUNDAMENTAL_RATIO_COLUMNS = [
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

FUNDAMENTAL_FEATURE_BASE_COLUMNS = [
    "cik",
    "cik10",
    "accession_number",
    "accession_lineage_key",
    "form",
    "period",
    "fy",
    "fp",
    "filed",
    "accepted",
    "feature_asof_date",
    "accepted_at_edgar",
    "timestamp_quality_flag",
    "fundamental_feature_version",
    "fundamental_coverage_count",
    "fundamental_coverage_ratio",
    "fundamental_quality_flag",
    "fundamental_quality_notes",
]


@dataclass(frozen=True)
class FundamentalFeaturesConfig:
    accounting_fact_selected_path: Path
    filing_availability_path: Path | None
    output_table_path: Path
    output_csv_path: Path
    diagnostics_path: Path
    feature_version: str = FUNDAMENTAL_FEATURE_VERSION


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
        return float(clean)
    except Exception:
        return None


def _safe_divide(num: float | None, den: float | None) -> float | None:
    if num is None or den is None:
        return None
    if den == 0:
        return None
    return num / den


def _availability_lookup(path: str | Path | None) -> dict[str, dict[str, Any]]:
    if path is None:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    df = read_table(p)
    lookup: dict[str, dict[str, Any]] = {}
    for _, row in df.iterrows():
        cik10 = str(row.get("cik10", "") or "")
        accession = str(row.get("accession_number", "") or "")
        if cik10 and accession:
            lookup[f"{cik10}:{accession}"] = row.to_dict()
        lineage = str(row.get("accession_lineage_key", "") or "")
        if lineage:
            lookup[lineage] = row.to_dict()
    return lookup


def _quality_rank(flag: str) -> int:
    flag = str(flag or "").upper()
    if flag == "GREEN":
        return 0
    if flag == "YELLOW":
        return 1
    if flag == "RED":
        return 2
    return 3


def _best_fact_per_concept(facts: pd.DataFrame) -> pd.DataFrame:
    if facts.empty:
        return facts

    out = facts.copy()
    out["_quality_rank"] = out["fact_quality_flag"].map(_quality_rank) if "fact_quality_flag" in out.columns else 3
    if "selection_rank" in out.columns:
        out["_selection_rank_num"] = pd.to_numeric(out["selection_rank"], errors="coerce").fillna(999999)
    else:
        out["_selection_rank_num"] = 999999

    out = out.sort_values(
        ["canonical_concept", "_quality_rank", "_selection_rank_num", "selected_tag"],
        ascending=[True, True, True, True],
    )
    out = out.drop_duplicates(subset=["canonical_concept"], keep="first")
    return out.drop(columns=[c for c in ["_quality_rank", "_selection_rank_num"] if c in out.columns])


def _availability_for_accession(row_base: dict[str, Any], availability: dict[str, dict[str, Any]]) -> dict[str, Any]:
    cik10 = str(row_base.get("cik10", "") or "")
    accession = str(row_base.get("accession_number", "") or "")
    key = f"{cik10}:{accession}"
    return availability.get(key, availability.get(str(row_base.get("accession_lineage_key", "") or ""), {}))


def _coverage_quality(available: set[str], concept_flags: dict[str, str], ratios: dict[str, float | None]) -> tuple[str, str]:
    notes: list[str] = []
    required_core = {"revenue", "net_income", "assets"}
    missing_core = sorted(required_core.difference(available))
    if missing_core:
        notes.append("missing_core_concepts=" + "|".join(missing_core))

    missing_cashflow = sorted({"cfo", "capex"}.difference(available))
    if missing_cashflow:
        notes.append("missing_cashflow_concepts=" + "|".join(missing_cashflow))

    red_concepts = sorted([c for c, f in concept_flags.items() if str(f).upper() == "RED"])
    yellow_concepts = sorted([c for c, f in concept_flags.items() if str(f).upper() == "YELLOW"])
    if red_concepts:
        notes.append("red_fact_quality=" + "|".join(red_concepts))
    if yellow_concepts:
        notes.append("yellow_fact_quality=" + "|".join(yellow_concepts))

    unavailable_ratios = sorted([k for k, v in ratios.items() if v is None])
    if unavailable_ratios:
        notes.append("unavailable_ratios=" + "|".join(unavailable_ratios[:8]))

    if red_concepts or missing_core:
        return "RED", ";".join(notes)
    if yellow_concepts or missing_cashflow or unavailable_ratios:
        return "YELLOW", ";".join(notes)
    return "GREEN", ""


def build_fundamental_features_asof_dataframe(config: FundamentalFeaturesConfig) -> pd.DataFrame:
    facts = read_table(config.accounting_fact_selected_path)
    availability = _availability_lookup(config.filing_availability_path)

    if facts.empty:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []

    for accession, group in facts.groupby("accession_number"):
        best = _best_fact_per_concept(group)
        first = best.iloc[0].to_dict()

        cik10 = str(first.get("cik10", "") or "")
        accession_number = str(first.get("accession_number", accession) or accession)
        row: dict[str, Any] = {
            "cik": first.get("cik", ""),
            "cik10": cik10,
            "accession_number": accession_number,
            "accession_lineage_key": first.get("accession_lineage_key", f"{cik10}:{accession_number}"),
            "form": first.get("form", ""),
            "period": first.get("period", ""),
            "fy": first.get("fy", ""),
            "fp": first.get("fp", ""),
            "filed": first.get("filed", ""),
            "accepted": first.get("accepted", ""),
            "fundamental_feature_version": config.feature_version,
        }

        values: dict[str, float | None] = {concept: None for concept in VALUE_CONCEPTS}
        available_concepts: set[str] = set()
        concept_quality_flags: dict[str, str] = {}

        for concept in VALUE_CONCEPTS:
            concept_row = best[best["canonical_concept"] == concept]
            if concept_row.empty:
                row[f"{concept}_available"] = False
                row[f"{concept}_fact_quality_flag"] = "MISSING"
                row[f"{concept}_selected_tag"] = ""
                row[f"{concept}_uom"] = ""
                row[f"{concept}_qtrs"] = ""
                row[concept] = None
                continue

            c = concept_row.iloc[0].to_dict()
            value = _to_float(c.get("value"))
            values[concept] = value
            available_concepts.add(concept)
            qflag = str(c.get("fact_quality_flag", "") or "")
            concept_quality_flags[concept] = qflag

            row[concept] = value
            row[f"{concept}_available"] = True
            row[f"{concept}_fact_quality_flag"] = qflag
            row[f"{concept}_fact_quality_notes"] = c.get("fact_quality_notes", "")
            row[f"{concept}_selected_tag"] = c.get("selected_tag", "")
            row[f"{concept}_uom"] = c.get("uom", "")
            row[f"{concept}_qtrs"] = c.get("qtrs", "")
            row[f"{concept}_ddate"] = c.get("ddate", "")

        ratios = {
            "net_margin": _safe_divide(values["net_income"], values["revenue"]),
            "cfo_to_net_income": _safe_divide(values["cfo"], values["net_income"]),
            "cfo_to_revenue": _safe_divide(values["cfo"], values["revenue"]),
            "liabilities_to_assets": _safe_divide(values["liabilities"], values["assets"]),
            "debt_to_assets": _safe_divide(values["debt"], values["assets"]),
            "cash_to_assets": _safe_divide(values["cash"], values["assets"]),
            "receivables_to_assets": _safe_divide(values["receivables"], values["assets"]),
            "inventory_to_assets": _safe_divide(values["inventory"], values["assets"]),
            "capex_to_revenue": _safe_divide(values["capex"], values["revenue"]),
            "asset_turnover": _safe_divide(values["revenue"], values["assets"]),
            "cash_minus_debt_to_assets": _safe_divide(
                (values["cash"] - values["debt"]) if values["cash"] is not None and values["debt"] is not None else None,
                values["assets"],
            ),
            "working_capital_proxy_to_assets": _safe_divide(
                (
                    (values["cash"] or 0.0)
                    + (values["receivables"] or 0.0)
                    + (values["inventory"] or 0.0)
                    - (values["liabilities"] or 0.0)
                )
                if values["assets"] is not None
                else None,
                values["assets"],
            ),
        }
        row.update(ratios)

        availability_row = _availability_for_accession(row, availability)
        row["feature_asof_date"] = availability_row.get("first_allowed_execution_date", "")
        row["accepted_at_edgar"] = availability_row.get("accepted_at_edgar", "")
        row["timestamp_quality_flag"] = availability_row.get("timestamp_quality_flag", "")

        coverage_count = len(available_concepts)
        row["fundamental_coverage_count"] = coverage_count
        row["fundamental_coverage_ratio"] = coverage_count / len(VALUE_CONCEPTS)
        qflag, qnotes = _coverage_quality(available_concepts, concept_quality_flags, ratios)
        row["fundamental_quality_flag"] = qflag
        row["fundamental_quality_notes"] = qnotes

        rows.append(row)

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values(["cik10", "accession_number"]).reset_index(drop=True)
    return df


def build_fundamental_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    if df.empty:
        return pd.DataFrame([{"diagnostic": "rows", "value": 0}])

    rows.append({"diagnostic": "rows", "value": len(df)})
    rows.append({"diagnostic": "distinct_cik10", "value": df["cik10"].nunique() if "cik10" in df else 0})

    for concept in VALUE_CONCEPTS:
        col = f"{concept}_available"
        rows.append(
            {
                "diagnostic": f"{concept}_coverage",
                "value": float(df[col].mean()) if col in df else 0.0,
            }
        )

    if "fundamental_quality_flag" in df:
        for flag, count in df["fundamental_quality_flag"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"quality_flag_{flag}", "value": int(count)})

    return pd.DataFrame(rows)


def write_fundamental_features_outputs(
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


def build_fundamental_features_asof(config: FundamentalFeaturesConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.fundamental_features_asof",
        root() / "logs/pipeline/fundamental_features_asof.log",
    )
    logger.info("Building fundamental_features_asof from %s", config.accounting_fact_selected_path)
    df = build_fundamental_features_asof_dataframe(config)
    diagnostics = build_fundamental_diagnostics(df)
    write_fundamental_features_outputs(
        df,
        diagnostics,
        output_table_path=config.output_table_path,
        output_csv_path=config.output_csv_path,
        diagnostics_path=config.diagnostics_path,
    )
    logger.info("Wrote %d fundamental feature rows to %s", len(df), config.output_table_path)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Build accession-level Fundamental Reality features.")
    parser.add_argument("--accounting-fact-selected-path", default="data/processed/source_tables/accounting_fact_selected.csv")
    parser.add_argument("--filing-availability-path", default="data/processed/point_in_time/filing_availability.csv")
    parser.add_argument("--output-table", default="data/processed/features/fundamental_features_asof.parquet")
    parser.add_argument("--output-csv", default="data/processed/features/fundamental_features_asof.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/fundamental_features_asof_diagnostics.csv")
    args = parser.parse_args()

    config = FundamentalFeaturesConfig(
        accounting_fact_selected_path=root() / args.accounting_fact_selected_path,
        filing_availability_path=root() / args.filing_availability_path if args.filing_availability_path else None,
        output_table_path=root() / args.output_table,
        output_csv_path=root() / args.output_csv,
        diagnostics_path=root() / args.diagnostics_path,
    )
    build_fundamental_features_asof(config)


if __name__ == "__main__":
    main()
