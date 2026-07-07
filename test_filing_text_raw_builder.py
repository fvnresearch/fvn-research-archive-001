from pathlib import Path

import pandas as pd

from fvn_dfm.features.comparable_deltas import ComparableDeltasConfig, build_comparable_period_deltas


def test_build_comparable_period_deltas_outputs(tmp_path: Path):
    rows = []
    for year, fp, accession, revenue, assets in [
        (2022, "Q2", "0000320193-22-000050", 500.0, 2000.0),
        (2023, "Q2", "0000320193-23-000050", 650.0, 2500.0),
    ]:
        rows.append(
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": accession,
                "accession_lineage_key": f"0000320193:{accession}",
                "form": "10-Q",
                "period": f"{year}0630",
                "fy": str(year),
                "fp": fp,
                "feature_asof_date": f"{year}-08-08",
                "accepted_at_edgar": f"{year}-08-04T18:00:00-04:00",
                "timestamp_quality_flag": "GREEN",
                "fundamental_quality_flag": "YELLOW",
                "fundamental_coverage_count": 6,
                "fundamental_coverage_ratio": 6 / 11,
                "revenue": revenue,
                "net_income": 50.0,
                "cfo": 60.0,
                "assets": assets,
                "liabilities": 1000.0,
                "debt": 300.0,
                "cash": 200.0,
                "receivables": 100.0,
                "inventory": 50.0,
                "capex": 20.0,
                "shares": 10.0,
                "net_margin": 50.0 / revenue,
                "cfo_to_net_income": 1.2,
                "cfo_to_revenue": 60.0 / revenue,
                "liabilities_to_assets": 1000.0 / assets,
                "debt_to_assets": 300.0 / assets,
                "cash_to_assets": 200.0 / assets,
                "receivables_to_assets": 100.0 / assets,
                "inventory_to_assets": 50.0 / assets,
                "capex_to_revenue": 20.0 / revenue,
                "asset_turnover": revenue / assets,
                "cash_minus_debt_to_assets": (200.0 - 300.0) / assets,
                "working_capital_proxy_to_assets": (200.0 + 100.0 + 50.0 - 1000.0) / assets,
            }
        )

    source = pd.DataFrame(rows)
    source_path = tmp_path / "fundamental_features_asof.csv"
    source.to_csv(source_path, index=False)

    config = ComparableDeltasConfig(
        fundamental_features_asof_path=source_path,
        output_table_path=tmp_path / "fundamental_delta_features_asof.parquet",
        output_csv_path=tmp_path / "fundamental_delta_features_asof.csv",
        diagnostics_path=tmp_path / "fundamental_delta_features_asof_diagnostics.csv",
    )
    out = build_comparable_period_deltas(config)

    assert len(out) == 2
    assert (tmp_path / "fundamental_delta_features_asof.csv").exists()
    assert (tmp_path / "fundamental_delta_features_asof_diagnostics.csv").exists()
    linked = out[out["prior_accession_number"] == "0000320193-22-000050"].iloc[0]
    assert linked["comparable_period_key"] == "Q2"
    assert linked["revenue_yoy_abs_change"] == 150.0
    assert round(linked["revenue_yoy_pct_change"], 6) == 0.3
    assert linked["prior_period"] == "20220630"
