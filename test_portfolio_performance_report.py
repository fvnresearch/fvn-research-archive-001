from pathlib import Path

import pandas as pd

from fvn_dfm.features.mismatch_features import (
    MismatchFeaturesConfig,
    build_mismatch_features_dataframe,
    build_mismatch_diagnostics,
    build_mismatch_row,
    join_feature_layers,
)


def sample_fundamental_row():
    return pd.Series(
        {
            "cik": "320193",
            "cik10": "0000320193",
            "accession_number": "0000320193-23-000106",
            "accession_lineage_key": "0000320193:0000320193-23-000106",
            "feature_asof_date": "2023-11-07",
            "accepted_at_edgar": "2023-11-03T18:10:43-04:00",
            "timestamp_quality_flag": "GREEN",
            "fundamental_composite_quality_flag": "GREEN",
            "fund_stress_score": 0.20,
            "fund_improve_score": 0.03,
            "fund_net_stress_score": 0.17,
            "fund_net_improvement_score": -0.17,
            "fundamental_reality_score": -0.17,
            "stress_margin_deterioration_pos": 0.05,
            "stress_cfo_quality_deterioration_pos": 0.04,
            "stress_cash_conversion_deterioration_pos": 0.03,
            "stress_leverage_increase_pos": 0.02,
            "stress_liability_intensity_increase_pos": 0.02,
            "stress_receivables_intensity_increase_pos": 0.01,
            "stress_inventory_intensity_increase_pos": 0.01,
            "stress_share_dilution_pos": 0.02,
            "improve_margin_improvement_pos": 0.0,
            "improve_cfo_quality_improvement_pos": 0.0,
            "improve_cash_conversion_improvement_pos": 0.0,
            "improve_leverage_decline_pos": 0.0,
            "improve_cash_buffer_improvement_pos": 0.0,
            "improve_working_capital_proxy_improvement_pos": 0.0,
        }
    )


def sample_text_row():
    return pd.Series(
        {
            "cik": "320193",
            "cik10": "0000320193",
            "accession_number": "0000320193-23-000106",
            "primary_document": "aapl.htm",
            "accession_lineage_key": "0000320193:0000320193-23-000106:aapl.htm",
            "feature_asof_date": "2023-11-07",
            "accepted_at_edgar": "2023-11-03T18:10:43-04:00",
            "timestamp_quality_flag": "GREEN",
            "full_parse_quality_flag": "GREEN",
            "mda_section_quality_flag": "GREEN",
            "risk_section_quality_flag": "GREEN",
            "liquidity_section_quality_flag": "GREEN",
            "full_lm_positive_share": 0.05,
            "full_lm_negative_share": 0.01,
            "full_lm_uncertainty_share": 0.02,
            "full_lm_litigious_share": 0.005,
            "full_lm_constraining_share": 0.004,
            "full_lm_modal_total_share": 0.01,
            "full_lm_pos_neg_balance": 0.6666666667,
            "mda_lm_positive_share": 0.04,
            "mda_lm_negative_share": 0.01,
            "mda_lm_uncertainty_share": 0.02,
            "mda_lm_pos_neg_balance": 0.60,
            "risk_lm_negative_share": 0.005,
            "risk_lm_litigious_share": 0.01,
            "risk_lm_constraining_share": 0.02,
            "liquidity_lm_negative_share": 0.01,
        }
    )


def config(tmp_path: Path):
    return MismatchFeaturesConfig(
        fundamental_composite_features_path=tmp_path / "fundamental_composite_features_asof.csv",
        text_features_path=tmp_path / "text_features_asof.csv",
        output_table_path=tmp_path / "mismatch_features_asof.parquet",
        output_csv_path=tmp_path / "mismatch_features_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )


def test_join_feature_layers():
    fund = pd.DataFrame([sample_fundamental_row().to_dict()])
    text = pd.DataFrame([sample_text_row().to_dict()])
    joined = join_feature_layers(fund, text)
    assert len(joined) == 1
    assert joined.iloc[0]["primary_document"] == "aapl.htm"


def test_build_mismatch_row_downside(tmp_path: Path):
    row = join_feature_layers(
        pd.DataFrame([sample_fundamental_row().to_dict()]),
        pd.DataFrame([sample_text_row().to_dict()]),
    ).iloc[0]
    out = build_mismatch_row(row, config(tmp_path))
    assert out["downside_stress_x_full_positive_tone"] == 0.01
    assert out["downside_stress_x_full_net_positive_tone"] > 0.1
    assert out["upside_improvement_x_full_negative_tone"] == 0.0003
    assert out["downside_mismatch_score"] > out["upside_mismatch_score"]
    assert out["net_mismatch_score"] < 0
    assert out["dfm_score_simple"] == out["net_mismatch_score"]
    assert out["mismatch_quality_flag"] == "GREEN"


def test_quality_flag_yellow_for_section_quality(tmp_path: Path):
    fund = sample_fundamental_row()
    text = sample_text_row()
    text["risk_section_quality_flag"] = "YELLOW"
    row = join_feature_layers(pd.DataFrame([fund.to_dict()]), pd.DataFrame([text.to_dict()])).iloc[0]
    out = build_mismatch_row(row, config(tmp_path))
    assert out["mismatch_quality_flag"] == "YELLOW"
    assert "risk_section_quality_yellow" in out["mismatch_quality_notes"]


def test_build_mismatch_features_dataframe_and_diagnostics(tmp_path: Path):
    fund = pd.DataFrame([sample_fundamental_row().to_dict()])
    text = pd.DataFrame([sample_text_row().to_dict()])
    fund_path = tmp_path / "fundamental_composite_features_asof.csv"
    text_path = tmp_path / "text_features_asof.csv"
    fund.to_csv(fund_path, index=False)
    text.to_csv(text_path, index=False)
    cfg = config(tmp_path)

    df = build_mismatch_features_dataframe(cfg)
    assert len(df) == 1
    assert "downside_mismatch_score" in df.columns
    assert "upside_mismatch_score" in df.columns
    assert "net_mismatch_score" in df.columns

    diagnostics = build_mismatch_diagnostics(df)
    assert "rows" in set(diagnostics["diagnostic"])
    assert "mean_net_mismatch_score" in set(diagnostics["diagnostic"])
