from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


MODEL_RESEARCH_PANEL_VERSION = "MODEL_RESEARCH_PANEL_V0"


@dataclass(frozen=True)
class ResearchPanelConfig:
    mismatch_features_path: Path
    fundamental_features_path: Path
    text_features_path: Path
    filing_availability_path: Path | None
    output_table_path: Path
    output_csv_path: Path
    diagnostics_path: Path
    panel_version: str = MODEL_RESEARCH_PANEL_VERSION
    require_mismatch_quality_green_or_yellow: bool = True
    require_feature_asof_date: bool = True
    require_timestamp_quality_green_or_yellow: bool = True


CORE_PANEL_COLUMNS = [
    "panel_row_id",
    "cik",
    "cik10",
    "accession_number",
    "primary_document",
    "accession_lineage_key",
    "accession_key",
    "feature_asof_date",
    "accepted_at_edgar",
    "timestamp_quality_flag",
    "panel_eligible",
    "panel_quality_flag",
    "panel_quality_notes",
    "panel_version",
    "lineage_mismatch_features_version",
    "lineage_fundamental_features_version",
    "lineage_text_features_version",
    "lineage_filing_availability_version",
]


def read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input table not found: {p}")
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    return pd.read_csv(p, dtype=str).fillna("")


def _join_key(df: pd.DataFrame) -> pd.Series:
    if {"cik10", "accession_number"}.issubset(df.columns):
        return df["cik10"].astype(str) + ":" + df["accession_number"].astype(str)
    if "accession_lineage_key" in df.columns:
        return df["accession_lineage_key"].astype(str).str.split(":").str[:2].str.join(":")
    raise ValueError("Input table requires cik10/accession_number or accession_lineage_key.")


def _primary_join_key(df: pd.DataFrame) -> pd.Series:
    if {"cik10", "accession_number", "primary_document"}.issubset(df.columns):
        return df["cik10"].astype(str) + ":" + df["accession_number"].astype(str) + ":" + df["primary_document"].astype(str)
    if "accession_lineage_key" in df.columns:
        return df["accession_lineage_key"].astype(str)
    return _join_key(df)


def _prefix_non_key_columns(df: pd.DataFrame, prefix: str, key_cols: set[str]) -> pd.DataFrame:
    out = df.copy()
    rename = {}
    for col in out.columns:
        if col in key_cols:
            continue
        if col.startswith(prefix + "_"):
            continue
        rename[col] = f"{prefix}_{col}"
    return out.rename(columns=rename)


def _dedupe_by_key(df: pd.DataFrame, key_col: str, preferred_quality_col: str | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()

    if preferred_quality_col and preferred_quality_col in out.columns:
        rank_col = "__quality_rank"
        out[rank_col] = out[preferred_quality_col].map(_quality_rank)
        sort_cols = [key_col, rank_col]
    else:
        rank_col = None
        sort_cols = [key_col]

    if "feature_asof_date" in out.columns:
        out["__asof_sort"] = pd.to_datetime(out["feature_asof_date"], errors="coerce")
        sort_cols.append("__asof_sort")

    out = out.sort_values(sort_cols, na_position="last").drop_duplicates(subset=[key_col], keep="first")
    drop_cols = [c for c in ["__quality_rank", "__asof_sort"] if c in out.columns]
    return out.drop(columns=drop_cols)


def _quality_rank(flag: Any) -> int:
    flag = str(flag or "").upper()
    if flag == "GREEN":
        return 0
    if flag == "YELLOW":
        return 1
    if flag == "RED":
        return 2
    if flag in {"", "MISSING"}:
        return 3
    return 4


def _quality_flag_for_panel(row: pd.Series, config: ResearchPanelConfig) -> tuple[bool, str, str]:
    notes: list[str] = []

    mismatch_quality = str(row.get("mismatch_quality_flag", "") or "").upper()
    fundamental_quality = str(row.get("fund_fundamental_quality_flag", "") or "").upper()
    text_parse_quality = str(row.get("text_full_parse_quality_flag", "") or "").upper()
    timestamp_quality = str(row.get("timestamp_quality_flag", "") or "").upper()
    asof_date = str(row.get("feature_asof_date", "") or "").strip()

    if config.require_feature_asof_date and not asof_date:
        notes.append("missing_feature_asof_date")

    if config.require_mismatch_quality_green_or_yellow:
        if mismatch_quality not in {"GREEN", "YELLOW"}:
            notes.append(f"bad_mismatch_quality={mismatch_quality or 'MISSING'}")

    if config.require_timestamp_quality_green_or_yellow:
        if timestamp_quality not in {"GREEN", "YELLOW"}:
            notes.append(f"bad_timestamp_quality={timestamp_quality or 'MISSING'}")

    if fundamental_quality == "RED":
        notes.append("fundamental_quality_red")
    elif fundamental_quality == "":
        notes.append("fundamental_quality_missing")

    if text_parse_quality == "RED":
        notes.append("text_parse_quality_red")
    elif text_parse_quality == "":
        notes.append("text_parse_quality_missing")

    if not str(row.get("mismatch_dfm_score_simple", row.get("dfm_score_simple", ""))).strip():
        notes.append("missing_dfm_score_simple")

    if any("red" in note or note.startswith("bad_") or note.startswith("missing_") for note in notes):
        return False, "RED", ";".join(notes)
    if notes:
        return True, "YELLOW", ";".join(notes)
    return True, "GREEN", ""


def _lineage_value(df: pd.DataFrame, candidates: list[str]) -> str:
    for col in candidates:
        if col in df.columns:
            series = df[col].dropna().astype(str)
            if not series.empty:
                values = sorted(set(series[series.str.len() > 0]))
                if values:
                    return values[0]
    return ""


def _select_availability_columns(availability: pd.DataFrame) -> pd.DataFrame:
    if availability.empty:
        return availability
    cols = [
        "accession_key",
        "availability_accepted_at_edgar",
        "availability_first_allowed_execution_date",
        "availability_timestamp_quality_flag",
        "availability_header_source_file",
    ]
    out = pd.DataFrame()
    out["accession_key"] = _join_key(availability)
    source_map = {
        "accepted_at_edgar": "availability_accepted_at_edgar",
        "first_allowed_execution_date": "availability_first_allowed_execution_date",
        "timestamp_quality_flag": "availability_timestamp_quality_flag",
        "header_source_file": "availability_header_source_file",
    }
    for source, dest in source_map.items():
        out[dest] = availability[source] if source in availability.columns else ""
    return _dedupe_by_key(out[cols], "accession_key")


def build_model_research_panel_dataframe(config: ResearchPanelConfig) -> pd.DataFrame:
    mismatch = read_table(config.mismatch_features_path)
    fundamental = read_table(config.fundamental_features_path)
    text = read_table(config.text_features_path)
    availability = read_table(config.filing_availability_path) if config.filing_availability_path and Path(config.filing_availability_path).exists() else pd.DataFrame()

    if mismatch.empty:
        return pd.DataFrame()

    mismatch = mismatch.copy()
    fundamental = fundamental.copy()
    text = text.copy()

    mismatch["primary_join_key"] = _primary_join_key(mismatch)
    mismatch["accession_key"] = _join_key(mismatch)
    fundamental["accession_key"] = _join_key(fundamental)
    text["primary_join_key"] = _primary_join_key(text)
    text["accession_key"] = _join_key(text)

    mismatch = _dedupe_by_key(mismatch, "primary_join_key", preferred_quality_col="mismatch_quality_flag")
    fundamental = _dedupe_by_key(fundamental, "accession_key", preferred_quality_col="fundamental_quality_flag")
    text = _dedupe_by_key(text, "primary_join_key", preferred_quality_col="full_parse_quality_flag")

    # Preserve natural core columns from mismatch, because it is already the final signal layer.
    fund_key_cols = {"accession_key"}
    text_key_cols = {"primary_join_key", "accession_key"}

    fundamental_prefixed = _prefix_non_key_columns(fundamental, "fund", fund_key_cols)
    text_prefixed = _prefix_non_key_columns(text, "text", text_key_cols)

    panel = mismatch.merge(fundamental_prefixed, on="accession_key", how="left")
    panel = panel.merge(text_prefixed, on=["primary_join_key", "accession_key"], how="left")

    if not availability.empty:
        availability_selected = _select_availability_columns(availability)
        panel = panel.merge(availability_selected, on="accession_key", how="left")

        # Fill canonical panel metadata from availability when feature layers are missing.
        if "accepted_at_edgar" in panel.columns and "availability_accepted_at_edgar" in panel.columns:
            panel["accepted_at_edgar"] = panel["accepted_at_edgar"].replace("", pd.NA).fillna(panel["availability_accepted_at_edgar"]).fillna("")
        if "feature_asof_date" in panel.columns and "availability_first_allowed_execution_date" in panel.columns:
            panel["feature_asof_date"] = panel["feature_asof_date"].replace("", pd.NA).fillna(panel["availability_first_allowed_execution_date"]).fillna("")
        if "timestamp_quality_flag" in panel.columns and "availability_timestamp_quality_flag" in panel.columns:
            panel["timestamp_quality_flag"] = panel["timestamp_quality_flag"].replace("", pd.NA).fillna(panel["availability_timestamp_quality_flag"]).fillna("")

    panel["panel_version"] = config.panel_version
    panel["lineage_mismatch_features_version"] = _lineage_value(mismatch, ["mismatch_feature_version"])
    panel["lineage_fundamental_features_version"] = _lineage_value(fundamental, ["fundamental_feature_version"])
    panel["lineage_text_features_version"] = _lineage_value(text, ["text_feature_version"])
    panel["lineage_filing_availability_version"] = "filing_availability_v0" if not availability.empty else ""

    eligibility_rows = panel.apply(lambda row: _quality_flag_for_panel(row, config), axis=1)
    panel["panel_eligible"] = [item[0] for item in eligibility_rows]
    panel["panel_quality_flag"] = [item[1] for item in eligibility_rows]
    panel["panel_quality_notes"] = [item[2] for item in eligibility_rows]

    panel["panel_row_id"] = (
        panel["cik10"].astype(str)
        + ":"
        + panel["accession_number"].astype(str)
        + ":"
        + panel.get("primary_document", "").astype(str)
    )

    # Put core panel columns first, then all feature columns.
    for col in CORE_PANEL_COLUMNS:
        if col not in panel.columns:
            panel[col] = ""

    drop_cols = [c for c in ["primary_join_key"] if c in panel.columns]
    panel = panel.drop(columns=drop_cols)

    ordered_cols = CORE_PANEL_COLUMNS + [c for c in panel.columns if c not in CORE_PANEL_COLUMNS]
    panel = panel[ordered_cols].sort_values(["cik10", "accession_number", "primary_document"]).reset_index(drop=True)
    return panel


def build_model_research_panel_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame([{"diagnostic": "rows", "value": 0}])

    rows: list[dict[str, Any]] = [
        {"diagnostic": "rows", "value": len(df)},
        {"diagnostic": "eligible_rows", "value": int(df["panel_eligible"].astype(bool).sum()) if "panel_eligible" in df else 0},
        {"diagnostic": "distinct_cik10", "value": df["cik10"].nunique() if "cik10" in df else 0},
        {"diagnostic": "distinct_accessions", "value": df["accession_key"].nunique() if "accession_key" in df else 0},
        {"diagnostic": "feature_columns", "value": len(df.columns)},
    ]

    if "panel_quality_flag" in df:
        for flag, count in df["panel_quality_flag"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"panel_quality_flag_{flag}", "value": int(count)})

    for col in ["mismatch_quality_flag", "fund_fundamental_quality_flag", "text_full_parse_quality_flag", "timestamp_quality_flag"]:
        if col in df.columns:
            for flag, count in df[col].value_counts(dropna=False).items():
                rows.append({"diagnostic": f"{col}_{flag}", "value": int(count)})

    return pd.DataFrame(rows)


def write_model_research_panel_outputs(
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


def build_model_research_panel(config: ResearchPanelConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.model_research_panel",
        root() / "logs/pipeline/model_research_panel.log",
    )
    logger.info("Building model research panel from mismatch, fundamental, text, and availability layers")
    df = build_model_research_panel_dataframe(config)
    diagnostics = build_model_research_panel_diagnostics(df)
    write_model_research_panel_outputs(
        df,
        diagnostics,
        output_table_path=config.output_table_path,
        output_csv_path=config.output_csv_path,
        diagnostics_path=config.diagnostics_path,
    )
    logger.info("Wrote %d model research panel rows to %s", len(df), config.output_table_path)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Assemble model research panel.")
    parser.add_argument("--mismatch-features-path", default="data/processed/features/mismatch_features_asof.csv")
    parser.add_argument("--fundamental-features-path", default="data/processed/features/fundamental_features_asof.csv")
    parser.add_argument("--text-features-path", default="data/processed/features/text_features_asof.csv")
    parser.add_argument("--filing-availability-path", default="data/processed/point_in_time/filing_availability.csv")
    parser.add_argument("--output-table", default="data/processed/model/model_research_panel.parquet")
    parser.add_argument("--output-csv", default="data/processed/model/model_research_panel.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/model_research_panel_diagnostics.csv")
    parser.add_argument("--allow-red-mismatch-quality", action="store_true")
    parser.add_argument("--allow-missing-asof-date", action="store_true")
    parser.add_argument("--allow-red-timestamp-quality", action="store_true")
    args = parser.parse_args()

    config = ResearchPanelConfig(
        mismatch_features_path=root() / args.mismatch_features_path,
        fundamental_features_path=root() / args.fundamental_features_path,
        text_features_path=root() / args.text_features_path,
        filing_availability_path=root() / args.filing_availability_path if args.filing_availability_path else None,
        output_table_path=root() / args.output_table,
        output_csv_path=root() / args.output_csv,
        diagnostics_path=root() / args.diagnostics_path,
        require_mismatch_quality_green_or_yellow=not args.allow_red_mismatch_quality,
        require_feature_asof_date=not args.allow_missing_asof_date,
        require_timestamp_quality_green_or_yellow=not args.allow_red_timestamp_quality,
    )
    build_model_research_panel(config)


if __name__ == "__main__":
    main()
