from fvn_dfm.data_ingestion.sec_submissions import (
    cik_to_submissions_filename,
    cik_to_submissions_url,
)


def test_cik_to_submissions_filename():
    assert cik_to_submissions_filename("320193") == "CIK0000320193.json"
    assert cik_to_submissions_filename("0000320193") == "CIK0000320193.json"


def test_cik_to_submissions_url():
    url = cik_to_submissions_url("320193", "https://data.sec.gov/submissions/")
    assert url == "https://data.sec.gov/submissions/CIK0000320193.json"
