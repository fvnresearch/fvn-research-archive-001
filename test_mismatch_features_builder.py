from pathlib import Path

import pandas as pd

from fvn_dfm.features.fundamental_composites import FundamentalCompositeConfig, build_fundamental_stress_improvement


def test_build_fundamental_stress_improvement_outputs(tmp_path: Path):
    row = {
        "cik": "320193",
        "cik10": "0000320193",
        "accession_number": "0000320193-23-000106",
        "accession_lineage_key": "0000320193:0000320193-23-000106",
        "form": "10-K",
        "period": "20230930",
        "fy": "2023",
        "fp": "FY",
        "feature_asof_date": "2023-11-07",
        "accepted_at_edgar": "2023-11-03T18:10:43-04:00",
        "timestamp_quality_flag": "GREEN",
        "fundamental_quality_flag": "YELLOW",
        "fundamental_coverage_count": 10,
        "fundamental_coverage_ratio": 10 / 11,
        "comparable_period_key": "FY",
        "prior_accession_number": "0000320193-22-000106",
        "prior_accession_lineage_key": "0000320193:0000320193-22-000106",
        "prior_period": "20220930",
        "prior_fy": "2022",
        "prior_fp": "FY",
        "prior_feature_asof_date": "2022-11-07",
        "prior_fundamental_quality_flag": "GREEN",
        "period_gap_years": 1,
        "comparable_link_quality_flag": "GREEN",
        "comparable_link_quality_notes": "",
        "revenue_yoy_pct_change": -0.2,
        "net_income_yoy_pct_change": -0.1,
        "margin_yoy_delta": -0.02,
        "cfo_quality_yoy_delta": -0.05,
        "cash_conversion_yoy_delta": -0.04,
        "assets_yoy_pct_change": 0.1,
        "liability_intensity_yoy_delta": 0.03,
        "leverage_yoy_delta": 0.02,
        "cash_to_assets_yoy_delta": -0.01,
        "receivables_to_assets_yoy_delta": 0.02,
        "inventory_to_assets_yoy_delta": 0.01,
        "capex_intensity_yoy_delta": 0.02,
        "shares_yoy_pct_change": 0.03,
        "working_capital_proxy_yoy_delta": -0.03,
    }
    source = pd.DataFrame([row])
    source_path = tmp_path / "fundamental_delta_features_asof.csv"
    source.to_csv(source_path, index=False)

    config = FundamentalCompositeConfig(
        fundamental_delta_features_path=source_path,
        output_table_path=tmp_path / "fundamental_composite_features_asof.parquet",
        output_csv_path=tmp_path / "fundamental_composite_features_asof.csv",
        diagnostics_path=tmp_path / "fundamental_composite_features_asof_diagnostics.csv",
    )
    df = build_fundamental_stress_improvement(config)

    assert len(df) == 1
    assert (tmp_path / "fundamental_composite_features_asof.csv").exists()
    assert (tmp_path / "fundamental_composite_features_asof_diagnostics.csv").exists()
    assert df.iloc[0]["fund_stress_score"] > df.iloc[0]["fund_improve_score"]
    assert df.iloc[0]["fundamental_composite_quality_flag"] == "YELLOW"
    assert "current_fundamental_quality_yellow" in df.iloc[0]["fundamental_composite_quality_notes"]
