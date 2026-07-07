from pathlib import Path

import pandas as pd

from fvn_dfm.features.research_panel import ResearchPanelConfig, build_model_research_panel


def test_build_model_research_panel_outputs(tmp_path: Path):
    mismatch = pd.DataFrame(
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
                "mismatch_quality_flag": "YELLOW",
                "mismatch_quality_notes": "risk_section_quality_yellow",
                "downside_mismatch_score": 0.02,
                "upside_mismatch_score": 0.001,
                "net_mismatch_score": -0.019,
                "dfm_score_simple": -0.019,
                "mismatch_feature_version": "DFM_MISMATCH_FEATURES_V0",
            }
        ]
    )
    fund = pd.DataFrame(
        [
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "accession_lineage_key": "0000320193:0000320193-23-000106",
                "feature_asof_date": "2023-11-07",
                "fundamental_quality_flag": "YELLOW",
                "fundamental_feature_version": "FUNDAMENTAL_FEATURES_ASOF_V0",
                "revenue": 1000.0,
                "net_margin": 0.1,
                "fundamental_coverage_ratio": 0.8,
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
                "text_feature_version": "TEXT_FEATURES_ASOF_V1",
                "full_parse_quality_flag": "GREEN",
                "full_lm_positive_share": 0.05,
                "risk_lm_negative_share": 0.02,
            }
        ]
    )
    availability = pd.DataFrame(
        [
            {
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "accession_lineage_key": "0000320193:0000320193-23-000106",
                "accepted_at_edgar": "2023-11-03T18:10:43-04:00",
                "first_allowed_execution_date": "2023-11-07",
                "timestamp_quality_flag": "GREEN",
                "header_source_file": "complete.txt",
            }
        ]
    )

    mismatch_path = tmp_path / "mismatch_features_asof.csv"
    fund_path = tmp_path / "fundamental_features_asof.csv"
    text_path = tmp_path / "text_features_asof.csv"
    availability_path = tmp_path / "filing_availability.csv"

    mismatch.to_csv(mismatch_path, index=False)
    fund.to_csv(fund_path, index=False)
    text.to_csv(text_path, index=False)
    availability.to_csv(availability_path, index=False)

    config = ResearchPanelConfig(
        mismatch_features_path=mismatch_path,
        fundamental_features_path=fund_path,
        text_features_path=text_path,
        filing_availability_path=availability_path,
        output_table_path=tmp_path / "model_research_panel.parquet",
        output_csv_path=tmp_path / "model_research_panel.csv",
        diagnostics_path=tmp_path / "model_research_panel_diagnostics.csv",
    )
    df = build_model_research_panel(config)

    assert len(df) == 1
    assert (tmp_path / "model_research_panel.csv").exists()
    assert (tmp_path / "model_research_panel_diagnostics.csv").exists()
    assert df.iloc[0]["panel_eligible"] is True or df.iloc[0]["panel_eligible"] == True
    assert df.iloc[0]["panel_quality_flag"] == "GREEN"
    assert "fund_revenue" in df.columns
    assert "text_full_lm_positive_share" in df.columns
    assert "dfm_score_simple" in df.columns
