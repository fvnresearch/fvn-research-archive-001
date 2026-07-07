from pathlib import Path

import pandas as pd
import pytest

from fvn_dfm.data_ingestion.price_returns import (
    compute_daily_returns,
    download_price_data_stub,
    normalize_price_table,
)


def test_normalize_price_table():
    raw = pd.DataFrame(
        [
            {"date": "2023-01-03", "ticker": " aapl ", "cik10": "320193", "sector": "Tech", "adj_close": "100"},
            {"date": "2023-01-04", "ticker": "AAPL", "cik10": "0000320193", "sector": "Tech", "adj_close": "110"},
        ]
    )
    out = normalize_price_table(raw)
    assert len(out) == 2
    assert out.iloc[0]["ticker"] == "AAPL"
    assert out.iloc[0]["cik10"] == "0000320193"
    assert out.iloc[0]["adj_close"] == 100.0
    assert "price_return_source_version" in out.columns


def test_compute_daily_returns():
    raw = pd.DataFrame(
        [
            {"date": "2023-01-03", "ticker": "AAPL", "sector": "Tech", "adj_close": "100"},
            {"date": "2023-01-04", "ticker": "AAPL", "sector": "Tech", "adj_close": "110"},
            {"date": "2023-01-05", "ticker": "AAPL", "sector": "Tech", "adj_close": "121"},
        ]
    )
    out = compute_daily_returns(raw)
    assert out.iloc[0]["daily_return"] != out.iloc[0]["daily_return"]  # NaN
    assert round(out.iloc[1]["daily_return"], 6) == 0.1
    assert round(out.iloc[2]["daily_return"], 6) == 0.1
    assert list(out["trading_day_index"]) == [0, 1, 2]


def test_download_price_data_stub_raises():
    with pytest.raises(NotImplementedError):
        download_price_data_stub()
