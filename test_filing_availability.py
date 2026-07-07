from pathlib import Path

import pandas as pd

from fvn_dfm.features.comparable_deltas import (
    ComparableDeltasConfig,
    build_comparable_delta_diagnostics,
    build_comparable_period_deltas_dataframe,
    comparable_period_key,
    normalize_fp,
)


def make_fundamental_features() -> pd.DataFrame:
    rows = []
    for year, revenue, net_income, cfo, assets, liabilities, debt, capex, shares in [
        (2022, 1000.0, 100.0, 120.0, 2000.0, 800.0, 300.0, 50.0, 10.0),
        (2023, 1200.0, 150.0, 180.0, 2400.0, 900.0, 360.0, 60.0, 11.0),
    ]:
        rows.append(
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": f"0000320193-{str(year)[2:]}-000001",
                "accession_lineage_key": f"0000320193:0000320193-{str(year)[2:]}-000001",
                "form": "10-K",
                "period": f"{year}0930",
                "fy": str(year),
                "fp": "FY",
                "feature_asof_date": f"{year}-11-07",
                "accepted_at_edgar": f"{year}-11-03T18:10:43-04:00",
                "timestamp_quality_flag": "GREEN",
                "fundamental_quality_flag": "GREEN",
                "fundamental_coverage_count": 11,
                "fundamental_coverage_ratio": 1.0,
                "revenue": revenue,
                "net_income": net_income,
                "cfo": cfo,
                "assets": assets,
                "liabilities": liabilities,
                "debt": debt,
                "cash": 250.0,
                "receivables": 100.0,
                "inventory": 80.0,
                "capex": capex,
                "shares": shares,
                "net_margin": net_income / revenue,
                "cfo_to_net_income": cfo / net_income,
                "cfo_to_revenue": cfo / revenue,
                "liabilities_to_assets": liabilities / assets,
                "debt_to_assets": debt / assets,
                "cash_to_assets": 250.0 / assets,
                "receivables_to_assets": 100.0 / assets,
                "inventory_to_assets": 80.0 / assets,
                "capex_to_revenue": capex / revenue,
                "asset_turnover": revenue / assets,
                "cash_minus_debt_to_assets": (250.0 - debt) / assets,
                "working_capital_proxy_to_assets": (250.0 + 100.0 + 80.0 - liabilities) / assets,
            }
        )
    return pd.DataFrame(rows)


def test_normalize_fp_and_key():
    assert normalize_fp("fy", "10-K") == "FY"
    assert normalize_fp("", "10-K") == "FY"
    assert comparable_period_key({"fp": "Q2", "form": "10-Q"}) == "Q2"


def test_build_comparable_period_deltas_dataframe(tmp_path: Path):
    df = make_fundamental_features()
    source_path = tmp_path / "fundamental_features_asof.csv"
    df.to_csv(source_path, index=False)

    config = ComparableDeltasConfig(
        fundamental_features_asof_path=source_path,
        output_table_path=tmp_path / "fundamental_delta_features_asof.parquet",
        output_csv_path=tmp_path / "fundamental_delta_features_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )
    out = build_comparable_period_deltas_dataframe(config)
    assert len(out) == 2

    first = out[out["period"] == "20220930"].iloc[0]
    assert first["comparable_link_quality_flag"] == "RED"
    assert "missing_prior_comparable_filing" in first["comparable_link_quality_notes"]

    second = out[out["period"] == "20230930"].iloc[0]
    assert second["prior_accession_number"] == "0000320193-22-000001"
    assert second["period_gap_years"] == 1
    assert second["comparable_link_quality_flag"] == "GREEN"
    assert second["revenue_yoy_abs_change"] == 200.0
    assert round(second["revenue_yoy_pct_change"], 6) == 0.2
    assert second["net_margin_yoy_delta"] == 0.025
    assert second["cfo_quality_yoy_delta"] == 0.0
    assert second["shares_yoy_abs_change"] == 1.0


def test_build_comparable_delta_diagnostics(tmp_path: Path):
    df = make_fundamental_features()
    source_path = tmp_path / "fundamental_features_asof.csv"
    df.to_csv(source_path, index=False)
    config = ComparableDeltasConfig(
        fundamental_features_asof_path=source_path,
        output_table_path=tmp_path / "fundamental_delta_features_asof.parquet",
        output_csv_path=tmp_path / "fundamental_delta_features_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )
    out = build_comparable_period_deltas_dataframe(config)
    diag = build_comparable_delta_diagnostics(out)
    assert "rows" in set(diag["diagnostic"])
    assert "linked_rows" in set(diag["diagnostic"])
    assert int(diag[diag["diagnostic"] == "linked_rows"].iloc[0]["value"]) == 1
