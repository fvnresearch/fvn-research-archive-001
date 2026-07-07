from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


WALK_FORWARD_SPLIT_VERSION = "WALK_FORWARD_SPLITS_V0"


@dataclass(frozen=True)
class WalkForwardSplitConfig:
    model_dataset_path: Path
    output_table_path: Path
    output_csv_path: Path
    diagnostics_path: Path
    split_version: str = WALK_FORWARD_SPLIT_VERSION
    min_train_months: int = 24
    validation_months: int = 12
    test_months: int = 1
    step_months: int = 1
    embargo_days: int = 63
    first_test_month: str | None = None
    max_folds: int | None = None
    require_eligible_rows: bool = True


SPLIT_COLUMNS = [
    "walk_forward_fold_id",
    "walk_forward_role",
    "walk_forward_train_start",
    "walk_forward_train_end",
    "walk_forward_validation_start",
    "walk_forward_validation_end",
    "walk_forward_test_start",
    "walk_forward_test_end",
    "walk_forward_embargo_days",
    "walk_forward_split_version",
]


def read_table(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Input table not found: {p}")
    if p.suffix == ".parquet":
        return pd.read_parquet(p)
    return pd.read_csv(p, dtype=str).fillna("")


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _month_start(value: pd.Timestamp) -> pd.Timestamp:
    return pd.Timestamp(year=value.year, month=value.month, day=1)


def _parse_month(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    ts = pd.to_datetime(value, errors="raise")
    return _month_start(ts)


def _date_str(value: pd.Timestamp | None) -> str:
    if value is None or pd.isna(value):
        return ""
    return pd.Timestamp(value).date().isoformat()


@dataclass(frozen=True)
class FoldWindow:
    fold_id: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    validation_start: pd.Timestamp
    validation_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    embargo_days: int


def generate_fold_windows(
    *,
    min_date: pd.Timestamp,
    max_date: pd.Timestamp,
    min_train_months: int,
    validation_months: int,
    test_months: int,
    step_months: int,
    embargo_days: int,
    first_test_month: str | None = None,
    max_folds: int | None = None,
) -> list[FoldWindow]:
    if pd.isna(min_date) or pd.isna(max_date):
        return []
    if min_date > max_date:
        return []

    first_test = _parse_month(first_test_month)
    if first_test is None:
        first_test = _month_start(min_date) + pd.DateOffset(months=min_train_months + validation_months)

    windows: list[FoldWindow] = []
    current_test_start = first_test

    while current_test_start <= max_date:
        test_start = current_test_start
        test_end = current_test_start + pd.DateOffset(months=test_months) - pd.Timedelta(days=1)

        validation_end = test_start - pd.Timedelta(days=embargo_days + 1)
        validation_start = validation_end - pd.DateOffset(months=validation_months) + pd.Timedelta(days=1)

        train_end = validation_start - pd.Timedelta(days=embargo_days + 1)
        train_start = min_date

        # Enforce minimum expanding train history.
        min_allowed_train_end = min_date + pd.DateOffset(months=min_train_months) - pd.Timedelta(days=1)
        if train_end >= min_allowed_train_end:
            fold_id = f"WF{len(windows) + 1:04d}_{test_start.strftime('%Y%m')}"
            windows.append(
                FoldWindow(
                    fold_id=fold_id,
                    train_start=train_start,
                    train_end=train_end,
                    validation_start=validation_start,
                    validation_end=validation_end,
                    test_start=test_start,
                    test_end=test_end,
                    embargo_days=embargo_days,
                )
            )

        if max_folds is not None and len(windows) >= max_folds:
            break

        current_test_start = current_test_start + pd.DateOffset(months=step_months)

    return windows


def assign_rows_to_fold(df: pd.DataFrame, window: FoldWindow) -> pd.DataFrame:
    out = df.copy()
    dates = out["_feature_asof_ts"]

    roles = pd.Series("", index=out.index, dtype="object")
    roles[(dates >= window.train_start) & (dates <= window.train_end)] = "train"
    roles[(dates >= window.validation_start) & (dates <= window.validation_end)] = "validation"
    roles[(dates >= window.test_start) & (dates <= window.test_end)] = "test"

    out = out[roles != ""].copy()
    out["walk_forward_role"] = roles[roles != ""]
    out["walk_forward_fold_id"] = window.fold_id
    out["walk_forward_train_start"] = _date_str(window.train_start)
    out["walk_forward_train_end"] = _date_str(window.train_end)
    out["walk_forward_validation_start"] = _date_str(window.validation_start)
    out["walk_forward_validation_end"] = _date_str(window.validation_end)
    out["walk_forward_test_start"] = _date_str(window.test_start)
    out["walk_forward_test_end"] = _date_str(window.test_end)
    out["walk_forward_embargo_days"] = window.embargo_days
    return out


def _prepare_dataset(df: pd.DataFrame, *, require_eligible_rows: bool) -> pd.DataFrame:
    out = df.copy()
    if "feature_asof_date" not in out.columns:
        raise ValueError("model_dataset_v0 requires feature_asof_date.")

    out["_feature_asof_ts"] = pd.to_datetime(out["feature_asof_date"], errors="coerce")
    out = out.dropna(subset=["_feature_asof_ts"]).copy()

    if require_eligible_rows and "model_dataset_eligible" in out.columns:
        out = out[out["model_dataset_eligible"].map(_as_bool)].copy()

    out = out.sort_values(["_feature_asof_ts", "cik10", "accession_number", "primary_document"]).reset_index(drop=True)
    return out


def build_model_dataset_with_splits_dataframe(config: WalkForwardSplitConfig) -> pd.DataFrame:
    source = _prepare_dataset(read_table(config.model_dataset_path), require_eligible_rows=config.require_eligible_rows)
    if source.empty:
        return pd.DataFrame()

    min_date = source["_feature_asof_ts"].min()
    max_date = source["_feature_asof_ts"].max()

    windows = generate_fold_windows(
        min_date=min_date,
        max_date=max_date,
        min_train_months=config.min_train_months,
        validation_months=config.validation_months,
        test_months=config.test_months,
        step_months=config.step_months,
        embargo_days=config.embargo_days,
        first_test_month=config.first_test_month,
        max_folds=config.max_folds,
    )

    parts: list[pd.DataFrame] = []
    for window in windows:
        part = assign_rows_to_fold(source, window)
        if not part.empty:
            parts.append(part)

    if not parts:
        return pd.DataFrame(columns=[*source.drop(columns=["_feature_asof_ts"]).columns, *SPLIT_COLUMNS])

    out = pd.concat(parts, ignore_index=True)
    out["walk_forward_split_version"] = config.split_version
    out = out.drop(columns=["_feature_asof_ts"], errors="ignore")

    # Put split columns up front after identifiers.
    for col in SPLIT_COLUMNS:
        if col not in out.columns:
            out[col] = ""

    preferred = [
        "model_row_id",
        "panel_row_id",
        "cik",
        "cik10",
        "ticker",
        "sector",
        "accession_number",
        "primary_document",
        "feature_asof_date",
        *SPLIT_COLUMNS,
    ]
    preferred = [c for c in preferred if c in out.columns]
    out = out[preferred + [c for c in out.columns if c not in preferred]]
    out = out.sort_values(["walk_forward_fold_id", "walk_forward_role", "feature_asof_date", "cik10", "accession_number"]).reset_index(drop=True)
    return out


def build_walk_forward_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame([{"diagnostic": "rows", "value": 0}])

    rows: list[dict[str, Any]] = [
        {"diagnostic": "rows", "value": len(df)},
        {"diagnostic": "folds", "value": df["walk_forward_fold_id"].nunique() if "walk_forward_fold_id" in df else 0},
        {"diagnostic": "distinct_model_rows", "value": df["model_row_id"].nunique() if "model_row_id" in df else 0},
    ]

    if "walk_forward_role" in df:
        for role, count in df["walk_forward_role"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"role_{role}_rows", "value": int(count)})

    if {"walk_forward_fold_id", "walk_forward_role"}.issubset(df.columns):
        fold_counts = (
            df.groupby(["walk_forward_fold_id", "walk_forward_role"])
            .size()
            .reset_index(name="rows")
        )
        for _, row in fold_counts.iterrows():
            rows.append(
                {
                    "diagnostic": f"{row['walk_forward_fold_id']}_{row['walk_forward_role']}_rows",
                    "value": int(row["rows"]),
                }
            )

    if "feature_asof_date" in df:
        rows.append({"diagnostic": "min_feature_asof_date", "value": str(pd.to_datetime(df["feature_asof_date"], errors="coerce").min().date())})
        rows.append({"diagnostic": "max_feature_asof_date", "value": str(pd.to_datetime(df["feature_asof_date"], errors="coerce").max().date())})

    return pd.DataFrame(rows)


def write_walk_forward_outputs(
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


def build_model_dataset_with_splits(config: WalkForwardSplitConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.walk_forward_splits",
        root() / "logs/pipeline/walk_forward_splits.log",
    )
    logger.info("Building walk-forward splits from %s", config.model_dataset_path)
    df = build_model_dataset_with_splits_dataframe(config)
    diagnostics = build_walk_forward_diagnostics(df)
    write_walk_forward_outputs(
        df,
        diagnostics,
        output_table_path=config.output_table_path,
        output_csv_path=config.output_csv_path,
        diagnostics_path=config.diagnostics_path,
    )
    logger.info("Wrote %d model_dataset_with_splits rows to %s", len(df), config.output_table_path)
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="Build walk-forward splits for model_dataset_v0.")
    parser.add_argument("--model-dataset-path", default="data/processed/model/model_dataset_v0.csv")
    parser.add_argument("--output-table", default="data/processed/model/model_dataset_with_splits.parquet")
    parser.add_argument("--output-csv", default="data/processed/model/model_dataset_with_splits.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/model_dataset_with_splits_diagnostics.csv")
    parser.add_argument("--min-train-months", type=int, default=24)
    parser.add_argument("--validation-months", type=int, default=12)
    parser.add_argument("--test-months", type=int, default=1)
    parser.add_argument("--step-months", type=int, default=1)
    parser.add_argument("--embargo-days", type=int, default=63)
    parser.add_argument("--first-test-month")
    parser.add_argument("--max-folds", type=int)
    parser.add_argument("--include-ineligible-rows", action="store_true")
    args = parser.parse_args()

    config = WalkForwardSplitConfig(
        model_dataset_path=root() / args.model_dataset_path,
        output_table_path=root() / args.output_table,
        output_csv_path=root() / args.output_csv,
        diagnostics_path=root() / args.diagnostics_path,
        min_train_months=args.min_train_months,
        validation_months=args.validation_months,
        test_months=args.test_months,
        step_months=args.step_months,
        embargo_days=args.embargo_days,
        first_test_month=args.first_test_month,
        max_folds=args.max_folds,
        require_eligible_rows=not args.include_ineligible_rows,
    )
    build_model_dataset_with_splits(config)


if __name__ == "__main__":
    main()
