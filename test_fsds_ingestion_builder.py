from pathlib import Path

import pandas as pd

from fvn_dfm.normalization.filing_availability import (
    FilingAvailabilityConfig,
    parse_complete_submission_header,
)


HEADER = """<SEC-HEADER>
<ACCEPTANCE-DATETIME>20231103150000
ACCESSION NUMBER: 0000320193-23-000106
CONFORMED SUBMISSION TYPE: 10-K
FILED AS OF DATE: 20231103
CONFORMED PERIOD OF REPORT: 20230930
COMPANY DATA:
    COMPANY CONFORMED NAME: APPLE INC
    CENTRAL INDEX KEY: 0000320193
</SEC-HEADER>
<DOCUMENT></DOCUMENT>
"""


def test_parse_header_with_event_lineage(tmp_path: Path):
    cik_dir = tmp_path / "complete_submissions" / "0000320193"
    cik_dir.mkdir(parents=True)
    file_path = cik_dir / "0000320193-23-000106.txt"
    file_path.write_text(HEADER, encoding="utf-8")

    event = {
        "cik10": "0000320193",
        "form_type": "10-K",
        "filing_date": "2023-11-03",
        "report_date": "2023-09-30",
        "primary_document": "aapl-20230930.htm",
        "acceptance_datetime_from_submissions": "2023-11-03T15:00:00.000Z",
    }

    row = parse_complete_submission_header(file_path, event_row=event)
    assert row["timestamp_quality_flag"] == "GREEN"
    assert row["first_allowed_execution_date"] == "2023-11-06"
    assert row["primary_document_from_event"] == "aapl-20230930.htm"
