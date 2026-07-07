from datetime import date
from pathlib import Path

from fvn_dfm.normalization.filing_availability import (
    extract_sec_header,
    parse_acceptance_datetime,
    parse_acceptance_datetime_raw,
    parse_complete_submission_header,
    parse_header_field,
)


HEADER = """<SEC-HEADER>0000320193-23-000106.hdr.sgml : 20231103
<ACCEPTANCE-DATETIME>20231103181043
ACCESSION NUMBER: 0000320193-23-000106
CONFORMED SUBMISSION TYPE: 10-K
FILED AS OF DATE: 20231103
CONFORMED PERIOD OF REPORT: 20230930
COMPANY DATA:
    COMPANY CONFORMED NAME: APPLE INC
    CENTRAL INDEX KEY: 0000320193
    STANDARD INDUSTRIAL CLASSIFICATION: ELECTRONIC COMPUTERS [3571]
    IRS NUMBER: 942404110
    STATE OF INCORPORATION: CA
    FISCAL YEAR END: 0930
</SEC-HEADER>
<DOCUMENT>
<TYPE>10-K
</DOCUMENT>
"""


def test_extract_sec_header():
    header = extract_sec_header(HEADER + "body")
    assert "<SEC-HEADER>" in header
    assert "</SEC-HEADER>" in header
    assert "<DOCUMENT>" not in header


def test_parse_acceptance_datetime_raw():
    assert parse_acceptance_datetime_raw(HEADER) == "20231103181043"


def test_parse_acceptance_datetime():
    dt = parse_acceptance_datetime("20231103181043")
    assert dt.year == 2023
    assert dt.month == 11
    assert dt.day == 3
    assert dt.hour == 18


def test_parse_header_field():
    assert parse_header_field(HEADER, "accession_number_header") == "0000320193-23-000106"
    assert parse_header_field(HEADER, "submission_type_header") == "10-K"
    assert parse_header_field(HEADER, "filed_as_of_date_header") == "20231103"
    assert parse_header_field(HEADER, "period_of_report_header") == "20230930"
    assert parse_header_field(HEADER, "company_conformed_name") == "APPLE INC"


def test_parse_complete_submission_header(tmp_path: Path):
    cik_dir = tmp_path / "0000320193"
    cik_dir.mkdir()
    file_path = cik_dir / "0000320193-23-000106.txt"
    file_path.write_text(HEADER, encoding="utf-8")

    row = parse_complete_submission_header(
        file_path,
        event_row={
            "form_type": "10-K",
            "filing_date": "2023-11-03",
            "report_date": "2023-09-30",
            "primary_document": "aapl-20230930.htm",
            "acceptance_datetime_from_submissions": "2023-11-03T18:10:43.000Z",
        },
    )
    assert row["cik"] == "320193"
    assert row["cik10"] == "0000320193"
    assert row["accession_number"] == "0000320193-23-000106"
    assert row["accepted_at_edgar_raw"] == "20231103181043"
    assert row["accepted_at_edgar"].startswith("2023-11-03T18:10:43")
    assert row["first_allowed_execution_date"] == "2023-11-07"
    assert row["timestamp_quality_flag"] == "GREEN"
    assert row["accession_lineage_key"] == "0000320193:0000320193-23-000106"
