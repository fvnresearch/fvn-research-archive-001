from pathlib import Path

import pandas as pd

from fvn_dfm.features.text_features import TextFeaturesConfig, build_text_features_asof_dataframe


def test_build_text_features_asof_dataframe(tmp_path: Path):
    lm_path = tmp_path / "lm.csv"
    lm_path.write_text("""Word,Negative,Positive,Uncertainty,Litigious,Constraining,Strong_Modal,Weak_Modal
LOSS,2009,0,0,0,0,0,0
GAIN,0,2009,0,0,0,0,0
MAY,0,0,1,0,0,0,1
LITIGATION,0,0,0,1,0,0,0
RESTRICTED,0,0,0,0,1,0,0
MUST,0,0,0,0,0,1,0
""", encoding="utf-8")

    raw = pd.DataFrame(
        [
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "primary_document": "aapl.htm",
                "clean_text": "gain gain loss may litigation restricted must",
                "clean_word_count": 7,
                "clean_char_count": 100,
                "parse_quality_flag": "GREEN",
                "parse_quality_notes": "",
                "accession_lineage_key": "0000320193:0000320193-23-000106:aapl.htm",
                "text_version": "FILING_TEXT_RAW_V0",
            }
        ]
    )
    raw_path = tmp_path / "filing_text_raw.csv"
    raw.to_csv(raw_path, index=False)

    sections = pd.DataFrame(
        [
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "primary_document": "aapl.htm",
                "section_name": "mda",
                "section_text": "gain may must",
                "section_word_count": 3,
                "section_quality_flag": "GREEN",
                "section_quality_notes": "",
                "accession_lineage_key": "0000320193:0000320193-23-000106:aapl.htm",
                "text_version": "FILING_TEXT_RAW_V0",
            },
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "primary_document": "aapl.htm",
                "section_name": "risk_factors",
                "section_text": "loss litigation restricted may",
                "section_word_count": 4,
                "section_quality_flag": "GREEN",
                "section_quality_notes": "",
                "accession_lineage_key": "0000320193:0000320193-23-000106:aapl.htm",
                "text_version": "FILING_TEXT_RAW_V0",
            },
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "primary_document": "aapl.htm",
                "section_name": "liquidity",
                "section_text": "restricted loss",
                "section_word_count": 2,
                "section_quality_flag": "YELLOW",
                "section_quality_notes": "low_section_word_count",
                "accession_lineage_key": "0000320193:0000320193-23-000106:aapl.htm",
                "text_version": "FILING_TEXT_RAW_V0",
            },
        ]
    )
    sections_path = tmp_path / "filing_section_text.csv"
    sections.to_csv(sections_path, index=False)

    availability = pd.DataFrame(
        [
            {
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "accession_lineage_key": "0000320193:0000320193-23-000106",
                "accepted_at_edgar": "2023-11-03T18:10:43-04:00",
                "first_allowed_execution_date": "2023-11-07",
                "timestamp_quality_flag": "GREEN",
            }
        ]
    )
    availability_path = tmp_path / "filing_availability.csv"
    availability.to_csv(availability_path, index=False)

    config = TextFeaturesConfig(
        filing_text_raw_path=raw_path,
        filing_section_text_path=sections_path,
        filing_availability_path=availability_path,
        lm_dictionary_path=lm_path,
        output_table_path=tmp_path / "text_features_asof.parquet",
        output_csv_path=tmp_path / "text_features_asof.csv",
    )
    df = build_text_features_asof_dataframe(config)

    assert len(df) == 1
    row = df.iloc[0]
    assert row["feature_asof_date"] == "2023-11-07"
    assert row["full_lm_positive_count"] == 2
    assert row["full_lm_negative_count"] == 1
    assert row["full_lm_uncertainty_count"] == 1
    assert row["mda_lm_positive_count"] == 1
    assert row["risk_lm_litigious_count"] == 1
    assert row["liquidity_lm_constraining_count"] == 1
    assert bool(row["mda_section_available"]) is True
