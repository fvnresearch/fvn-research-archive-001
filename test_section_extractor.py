from pathlib import Path

from fvn_dfm.normalization.sec_filing_event import (
    accession_no_dashes,
    extract_recent_filing_events_from_payload,
    infer_cik_from_filename,
    normalize_cik_10,
    normalize_cik_no_leading_zeros,
    write_filing_refs_csv,
)


def sample_payload():
    return {
        "cik": "320193",
        "entityType": "operating",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000320193-23-000106",
                    "0000320193-23-000077",
                    "0000320193-23-000001",
                ],
                "filingDate": ["2023-11-03", "2023-08-04", "2023-01-01"],
                "reportDate": ["2023-09-30", "2023-07-01", "2022-12-31"],
                "acceptanceDateTime": [
                    "2023-11-03T18:10:43.000Z",
                    "2023-08-04T18:04:27.000Z",
                    "2023-01-01T00:00:00.000Z",
                ],
                "form": ["10-K", "10-Q", "8-K"],
                "primaryDocument": ["aapl-20230930.htm", "aapl-20230701.htm", "aapl-8k.htm"],
                "primaryDocDescription": ["10-K", "10-Q", "8-K"],
                "act": ["34", "34", "34"],
                "fileNumber": ["001-36743", "001-36743", "001-36743"],
                "filmNumber": ["231373899", "231143456", "230000001"],
                "items": ["", "", "2.02"],
                "size": [123, 456, 789],
                "isXBRL": [1, 1, 1],
                "isInlineXBRL": [1, 1, 1],
            }
        },
    }


def test_normalizers():
    assert normalize_cik_10("320193") == "0000320193"
    assert normalize_cik_no_leading_zeros("0000320193") == "320193"
    assert accession_no_dashes("0000320193-23-000106") == "000032019323000106"


def test_infer_cik_from_filename():
    assert infer_cik_from_filename("/tmp/CIK0000320193.json") == "0000320193"
    assert infer_cik_from_filename("/tmp/CIK0000320193.json.gz") == "0000320193"
    assert infer_cik_from_filename("/tmp/nope.json") is None


def test_extract_recent_filing_events_filters_forms():
    rows = extract_recent_filing_events_from_payload(
        sample_payload(),
        source_file="/tmp/CIK0000320193.json",
        included_forms=("10-K", "10-Q"),
    )
    assert len(rows) == 2
    assert rows[0]["cik"] == "320193"
    assert rows[0]["cik10"] == "0000320193"
    assert rows[0]["accession_number"] == "0000320193-23-000106"
    assert rows[0]["form_type"] == "10-K"
    assert rows[1]["form_type"] == "10-Q"


def test_extract_recent_filing_events_date_filter():
    rows = extract_recent_filing_events_from_payload(
        sample_payload(),
        source_file="/tmp/CIK0000320193.json",
        included_forms=("10-K", "10-Q"),
        min_filing_date="2023-09-01",
    )
    assert len(rows) == 1
    assert rows[0]["form_type"] == "10-K"


def test_write_filing_refs_csv(tmp_path: Path):
    import pandas as pd

    rows = extract_recent_filing_events_from_payload(
        sample_payload(),
        source_file="/tmp/CIK0000320193.json",
        included_forms=("10-K",),
    )
    df = pd.DataFrame(rows)
    out = tmp_path / "filing_refs.csv"
    write_filing_refs_csv(df, out)

    text = out.read_text(encoding="utf-8")
    assert "cik,accession_number,form_type,filing_date,report_date,primary_document" in text
    assert "320193,0000320193-23-000106,10-K,2023-11-03,2023-09-30,aapl-20230930.htm" in text
