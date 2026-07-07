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


MODEL_DATASET_VERSION = "MODEL_DATASET_V0"

LABEL_COLUMNS = [
    "y_forward_63d_sector_adjusted_return",
    "y_forward_63d_raw_return",
    "y_forward_63d_sector_return",
]

TARGET_SOURCE_COLUMNS = [
    "forward_63d_sector_adjusted_return",
    "forward_63d_raw_return",
    "forward_63d_sector_return",
]

CORE_DATASET_COLUMNS = [
    "model_row_id",
    "panel_row_id",
    "cik",
    "cik10",
    "ticker",
    "sector",
    "accession_number",
    "primary_document",
    "accession_lineage_key",
    "feature_asof_date",
    "target_entry_date",
    "target_exit_date",
    "target_horizon_trading_days",
    "y_forward_63d_sector_adjusted_return",
    "y_forward_63d_raw_return",
    "y_forward_63d_sector_return",
    "sample_weight",
    "dataset_split_status",
    "model_dataset_eligible",
    "model_dataset_quality_flag",
    "model_dataset_quality_notes",
    "model_dataset_version",
    "lineage_model_research_panel_version",
    "lineage_return_target_version",
    "model_feature_count",
    "model_feature_columns",
]


LEAKAGE_EXCLUDE_EXACT = {
    "target_available",
    "target_quality_flag",
    "target_quality_notes",
    "target_version",
    "target_entry_date",
    "target_exit_date",
    "target_horizon_trading_days",
    "forward_63d_raw_return",
    "forward_63d_sector_return",
    "forward_63d_sector_adjusted_return",
    "y_forward_63d_raw_return",
    "y_forward_63d_sector_return",
    "y_forward_63d_sector_adjusted_return",
    "model_dataset_eligible",
    "model_dataset_quality_flag",
    "model_dataset_quality_notes",
    "model_dataset_version",
    "model_feature_columns",
    "model_feature_count",
    "sample_weight",
    "dataset_split_status",
}


LEAKAGE_EXCLUDE_PREFIXES = (
    "target_",
    "y_",
    "forward_",
)


NON_FEATURE_COLUMNS = {
    "model_row_id",
    "panel_row_id",
    "cik",
    "cik10",
    "ticker",
    "sector",
    "accession_number",
    "primary_document",
    "accession_lineage_key",
    "feature_asof_date",
    "accepted_at_edgar",
    "panel_version",
    "panel_eligible",
    "panel_quality_flag",
    "panel_quality_notes",
    "lineage_mismatch_features_version",
    "lineage_fundamental_features_version",
    "lineage_text_features_version",
    "lineage_filing_availability_version",
    "lineage_model_research_panel_version",
    "lineage_return_target_version",
}


@dataclass(frozen=True)
class ModelDatasetConfig:
    model_research_panel_path: Path
    return_targets_path: Path
    output_table_path: Path
    output_csv_path: Path
    diagnostics_path: Path
    dataset_version: str = MODEL_DATASET_VERSION
    require_panel_eligible: bool = True
    require_target_available: bool = True
    allow_yellow_panel_quality: bool = True
    allow_yellow_target_quality: bool = True
    require_nonmissing_label: bool = True
    require_target_after_feature_asof: bool = True


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
    clean = str(value or "").strip().lower()
    return clean in {"true", "1", "yes", "y"}


def _quality_allowed(flag: Any, *, allow_yellow: bool) -> bool:
    clean = str(flag or "").strip().upper()
    allowed = {"GREEN"}
    if allow_yellow:
        allowed.add("YELLOW")
    return clean in allowed


def _join_key(df: pd.DataFrame) -> pd.Series:
    if "panel_row_id" in df.columns:
        return df["panel_row_id"].astype(str)
    if "accession_lineage_key" in df.columns:
        return df["accession_lineage_key"].astype(str)
    if {"cik10", "accession_number", "primary_document"}.issubset(df.columns):
        return df["cik10"].astype(str) + ":" + df["accession_number"].astype(str) + ":" + df["primary_document"].astype(str)
    raise ValueError("Input requires panel_row_id, accession_lineage_key, or cik10/accession_number/primary_document.")


def _dedupe_by_join_key(df: pd.DataFrame, quality_col: str | None = None) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["_model_dataset_join_key"] = _join_key(out)
    if quality_col and quality_col in out.columns:
        out["_quality_rank"] = out[quality_col].map(_quality_rank)
    else:
        out["_quality_rank"] = 99
    if "feature_asof_date" in out.columns:
        out["_asof_sort"] = pd.to_datetime(out["feature_asof_date"], errors="coerce")
    else:
        out["_asof_sort"] = pd.NaT
    out = out.sort_values(["_model_dataset_join_key", "_quality_rank", "_asof_sort"]).drop_duplicates(
        subset=["_model_dataset_join_key"],
        keep="first",
    )
    return out.drop(columns=["_quality_rank", "_asof_sort"])


def _quality_rank(flag: Any) -> int:
    clean = str(flag or "").upper()
    if clean == "GREEN":
        return 0
    if clean == "YELLOW":
        return 1
    if clean == "RED":
        return 2
    return 3


def _lineage_value(df: pd.DataFrame, candidates: list[str], fallback: str = "") -> str:
    for col in candidates:
        if col in df.columns:
            values = sorted(set(df[col].dropna().astype(str)))
            values = [v for v in values if v]
            if values:
                return values[0]
    return fallback


def join_panel_and_targets(panel: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    panel = _dedupe_by_join_key(panel, "panel_quality_flag")
    targets = _dedupe_by_join_key(targets, "target_quality_flag")

    joined = panel.merge(
        targets,
        on="_model_dataset_join_key",
        how="left",
        suffixes=("", "_target"),
    )

    # Fill target identifiers from panel where suffixing created duplicates.
    for col in ["ticker", "sector", "target_entry_date", "target_exit_date", "target_horizon_trading_days"]:
        target_col = f"{col}_target"
        if col not in joined.columns and target_col in joined.columns:
            joined[col] = joined[target_col]
        elif col in joined.columns and target_col in joined.columns:
            joined[col] = joined[col].replace("", pd.NA).fillna(joined[target_col]).fillna("")

    return joined


def _dataset_quality(row: pd.Series, config: ModelDatasetConfig) -> tuple[bool, str, str]:
    notes: list[str] = []

    panel_eligible = _as_bool(row.get("panel_eligible", False))
    target_available = _as_bool(row.get("target_available", False))
    panel_quality = row.get("panel_quality_flag", "")
    target_quality = row.get("target_quality_flag", "")

    if config.require_panel_eligible and not panel_eligible:
        notes.append("panel_not_eligible")

    if not _quality_allowed(panel_quality, allow_yellow=config.allow_yellow_panel_quality):
        notes.append(f"bad_panel_quality={str(panel_quality or 'MISSING').upper()}")

    if config.require_target_available and not target_available:
        notes.append("target_not_available")

    if not _quality_allowed(target_quality, allow_yellow=config.allow_yellow_target_quality):
        notes.append(f"bad_target_quality={str(target_quality or 'MISSING').upper()}")

    label = _to_float(row.get("forward_63d_sector_adjusted_return", None))
    if config.require_nonmissing_label and label is None:
        notes.append("missing_primary_label_forward_63d_sector_adjusted_return")

    feature_asof = pd.to_datetime(row.get("feature_asof_date", ""), errors="coerce")
    target_entry = pd.to_datetime(row.get("target_entry_date", ""), errors="coerce")
    target_exit = pd.to_datetime(row.get("target_exit_date", ""), errors="coerce")

    if config.require_target_after_feature_asof:
        if pd.isna(feature_asof):
            notes.append("missing_or_invalid_feature_asof_date")
        if pd.isna(target_entry):
            notes.append("missing_or_invalid_target_entry_date")
        if pd.isna(target_exit):
            notes.append("missing_or_invalid_target_exit_date")
        if pd.notna(feature_asof) and pd.notna(target_entry) and target_entry < feature_asof:
            notes.append("target_entry_before_feature_asof")
        if pd.notna(target_entry) and pd.notna(target_exit) and target_exit <= target_entry:
            notes.append("target_exit_not_after_entry")

    if any(note.startswith("bad_") or note.startswith("missing_") or note.endswith("_not_available") or note.endswith("_not_eligible") or "before" in note for note in notes):
        return False, "RED", ";".join(notes)
    if notes:
        return True, "YELLOW", ";".join(notes)
    return True, "GREEN", ""


def _is_model_feature_column(col: str) -> bool:
    if col in CORE_DATASET_COLUMNS or col in NON_FEATURE_COLUMNS or col in LEAKAGE_EXCLUDE_EXACT:
        return False
    if any(col.startswith(prefix) for prefix in LEAKAGE_EXCLUDE_PREFIXES):
        return False
    if col.endswith("_target"):
        return False
    if col.startswith("lineage_"):
        return False
    if col.startswith("availability_"):
        return False

    # Prefer numeric or signal-bearing columns. Keep quality flags out.
    if col.endswith("_quality_flag") or col.endswith("_quality_notes"):
        return False
    if col.endswith("_version") or col.endswith("_source_col"):
        return False
    return True


def candidate_model_feature_columns(df: pd.DataFrame) -> list[str]:
    features: list[str] = []
    for col in df.columns:
        if not _is_model_feature_column(col):
            continue
        numeric = pd.to_numeric(df[col], errors="coerce")
        if numeric.notna().any():
            features.append(col)
    return sorted(features)


def build_model_dataset_dataframe(config: ModelDatasetConfig) -> pd.DataFrame:
    panel = read_table(config.model_research_panel_path)
    targets = read_table(config.return_targets_path)

    if panel.empty:
        return pd.DataFrame()

    panel_lineage = _lineage_value(panel, ["panel_version"], fallback="MODEL_RESEARCH_PANEL_V0")
    target_lineage = _lineage_value(targets, ["target_version"], fallback="RETURN_TARGETS_V0")

    joined = join_panel_and_targets(panel, targets)
    rows: list[dict[str, Any]] = []

    # Compute feature candidates after join; then save same list on each row for auditability.
    feature_columns = candidate_model_feature_columns(joined)
    feature_columns_str = ",".join(feature_columns)

    for _, row in joined.iterrows():
        eligible, quality_flag, quality_notes = _dataset_quality(row, config)

        out = row.to_dict()
        out["model_row_id"] = str(row.get("panel_row_id", row.get("_model_dataset_join_key", "")))
        out["y_forward_63d_sector_adjusted_return"] = _to_float(row.get("forward_63d_sector_adjusted_return", None))
        out["y_forward_63d_raw_return"] = _to_float(row.get("forward_63d_raw_return", None))
        out["y_forward_63d_sector_return"] = _to_float(row.get("forward_63d_sector_return", None))
        out["sample_weight"] = 1.0 if eligible else 0.0
        out["dataset_split_status"] = "unassigned"
        out["model_dataset_eligible"] = eligible
        out["model_dataset_quality_flag"] = quality_flag
        out["model_dataset_quality_notes"] = quality_notes
        out["model_dataset_version"] = config.dataset_version
        out["lineage_model_research_panel_version"] = panel_lineage
        out["lineage_return_target_version"] = target_lineage
        out["model_feature_count"] = len(feature_columns)
        out["model_feature_columns"] = feature_columns_str
        rows.append(out)

    df = pd.DataFrame(rows)

    # Ensure all core columns exist.
    for col in CORE_DATASET_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # Drop internal helper.
    if "_model_dataset_join_key" in df.columns:
        df = df.drop(columns=["_model_dataset_join_key"])

    ordered = CORE_DATASET_COLUMNS + [c for c in df.columns if c not in CORE_DATASET_COLUMNS]
    df = df[ordered].sort_values(["cik10", "accession_number", "primary_document"]).reset_index(drop=True)
    return df


def build_model_dataset_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame([{"diagnostic": "rows", "value": 0}])

    rows: list[dict[str, Any]] = [
        {"diagnostic": "rows", "value": len(df)},
        {"diagnostic": "eligible_rows", "value": int(df["model_dataset_eligible"].astype(bool).sum()) if "model_dataset_eligible" in df else 0},
        {"diagnostic": "distinct_cik10", "value": df["cik10"].nunique() if "cik10" in df else 0},
        {"diagnostic": "distinct_accessions", "value": df["accession_number"].nunique() if "accession_number" in df else 0},
        {"diagnostic": "feature_count", "value": int(df["model_feature_count"].iloc[0]) if "model_feature_count" in df and len(df) else 0},
    ]

    for flag, count in df["model_dataset_quality_flag"].value_counts(dropna=False).items():
        rows.append({"diagnostic": f"model_dataset_quality_flag_{flag}", "value": int(count)})

    label = pd.to_numeric(df["y_forward_63d_sector_adjusted_return"], errors="coerce") if "y_forward_63d_sector_adjusted_return" in df else pd.Series(dtype=float)
    rows.extend(
        [
            {"diagnostic": "label_nonmissing_rows", "value": int(label.notna().sum())},
            {"diagnostic": "label_mean", "value": label.mean()},
            {"diagnostic": "label_median", "value": label.median()},
        ]
    )
    return pd.DataFrame(rows)


def write_model_dataset_outputs(
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


def build_model_dataset_v0(config: ModelDatasetConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.model_dataset_v0",
        root() / "logs/pipeline/model_dataset_v0.log",
    )
    logger.info("Building model_dataset_v0 from %s and %s", config.model_research_panel_path, config.return_targets_path)
    df = build_model_dataset_dataframe(config)
    diagnostics = build_model_dataset_diagnostics(df)
    write_model_dataset_outputs(
        df,
        diagnostics,
        output_table_path=config.output_table_path,
        output_csv_path=config.output_csv_path,
        diagnostics_path=config.diagnostics_path,
    )
    logger.info("Wrote %d model dataset rows to %s", len(df), config.output_table_path)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Build final modeling dataset v0.")
    parser.add_argument("--model-research-panel-path", default="data/processed/model/model_research_panel.csv")
    parser.add_argument("--return-targets-path", default="data/processed/targets/return_targets_asof.csv")
    parser.add_argument("--output-table", default="data/processed/model/model_dataset_v0.parquet")
    parser.add_argument("--output-csv", default="data/processed/model/model_dataset_v0.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/model_dataset_v0_diagnostics.csv")
    parser.add_argument("--allow-red-panel-quality", action="store_true")
    parser.add_argument("--allow-red-target-quality", action="store_true")
    parser.add_argument("--allow-missing-label", action="store_true")
    args = parser.parse_args()

    config = ModelDatasetConfig(
        model_research_panel_path=root() / args.model_research_panel_path,
        return_targets_path=root() / args.return_targets_path,
        output_table_path=root() / args.output_table,
        output_csv_path=root() / args.output_csv,
        diagnostics_path=root() / args.diagnostics_path,
        allow_yellow_panel_quality=True,
        allow_yellow_target_quality=True,
        require_nonmissing_label=not args.allow_missing_label,
    )
    build_model_dataset_v0(config)


if __name__ == "__main__":
    main()
