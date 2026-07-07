from pathlib import Path

import pandas as pd

from fvn_dfm.features.fundamental_composites import (
    FundamentalCompositeConfig,
    build_fundamental_composite_row,
    build_fundamental_composite_diagnostics,
    build_fundamental_composites_dataframe,
)


def stress_row():
    data = {
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
        "fundamental_quality_flag": "GREEN",
        "fundamental_coverage_count": 11,
        "fundamental_coverage_ratio": 1.0,
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
        "revenue_yoy_pct_change": -0.10,
        "net_income_yoy_pct_change": -0.30,
        "margin_yoy_delta": -0.05,
        "cfo_quality_yoy_delta": -0.20,
        "cash_conversion_yoy_delta": -0.08,
        "assets_yoy_pct_change": 0.20,
        "liability_intensity_yoy_delta": 0.05,
        "leverage_yoy_delta": 0.04,
        "cash_to_assets_yoy_delta": -0.03,
        "receivables_to_assets_yoy_delta": 0.02,
        "inventory_to_assets_yoy_delta": 0.01,
        "capex_intensity_yoy_delta": 0.02,
        "shares_yoy_pct_change": 0.05,
        "working_capital_proxy_yoy_delta": -0.04,
    }
    return pd.Series(data)


def improvement_row():
    row = stress_row().copy()
    for col in [
        "revenue_yoy_pct_change",
        "net_income_yoy_pct_change",
        "margin_yoy_delta",
        "cfo_quality_yoy_delta",
        "cash_conversion_yoy_delta",
        "cash_to_assets_yoy_delta",
        "working_capital_proxy_yoy_delta",
    ]:
        row[col] = abs(float(row[col]))
    for col in [
        "assets_yoy_pct_change",
        "liability_intensity_yoy_delta",
        "leverage_yoy_delta",
        "receivables_to_assets_yoy_delta",
        "inventory_to_assets_yoy_delta",
        "capex_intensity_yoy_delta",
        "shares_yoy_pct_change",
    ]:
        row[col] = -abs(float(row[col]))
    row["accession_number"] = "0000320193-24-000106"
    row["period"] = "20240930"
    return row


def test_build_fundamental_composite_row_stress():
    config = FundamentalCompositeConfig(
        fundamental_delta_features_path=Path("dummy.csv"),
        output_table_path=Path("dummy.parquet"),
        output_csv_path=Path("dummy.csv"),
        diagnostics_path=Path("diag.csv"),
    )
    out = build_fundamental_composite_row(stress_row(), config)
    assert out["stress_revenue_decline_pos"] == 0.1
    assert out["stress_margin_deterioration_pos"] == 0.05
    assert out["stress_leverage_increase_pos"] == 0.04
    assert out["improve_revenue_growth_pos"] == 0.0
    assert out["fund_stress_score"] > out["fund_improve_score"]
    assert out["fund_net_stress_score"] > 0
    assert out["fundamental_composite_quality_flag"] == "GREEN"


def test_build_fundamental_composite_row_improvement():
    config = FundamentalCompositeConfig(
        fundamental_delta_features_path=Path("dummy.csv"),
        output_table_path=Path("dummy.parquet"),
        output_csv_path=Path("dummy.csv"),
        diagnostics_path=Path("diag.csv"),
    )
    out = build_fundamental_composite_row(improvement_row(), config)
    assert out["improve_revenue_growth_pos"] == 0.1
    assert out["improve_margin_improvement_pos"] == 0.05
    assert out["improve_leverage_decline_pos"] == 0.04
    assert out["fund_improve_score"] > out["fund_stress_score"]
    assert out["fundamental_reality_score"] > 0
    assert out["fundamental_composite_quality_flag"] == "GREEN"


def test_missing_prior_link_is_red():
    row = stress_row()
    row["comparable_link_quality_flag"] = "RED"
    row["prior_accession_number"] = ""
    config = FundamentalCompositeConfig(
        fundamental_delta_features_path=Path("dummy.csv"),
        output_table_path=Path("dummy.parquet"),
        output_csv_path=Path("dummy.csv"),
        diagnostics_path=Path("diag.csv"),
    )
    out = build_fundamental_composite_row(row, config)
    assert out["fundamental_composite_quality_flag"] == "RED"
    assert "comparable_link_quality_red" in out["fundamental_composite_quality_notes"]


def test_build_fundamental_composites_dataframe(tmp_path: Path):
    source = pd.DataFrame([stress_row().to_dict(), improvement_row().to_dict()])
    source_path = tmp_path / "fundamental_delta_features_asof.csv"
    source.to_csv(source_path, index=False)

    config = FundamentalCompositeConfig(
        fundamental_delta_features_path=source_path,
        output_table_path=tmp_path / "fundamental_composite_features_asof.parquet",
        output_csv_path=tmp_path / "fundamental_composite_features_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )
    df = build_fundamental_composites_dataframe(config)
    assert len(df) == 2
    assert "fund_stress_score" in df.columns
    assert "fund_improve_score" in df.columns
    assert "fundamental_reality_score" in df.columns

    diag = build_fundamental_composite_diagnostics(df)
    assert "rows" in set(diag["diagnostic"])
    assert "mean_fund_stress_score" in set(diag["diagnostic"])
