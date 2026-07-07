from datetime import datetime

from fvn_dfm.data_ingestion.sec_complete_submissions import (
    complete_submission_output_path,
    complete_submission_url,
    normalize_accession_no_dashes,
    normalize_accession_with_dashes,
    normalize_cik_10,
    normalize_cik_for_archive,
    parse_acceptance_datetime_from_text,
)


def test_normalize_cik_for_archive():
    assert normalize_cik_for_archive("0000320193") == "320193"
    assert normalize_cik_for_archive("320193") == "320193"


def test_normalize_cik_10():
    assert normalize_cik_10("320193") == "0000320193"


def test_accession_normalization():
    assert normalize_accession_no_dashes("0000320193-23-000106") == "000032019323000106"
    assert normalize_accession_with_dashes("000032019323000106") == "0000320193-23-000106"
    assert normalize_accession_with_dashes("0000320193-23-000106") == "0000320193-23-000106"


def test_complete_submission_url():
    url = complete_submission_url(
        cik="0000320193",
        accession_number="0000320193-23-000106",
        archives_base="https://www.sec.gov/Archives",
    )
    assert url == (
        "https://www.sec.gov/Archives/edgar/data/"
        "320193/000032019323000106/0000320193-23-000106.txt"
    )


def test_complete_submission_url_from_no_dash_accession():
    url = complete_submission_url(
        cik="320193",
        accession_number="000032019323000106",
        archives_base="https://www.sec.gov/Archives/",
    )
    assert url.endswith("/320193/000032019323000106/0000320193-23-000106.txt")


def test_complete_submission_output_path(tmp_path):
    path = complete_submission_output_path(
        output_dir=tmp_path,
        cik="320193",
        accession_number="0000320193-23-000106",
    )
    assert str(path).endswith("0000320193/0000320193-23-000106.txt")


def test_parse_acceptance_datetime_from_text():
    text = "<SEC-HEADER>\\n<ACCEPTANCE-DATETIME>20231103181043\\n</SEC-HEADER>"
    assert parse_acceptance_datetime_from_text(text) == datetime(2023, 11, 3, 18, 10, 43)


def test_parse_acceptance_datetime_missing():
    assert parse_acceptance_datetime_from_text("no header") is None
