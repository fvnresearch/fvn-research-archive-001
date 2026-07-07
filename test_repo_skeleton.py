from pathlib import Path

import pandas as pd

from fvn_dfm.data_ingestion.sec_primary_documents import (
    PrimaryDocumentDiscoveryConfig,
    discover_primary_document_candidates,
    write_primary_document_candidates_csv,
)


COMPLETE_SUBMISSION = """
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


def test_discover_primary_document_candidates_from_filing_availability(tmp_path: Path):
    complete_dir = tmp_path / "complete_submissions" / "0000320193"
    complete_dir.mkdir(parents=True)
    complete_file = complete_dir / "0000320193-23-000106.txt"
    complete_file.write_text(COMPLETE_SUBMISSION, encoding="utf-8")

    availability = pd.DataFrame(
        [
            {
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "form_type_from_header": "10-K",
                "form_type_from_event": "10-K",
                "primary_document_from_event": "aapl-20230930.htm",
                "header_source_file": str(complete_file),
            }
        ]
    )
    availability_path = tmp_path / "filing_availability.csv"
    availability.to_csv(availability_path, index=False)

    config = PrimaryDocumentDiscoveryConfig(
        filing_availability_path=availability_path,
        complete_submissions_dir=tmp_path / "complete_submissions",
        candidates_csv_path=tmp_path / "primary_document_candidates.csv",
        allowed_forms=("10-K", "10-Q"),
    )
    candidates = discover_primary_document_candidates(config)
    assert len(candidates) == 1
    assert candidates[0].primary_document == "aapl-20230930.htm"
    assert candidates[0].discovery_method == "primary_document_hint_confirmed_in_complete_submission"

    write_primary_document_candidates_csv(candidates, config.candidates_csv_path)
    assert "aapl-20230930.htm" in config.candidates_csv_path.read_text(encoding="utf-8")
