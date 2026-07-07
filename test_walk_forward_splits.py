from pathlib import Path

from fvn_dfm.data_ingestion.sec_primary_documents import (
    PrimaryDocumentCandidate,
    choose_primary_document_from_index,
    parse_complete_submission_document_index,
    primary_document_output_path,
    primary_document_url,
    read_primary_document_candidates_csv,
    write_primary_document_candidates_csv,
)


COMPLETE_SUBMISSION = """
<SEC-DOCUMENT>0000320193-23-000106.txt : 20231103
<SEC-HEADER>
<ACCEPTANCE-DATETIME>20231103181043
ACCESSION NUMBER: 0000320193-23-000106
CONFORMED SUBMISSION TYPE: 10-K
</SEC-HEADER>
<DOCUMENT>
<TYPE>10-K
<SEQUENCE>1
<FILENAME>aapl-20230930.htm
<DESCRIPTION>10-K
<TEXT>
<html>primary</html>
</TEXT>
</DOCUMENT>
<DOCUMENT>
<TYPE>EX-21.1
<SEQUENCE>2
<FILENAME>aapl-ex211.htm
<DESCRIPTION>Subsidiaries
<TEXT>exhibit</TEXT>
</DOCUMENT>
"""


def test_parse_complete_submission_document_index():
    docs = parse_complete_submission_document_index(COMPLETE_SUBMISSION)
    assert len(docs) == 2
    assert docs[0]["type"] == "10-K"
    assert docs[0]["filename"] == "aapl-20230930.htm"
    assert docs[1]["type"] == "EX-21.1"


def test_choose_primary_document_with_hint_confirmed():
    docs = parse_complete_submission_document_index(COMPLETE_SUBMISSION)
    filename, method, warning = choose_primary_document_from_index(
        docs,
        form_type="10-K",
        primary_document_hint="aapl-20230930.htm",
    )
    assert filename == "aapl-20230930.htm"
    assert method == "primary_document_hint_confirmed_in_complete_submission"
    assert warning == ""


def test_choose_primary_document_by_form_type():
    docs = parse_complete_submission_document_index(COMPLETE_SUBMISSION)
    filename, method, warning = choose_primary_document_from_index(docs, form_type="10-K")
    assert filename == "aapl-20230930.htm"
    assert method == "document_type_matches_form"
    assert warning == ""


def test_primary_document_url():
    url = primary_document_url(
        cik="0000320193",
        accession_number="0000320193-23-000106",
        primary_document="aapl-20230930.htm",
        archives_base="https://www.sec.gov/Archives",
    )
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/"
        "320193/000032019323000106/aapl-20230930.htm"
    )


def test_primary_document_output_path(tmp_path: Path):
    path = primary_document_output_path(
        output_dir=tmp_path,
        cik="320193",
        accession_number="0000320193-23-000106",
        primary_document="aapl-20230930.htm",
    )
    assert str(path).endswith("0000320193/0000320193-23-000106/aapl-20230930.htm")


def test_candidate_csv_roundtrip(tmp_path: Path):
    candidate = PrimaryDocumentCandidate(
        cik="320193",
        cik10="0000320193",
        accession_number="0000320193-23-000106",
        accession_no_dashes="000032019323000106",
        form_type="10-K",
        primary_document="aapl-20230930.htm",
        discovery_method="unit_test",
    )
    out = tmp_path / "primary_document_candidates.csv"
    write_primary_document_candidates_csv([candidate], out)
    loaded = read_primary_document_candidates_csv(out)
    assert len(loaded) == 1
    assert loaded[0].primary_document == "aapl-20230930.htm"
    assert loaded[0].lineage_key == "0000320193:0000320193-23-000106:aapl-20230930.htm"
