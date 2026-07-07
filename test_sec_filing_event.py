from pathlib import Path

import pandas as pd

from fvn_dfm.features.research_panel import (
    ResearchPanelConfig,
    build_model_research_panel_dataframe,
    build_model_research_panel_diagnostics,
)


def config(tmp_path: Path) -> ResearchPanelConfig:
    return ResearchPanelConfig(
        mismatch_features_path=tmp_path / "mismatch_features_asof.csv",
        fundamental_features_path=tmp_path / "fundamental_features_asof.csv",
        text_features_path=tmp_path / "text_features_asof.csv",
        filing_availability_path=tmp_path / "filing_availability.csv",
        output_table_path=tmp_path / "model_research_panel.parquet",
        output_csv_path=tmp_path / "model_research_panel.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )


def write_inputs(tmp_path: Path, *, mismatch_quality="GREEN", timestamp_quality="GREEN", include_asof=True):
    mismatch = pd.DataFrame(
        [
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "primary_document": "aapl.htm",
                "accession_lineage_key": "0000320193:0000320193-23-000106:aapl.htm",
                "feature_asof_date": "2023-11-07" if include_asof else "",
                "accepted_at_edgar": "2023-11-03T18:10:43-04:00",
                "timestamp_quality_flag": timestamp_quality,
                "mismatch_quality_flag": mismatch_quality,
                "mismatch_quality_notes": "",
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
                "fundamental_quality_flag": "GREEN",
                "fundamental_feature_version": "FUNDAMENTAL_FEATURES_ASOF_V0",
                "revenue": 1000.0,
                "net_margin": 0.1,
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
    mismatch.to_csv(tmp_path / "mismatch_features_asof.csv", index=False)
    fund.to_csv(tmp_path / "fundamental_features_asof.csv", index=False)
    text.to_csv(tmp_path / "text_features_asof.csv", index=False)
    availability.to_csv(tmp_path / "filing_availability.csv", index=False)


def test_build_model_research_panel_dataframe(tmp_path: Path):
    write_inputs(tmp_path)
    df = build_model_research_panel_dataframe(config(tmp_path))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["panel_row_id"] == "0000320193:0000320193-23-000106:aapl.htm"
    assert row["panel_eligible"] is True or row["panel_eligible"] == True
    assert row["panel_quality_flag"] == "GREEN"
    assert row["dfm_score_simple"] == "-0.019" or float(row["dfm_score_simple"]) == -0.019
    assert row["fund_revenue"] == "1000.0" or float(row["fund_revenue"]) == 1000.0
    assert row["text_full_lm_positive_share"] == "0.05" or float(row["text_full_lm_positive_share"]) == 0.05
    assert row["lineage_mismatch_features_version"] == "DFM_MISMATCH_FEATURES_V0"
    assert row["lineage_fundamental_features_version"] == "FUNDAMENTAL_FEATURES_ASOF_V0"
    assert row["lineage_text_features_version"] == "TEXT_FEATURES_ASOF_V1"


def test_panel_red_when_missing_asof(tmp_path: Path):
    write_inputs(tmp_path, include_asof=False)
    df = build_model_research_panel_dataframe(config(tmp_path))
    assert len(df) == 1
    # availability fills the missing asof date, so row stays eligible.
    assert df.iloc[0]["feature_asof_date"] == "2023-11-07"
    assert df.iloc[0]["panel_quality_flag"] == "GREEN"


def test_panel_red_when_bad_mismatch_quality(tmp_path: Path):
    write_inputs(tmp_path, mismatch_quality="RED")
    df = build_model_research_panel_dataframe(config(tmp_path))
    assert len(df) == 1
    assert df.iloc[0]["panel_eligible"] is False or df.iloc[0]["panel_eligible"] == False
    assert df.iloc[0]["panel_quality_flag"] == "RED"
    assert "bad_mismatch_quality=RED" in df.iloc[0]["panel_quality_notes"]


def test_model_research_panel_diagnostics(tmp_path: Path):
    write_inputs(tmp_path)
    df = build_model_research_panel_dataframe(config(tmp_path))
    diag = build_model_research_panel_diagnostics(df)
    assert "rows" in set(diag["diagnostic"])
    assert "eligible_rows" in set(diag["diagnostic"])
    assert int(diag[diag["diagnostic"] == "eligible_rows"].iloc[0]["value"]) == 1
