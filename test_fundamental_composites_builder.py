from pathlib import Path

from fvn_dfm.text.filing_text_raw import FilingTextRawConfig, build_filing_text_raw_dataframe


def test_build_filing_text_raw_dataframe(tmp_path: Path):
    root = tmp_path / "primary_documents"
    doc = root / "0000320193" / "0000320193-23-000106" / "aapl-20230930.htm"
    doc.parent.mkdir(parents=True)
    words = "business risk liquidity management discussion " * 300
    doc.write_text(f"<html><body><p>{words}</p></body></html>", encoding="utf-8")

    config = FilingTextRawConfig(
        primary_documents_dir=root,
        output_table_path=tmp_path / "filing_text_raw.parquet",
        output_csv_path=tmp_path / "filing_text_raw.csv",
        min_clean_word_count=100,
    )

    df = build_filing_text_raw_dataframe(config)
    assert len(df) == 1
    assert df.iloc[0]["cik10"] == "0000320193"
    assert df.iloc[0]["parse_quality_flag"] == "GREEN"
    assert "business risk liquidity" in df.iloc[0]["clean_text"]
