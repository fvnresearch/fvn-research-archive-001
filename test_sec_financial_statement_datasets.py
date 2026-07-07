from pathlib import Path

import pandas as pd

from fvn_dfm.targets.return_targets import (
    ReturnTargetConfig,
    build_return_target_diagnostics,
    build_return_targets_dataframe,
)


def make_prices(days: int = 70) -> pd.DataFrame:
    dates = pd.bdate_range("2023-11-07", periods=days)
    rows = []
    for i, date in enumerate(dates):
        rows.append({"date": date.date().isoformat(), "ticker": "AAPL", "cik10": "0000320193", "sector": "Tech", "adj_close": 100 + i})
        rows.append({"date": date.date().isoformat(), "ticker": "MSFT", "cik10": "0000789019", "sector": "Tech", "adj_close": 200 + 2 * i})
        rows.append({"date": date.date().isoformat(), "ticker": "JPM", "cik10": "0000019617", "sector": "Financials", "adj_close": 50 + i})
    return pd.DataFrame(rows)


def make_panel() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "panel_row_id": "0000320193:0000320193-23-000106:aapl.htm",
                "cik": "320193",
                "cik10": "0000320193",
                "ticker": "AAPL",
                "sector": "Tech",
                "accession_number": "0000320193-23-000106",
                "primary_document": "aapl.htm",
                "accession_lineage_key": "0000320193:0000320193-23-000106:aapl.htm",
                "feature_asof_date": "2023-11-07",
                "dfm_score_simple": -0.1,
                "panel_eligible": True,
                "panel_quality_flag": "GREEN",
            }
        ]
    )


def test_build_return_targets_dataframe(tmp_path: Path):
    panel_path = tmp_path / "model_research_panel.csv"
    price_path = tmp_path / "price_return_source.csv"
    make_panel().to_csv(panel_path, index=False)
    make_prices().to_csv(price_path, index=False)

    config = ReturnTargetConfig(
        model_research_panel_path=panel_path,
        price_return_source_path=price_path,
        output_table_path=tmp_path / "return_targets_asof.parquet",
        output_csv_path=tmp_path / "return_targets_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )
    out = build_return_targets_dataframe(config)
    assert len(out) == 1
    row = out.iloc[0]
    assert row["target_entry_date"] == "2023-11-07"
    assert row["target_exit_date"] == pd.bdate_range("2023-11-07", periods=70)[63].date().isoformat()

    aapl_return = ((100 + 63) / 100) - 1
    msft_return = ((200 + 2 * 63) / 200) - 1
    sector_return = (aapl_return + msft_return) / 2
    assert row["forward_63d_raw_return"] == round(aapl_return, 12)
    assert row["forward_63d_sector_return"] == round(sector_return, 12)
    assert row["forward_63d_sector_adjusted_return"] == round(aapl_return - sector_return, 12)
    assert row["target_quality_flag"] == "GREEN"
    assert row["target_available"] is True or row["target_available"] == True


def test_missing_window_is_red(tmp_path: Path):
    panel_path = tmp_path / "model_research_panel.csv"
    price_path = tmp_path / "price_return_source.csv"
    make_panel().to_csv(panel_path, index=False)
    make_prices(days=10).to_csv(price_path, index=False)

    config = ReturnTargetConfig(
        model_research_panel_path=panel_path,
        price_return_source_path=price_path,
        output_table_path=tmp_path / "return_targets_asof.parquet",
        output_csv_path=tmp_path / "return_targets_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )
    out = build_return_targets_dataframe(config)
    assert out.iloc[0]["target_quality_flag"] == "RED"
    assert "missing_forward_return_window" in out.iloc[0]["target_quality_notes"]


def test_return_target_diagnostics(tmp_path: Path):
    panel_path = tmp_path / "model_research_panel.csv"
    price_path = tmp_path / "price_return_source.csv"
    make_panel().to_csv(panel_path, index=False)
    make_prices().to_csv(price_path, index=False)

    config = ReturnTargetConfig(
        model_research_panel_path=panel_path,
        price_return_source_path=price_path,
        output_table_path=tmp_path / "return_targets_asof.parquet",
        output_csv_path=tmp_path / "return_targets_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )
    out = build_return_targets_dataframe(config)
    diag = build_return_target_diagnostics(out)
    assert "rows" in set(diag["diagnostic"])
    assert "target_available_rows" in set(diag["diagnostic"])
