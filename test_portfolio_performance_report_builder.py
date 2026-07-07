from pathlib import Path

import pandas as pd

from fvn_dfm.features.mismatch_features import MismatchFeaturesConfig, build_mismatch_features_asof


def test_build_mismatch_features_asof_outputs(tmp_path: Path):
    fund = pd.DataFrame(
        [
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "accession_lineage_key": "0000320193:0000320193-23-000106",
                "feature_asof_date": "2023-11-07",
                "accepted_at_edgar": "2023-11-03T18:10:43-04:00",
                "timestamp_quality_flag": "GREEN",
                "fundamental_composite_quality_flag": "GREEN",
                "fund_stress_score": 0.25,
                "fund_improve_score": 0.02,
                "fund_net_stress_score": 0.23,
                "fund_net_improvement_score": -0.23,
                "fundamental_reality_score": -0.23,
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
        ]
    )
    text = pd.DataFrame(
        [
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
                "full_lm_pos_neg_balance": 0.5,
                "mda_lm_positive_share": 0.04,
                "mda_lm_negative_share": 0.01,
                "mda_lm_uncertainty_share": 0.02,
                "mda_lm_pos_neg_balance": 0.4,
                "risk_lm_negative_share": 0.005,
                "risk_lm_litigious_share": 0.01,
                "risk_lm_constraining_share": 0.02,
                "liquidity_lm_negative_share": 0.01,
            }
        ]
    )
    fund_path = tmp_path / "fundamental_composite_features_asof.csv"
    text_path = tmp_path / "text_features_asof.csv"
    fund.to_csv(fund_path, index=False)
    text.to_csv(text_path, index=False)

    config = MismatchFeaturesConfig(
        fundamental_composite_features_path=fund_path,
        text_features_path=text_path,
        output_table_path=tmp_path / "mismatch_features_asof.parquet",
        output_csv_path=tmp_path / "mismatch_features_asof.csv",
        diagnostics_path=tmp_path / "mismatch_features_asof_diagnostics.csv",
    )
    df = build_mismatch_features_asof(config)

    assert len(df) == 1
    assert (tmp_path / "mismatch_features_asof.csv").exists()
    assert (tmp_path / "mismatch_features_asof_diagnostics.csv").exists()
    assert df.iloc[0]["downside_mismatch_score"] > df.iloc[0]["upside_mismatch_score"]
    assert df.iloc[0]["net_mismatch_score"] < 0
    assert df.iloc[0]["mismatch_quality_flag"] == "GREEN"
