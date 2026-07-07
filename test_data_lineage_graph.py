from pathlib import Path

import pandas as pd

from fvn_dfm.xbrl.fact_selector import AccountingFactSelectorConfig, select_accounting_facts_dataframe


def make_num_sub():
    sub = pd.DataFrame(
        [
            {
                "adsh": "0000320193-23-000106",
                "cik": "320193",
                "form": "10-K",
                "period": "20230930",
                "fy": "2023",
                "fp": "FY",
                "filed": "20231103",
                "accepted": "2023-11-03 18:10:43",
                "fsds_year": "2023",
                "fsds_quarter": "4",
                "fsds_quarter_label": "2023q4",
                "source_zip": "2023q4.zip",
            }
        ]
    )
    num = pd.DataFrame(
        [
            {"adsh": "0000320193-23-000106", "tag": "Revenues", "version": "us-gaap/2023", "coreg": "", "ddate": "20230930", "qtrs": "4", "uom": "USD", "value": "383285000000"},
            {"adsh": "0000320193-23-000106", "tag": "RevenueFromContractWithCustomerExcludingAssessedTax", "version": "us-gaap/2023", "coreg": "", "ddate": "20230930", "qtrs": "4", "uom": "USD", "value": "383285000001"},
            {"adsh": "0000320193-23-000106", "tag": "NetIncomeLoss", "version": "us-gaap/2023", "coreg": "", "ddate": "20230930", "qtrs": "4", "uom": "USD", "value": "96995000000"},
            {"adsh": "0000320193-23-000106", "tag": "Assets", "version": "us-gaap/2023", "coreg": "", "ddate": "20230930", "qtrs": "0", "uom": "USD", "value": "352583000000"},
            {"adsh": "0000320193-23-000106", "tag": "EntityCommonStockSharesOutstanding", "version": "dei/2023", "coreg": "", "ddate": "20230930", "qtrs": "0", "uom": "shares", "value": "15550061000"},
        ]
    )
    return num, sub


def test_select_accounting_facts_dataframe(tmp_path: Path):
    num, sub = make_num_sub()
    num_path = tmp_path / "xbrl_fact_accession_raw.csv"
    sub_path = tmp_path / "xbrl_submission_metadata.csv"
    num.to_csv(num_path, index=False)
    sub.to_csv(sub_path, index=False)

    config = AccountingFactSelectorConfig(
        xbrl_fact_accession_raw_path=num_path,
        xbrl_submission_metadata_path=sub_path,
        output_table_path=tmp_path / "accounting_fact_selected.parquet",
        output_csv_path=tmp_path / "accounting_fact_selected.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )

    selected, diagnostics = select_accounting_facts_dataframe(config)
    assert set(selected["canonical_concept"]) == {"revenue", "net_income", "assets", "shares"}
    revenue = selected[selected["canonical_concept"] == "revenue"].iloc[0]
    assert revenue["selected_tag"] == "Revenues"
    assert revenue["value"] == 383285000000.0
    assert revenue["fact_quality_flag"] == "GREEN"
    shares = selected[selected["canonical_concept"] == "shares"].iloc[0]
    assert shares["uom"] == "shares"
    assert shares["accession_lineage_key"] == "0000320193:0000320193-23-000106"
    assert "revenue" in set(diagnostics["canonical_concept"])
