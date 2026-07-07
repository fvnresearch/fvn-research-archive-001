from pathlib import Path

import pandas as pd

from fvn_dfm.data_ingestion.price_returns import PriceReturnIngestionConfig, build_price_return_source
from fvn_dfm.targets.return_targets import ReturnTargetConfig, build_return_targets


def test_price_source_and_return_targets_outputs(tmp_path: Path):
    dates = pd.bdate_range("2023-11-07", periods=70)
    rows = []
    for i, date in enumerate(dates):
        rows.append({"date": date.date().isoformat(), "ticker": "AAPL", "cik10": "0000320193", "sector": "Tech", "adj_close": 100 + i})
        rows.append({"date": date.date().isoformat(), "ticker": "MSFT", "cik10": "0000789019", "sector": "Tech", "adj_close": 200 + i})
    raw_prices = pd.DataFrame(rows)
    raw_path = tmp_path / "adjusted_prices.csv"
    raw_prices.to_csv(raw_path, index=False)

    price_config = PriceReturnIngestionConfig(
        raw_price_path=raw_path,
        output_table_path=tmp_path / "price_return_source.parquet",
        output_csv_path=tmp_path / "price_return_source.csv",
        diagnostics_path=tmp_path / "price_return_source_diagnostics.csv",
    )
    price_source = build_price_return_source(price_config)
    assert len(price_source) == 140
    assert (tmp_path / "price_return_source.csv").exists()

    panel = pd.DataFrame(
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
    panel_path = tmp_path / "model_research_panel.csv"
    panel.to_csv(panel_path, index=False)

    target_config = ReturnTargetConfig(
        model_research_panel_path=panel_path,
        price_return_source_path=tmp_path / "price_return_source.csv",
        output_table_path=tmp_path / "return_targets_asof.parquet",
        output_csv_path=tmp_path / "return_targets_asof.csv",
        diagnostics_path=tmp_path / "return_targets_asof_diagnostics.csv",
    )
    targets = build_return_targets(target_config)

    assert len(targets) == 1
    assert (tmp_path / "return_targets_asof.csv").exists()
    assert (tmp_path / "return_targets_asof_diagnostics.csv").exists()
    assert targets.iloc[0]["target_quality_flag"] == "GREEN"
    assert targets.iloc[0]["target_available"] is True or targets.iloc[0]["target_available"] == True
