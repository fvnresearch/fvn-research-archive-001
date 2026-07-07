from pathlib import Path

import pandas as pd

from fvn_dfm.features.fundamental_features import FundamentalFeaturesConfig, build_fundamental_features_asof


def test_build_fundamental_features_asof_outputs(tmp_path: Path):
    rows = []
    values = {
        "revenue": 2000.0,
        "net_income": 200.0,
        "cfo": 240.0,
        "assets": 5000.0,
        "liabilities": 2500.0,
        "cash": 600.0,
    }
    for concept, value in values.items():
        rows.append(
            {
                "adsh": "0000320193-23-000106",
                "cik": "320193",
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "accession_lineage_key": "0000320193:0000320193-23-000106",
                "canonical_concept": concept,
                "selected_tag": concept.upper(),
                "uom": "USD",
                "ddate": "20230930",
                "qtrs": "4" if concept in {"revenue", "net_income", "cfo"} else "0",
                "value": value,
                "form": "10-K",
                "period": "20230930",
                "fy": "2023",
                "fp": "FY",
                "filed": "20231103",
                "accepted": "2023-11-03 18:10:43",
                "selection_rank": "1",
                "fact_quality_flag": "GREEN",
                "fact_quality_notes": "",
            }
        )
    facts = pd.DataFrame(rows)
    facts_path = tmp_path / "accounting_fact_selected.csv"
    facts.to_csv(facts_path, index=False)

    config = FundamentalFeaturesConfig(
        accounting_fact_selected_path=facts_path,
        filing_availability_path=None,
        output_table_path=tmp_path / "fundamental_features_asof.parquet",
        output_csv_path=tmp_path / "fundamental_features_asof.csv",
        diagnostics_path=tmp_path / "fundamental_features_asof_diagnostics.csv",
    )

    df = build_fundamental_features_asof(config)
    assert len(df) == 1
    assert (tmp_path / "fundamental_features_asof.csv").exists()
    assert (tmp_path / "fundamental_features_asof_diagnostics.csv").exists()
    assert df.iloc[0]["net_margin"] == 0.1
    assert df.iloc[0]["cfo_to_revenue"] == 0.12
    assert df.iloc[0]["liabilities_to_assets"] == 0.5
    assert df.iloc[0]["fundamental_quality_flag"] == "YELLOW"
