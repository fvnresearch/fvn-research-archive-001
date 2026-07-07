from pathlib import Path

import pandas as pd

from fvn_dfm.text.section_extractor import SectionExtractionConfig, build_filing_section_text_dataframe


def test_section_extraction_dataframe_from_filing_text_raw_csv(tmp_path: Path):
    text = (
        "Item 1A. Risk Factors " + ("risk disclosure " * 100) +
        "Item 1B. Unresolved Staff Comments None. "
        "Item 7. Management's Discussion and Analysis Results of Operations " + ("operating result " * 80) +
        "Liquidity and Capital Resources " + ("cash credit liquidity " * 80) +
        "Critical Accounting Estimates estimates. "
        "Item 7A. Quantitative and Qualitative Disclosures market risk."
    )
    source = pd.DataFrame(
        [
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "primary_document": "aapl.htm",
                "clean_text": text,
                "clean_word_count": 600,
                "accession_lineage_key": "0000320193:0000320193-23-000106:aapl.htm",
                "text_version": "FILING_TEXT_RAW_V0",
            }
        ]
    )
    source_path = tmp_path / "filing_text_raw.csv"
    source.to_csv(source_path, index=False)

    config = SectionExtractionConfig(
        filing_text_raw_path=source_path,
        output_table_path=tmp_path / "filing_section_text.parquet",
        output_csv_path=tmp_path / "filing_section_text.csv",
        min_mda_word_count=20,
        min_risk_word_count=20,
        min_liquidity_word_count=20,
    )
    df = build_filing_section_text_dataframe(config)
    assert len(df) == 3
    assert all(df["section_word_count"] > 0)
    assert df[df["section_name"] == "mda"].iloc[0]["section_quality_flag"] == "GREEN"
    assert df[df["section_name"] == "risk_factors"].iloc[0]["section_quality_flag"] == "GREEN"
    assert df[df["section_name"] == "liquidity"].iloc[0]["section_quality_flag"] == "GREEN"
