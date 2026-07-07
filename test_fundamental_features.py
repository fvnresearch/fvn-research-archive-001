from pathlib import Path

from fvn_dfm.text.filing_text_raw import (
    contains_html_tag,
    contains_xbrl_tag,
    extract_primary_document_text_row,
    infer_lineage_from_primary_document_path,
    parse_quality,
)


def test_infer_lineage_from_primary_document_path(tmp_path: Path):
    root = tmp_path / "primary_documents"
    path = root / "0000320193" / "0000320193-23-000106" / "aapl-20230930.htm"
    path.parent.mkdir(parents=True)
    path.write_text("<html></html>", encoding="utf-8")

    lineage = infer_lineage_from_primary_document_path(path, root)
    assert lineage["cik"] == "320193"
    assert lineage["cik10"] == "0000320193"
    assert lineage["accession_number"] == "0000320193-23-000106"
    assert lineage["primary_document"] == "aapl-20230930.htm"


def test_contains_tag_flags():
    assert contains_html_tag("<html><body>Text</body></html>")
    assert contains_xbrl_tag("<ix:nonFraction>1</ix:nonFraction>")


def test_parse_quality_green_for_sufficient_text():
    raw = "<html><body>" + ("word " * 2000) + "</body></html>"
    clean = "word " * 2000
    flag, notes = parse_quality(
        raw_text=raw,
        clean_text=clean,
        min_clean_word_count=1000,
        min_ratio_warning=0.01,
        max_ratio_warning=0.99,
    )
    assert flag == "GREEN"
    assert notes == ""


def test_parse_quality_yellow_for_short_text():
    raw = "<html><body>short text</body></html>"
    clean = "short text"
    flag, notes = parse_quality(
        raw_text=raw,
        clean_text=clean,
        min_clean_word_count=1000,
        min_ratio_warning=0.01,
        max_ratio_warning=0.99,
    )
    assert flag == "YELLOW"
    assert "low_clean_word_count" in notes


def test_extract_primary_document_text_row(tmp_path: Path):
    root = tmp_path / "primary_documents"
    path = root / "0000320193" / "0000320193-23-000106" / "aapl-20230930.htm"
    path.parent.mkdir(parents=True)
    words = "management discussion liquidity risk " * 300
    path.write_text(
        f"<html><body><p>{words}</p><script>bad()</script><table><tr><td>999</td></tr></table></body></html>",
        encoding="utf-8",
    )

    row = extract_primary_document_text_row(
        path,
        primary_documents_dir=root,
        min_clean_word_count=100,
    )
    assert row["cik10"] == "0000320193"
    assert row["accession_number"] == "0000320193-23-000106"
    assert row["primary_document"] == "aapl-20230930.htm"
    assert row["clean_word_count"] >= 100
    assert "bad" not in row["clean_text"]
    assert "999" not in row["clean_text"]
    assert row["parse_quality_flag"] == "GREEN"
    assert row["accession_lineage_key"] == "0000320193:0000320193-23-000106:aapl-20230930.htm"
