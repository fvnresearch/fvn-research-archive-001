from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.normalization.sec_filing_event import normalize_cik_10
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


PRICE_RETURN_SOURCE_VERSION = "PRICE_RETURN_SOURCE_V0"

REQUIRED_PRICE_COLUMNS = {"date", "adj_close"}
IDENTIFIER_COLUMNS = {"ticker", "cik10"}
OPTIONAL_PRICE_COLUMNS = {"sector", "industry", "exchange", "source"}


@dataclass(frozen=True)
class PriceReturnIngestionConfig:
    raw_price_path: Path
    output_table_path: Path
    output_csv_path: Path
    diagnostics_path: Path


def read_price_csv(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Price input not found: {p}")
    return pd.read_csv(p, dtype=str).fillna("")


def normalize_price_table(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [c.strip().lower() for c in out.columns]

    missing = REQUIRED_PRICE_COLUMNS.difference(out.columns)
    if missing:
        raise ValueError(f"Price table missing required columns: {sorted(missing)}")

    if not IDENTIFIER_COLUMNS.intersection(out.columns):
        raise ValueError("Price table requires at least one identifier column: ticker or cik10")

    if "ticker" not in out.columns:
        out["ticker"] = ""
    if "cik10" not in out.columns:
        out["cik10"] = ""
    if "sector" not in out.columns:
        out["sector"] = "UNKNOWN"

    out["ticker"] = out["ticker"].astype(str).str.strip().str.upper()
    out["cik10"] = out["cik10"].astype(str).map(lambda x: normalize_cik_10(x) if x.strip() else "")
    out["sector"] = out["sector"].replace("", "UNKNOWN").fillna("UNKNOWN").astype(str)
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["adj_close"] = pd.to_numeric(out["adj_close"], errors="coerce")

    out = out.dropna(subset=["date", "adj_close"]).copy()
    out = out[(out["ticker"].str.len() > 0) | (out["cik10"].str.len() > 0)].copy()
    out["price_return_source_version"] = PRICE_RETURN_SOURCE_VERSION

    out = out.sort_values(["ticker", "cik10", "date"]).drop_duplicates(
        subset=["ticker", "cik10", "date"],
        keep="last",
    ).reset_index(drop=True)

    return out


def compute_daily_returns(price_df: pd.DataFrame) -> pd.DataFrame:
    out = normalize_price_table(price_df)
    grouping_key = "ticker" if out["ticker"].astype(str).str.len().gt(0).any() else "cik10"
    out["daily_return"] = out.groupby(grouping_key)["adj_close"].pct_change()
    out["trading_day_index"] = out.groupby(grouping_key).cumcount()
    return out


def build_price_return_source(config: PriceReturnIngestionConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.price_return_source",
        root() / "logs/pipeline/price_return_source.log",
    )
    logger.info("Building normalized price return source from %s", config.raw_price_path)

    raw = read_price_csv(config.raw_price_path)
    out = compute_daily_returns(raw)
    diagnostics = build_price_return_diagnostics(out)

    safe_write_table(out, parquet_path=config.output_table_path, csv_path=config.output_csv_path)
    config.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(config.diagnostics_path, index=False)

    logger.info("Wrote %d normalized price rows to %s", len(out), config.output_table_path)
    return out


def build_price_return_diagnostics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame([{"diagnostic": "rows", "value": 0}])

    rows = [
        {"diagnostic": "rows", "value": len(df)},
        {"diagnostic": "distinct_tickers", "value": df["ticker"].nunique() if "ticker" in df else 0},
        {"diagnostic": "distinct_cik10", "value": df["cik10"].nunique() if "cik10" in df else 0},
        {"diagnostic": "min_date", "value": str(df["date"].min().date())},
        {"diagnostic": "max_date", "value": str(df["date"].max().date())},
        {"diagnostic": "sectors", "value": df["sector"].nunique() if "sector" in df else 0},
    ]
    return pd.DataFrame(rows)


def download_price_data_stub(*args, **kwargs) -> None:
    """Explicit placeholder for future public price-vendor integration.

    The research repo intentionally starts with file-based ingestion so target
    construction is reproducible and vendor-neutral. A later adapter can write
    the same schema expected by `normalize_price_table`:

    date,ticker,cik10,sector,adj_close
    """
    raise NotImplementedError(
        "Live price download is intentionally not implemented in v0. "
        "Provide a CSV with columns date,ticker or cik10,sector,adj_close."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize price data and compute daily returns.")
    parser.add_argument("--raw-price-path", required=True)
    parser.add_argument("--output-table", default="data/processed/source_tables/price_return_source.parquet")
    parser.add_argument("--output-csv", default="data/processed/source_tables/price_return_source.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/price_return_source_diagnostics.csv")
    args = parser.parse_args()

    config = PriceReturnIngestionConfig(
        raw_price_path=root() / args.raw_price_path,
        output_table_path=root() / args.output_table,
        output_csv_path=root() / args.output_csv,
        diagnostics_path=root() / args.diagnostics_path,
    )
    build_price_return_source(config)


if __name__ == "__main__":
    main()
