from pathlib import Path

import pandas as pd

from fvn_dfm.features.fundamental_features import (
    FundamentalFeaturesConfig,
    build_fundamental_diagnostics,
    build_fundamental_features_asof_dataframe,
)


def make_selected_facts():
    base = {
        "adsh": "0000320193-23-000106",
        "cik": "320193",
        "cik10": "0000320193",
        "accession_number": "0000320193-23-000106",
        "accession_lineage_key": "0000320193:0000320193-23-000106",
        "form": "10-K",
        "period": "20230930",
        "fy": "2023",
        "fp": "FY",
        "filed": "20231103",
        "accepted": "2023-11-03 18:10:43",
        "fact_quality_flag": "GREEN",
        "fact_quality_notes": "",
        "qtrs": "4",
        "ddate": "20230930",
        "uom": "USD",
        "selection_rank": "1",
    }
    values = {
        "revenue": 1000.0,
        "net_income": 100.0,
        "cfo": 150.0,
        "assets": 2000.0,
        "liabilities": 800.0,
        "debt": 300.0,
        "cash": 250.0,
        "receivables": 120.0,
        "inventory": 80.0,
        "capex": 50.0,
        "shares": 10.0,
    }
    rows = []
    for concept, value in values.items():
        row = base.copy()
        row.update(
            {
                "canonical_concept": concept,
                "selected_tag": concept.upper(),
                "value": value,
            }
        )
        if concept in {"assets", "liabilities", "debt", "cash", "receivables", "inventory", "shares"}:
            row["qtrs"] = "0"
        if concept == "shares":
            row["uom"] = "shares"
        rows.append(row)
    return pd.DataFrame(rows)


def test_build_fundamental_features_asof_dataframe(tmp_path: Path):
    facts = make_selected_facts()
    facts_path = tmp_path / "accounting_fact_selected.csv"
    facts.to_csv(facts_path, index=False)

    availability = pd.DataFrame(
        [
            {
                "cik10": "0000320193",
                "accession_number": "0000320193-23-000106",
                "accession_lineage_key": "0000320193:0000320193-23-000106",
                "accepted_at_edgar": "2023-11-03T18:10:43-04:00",
                "first_allowed_execution_date": "2023-11-07",
                "timestamp_quality_flag": "GREEN",
            }
        ]
    )
    availability_path = tmp_path / "filing_availability.csv"
    availability.to_csv(availability_path, index=False)

    config = FundamentalFeaturesConfig(
        accounting_fact_selected_path=facts_path,
        filing_availability_path=availability_path,
        output_table_path=tmp_path / "fundamental_features_asof.parquet",
        output_csv_path=tmp_path / "fundamental_features_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )

    df = build_fundamental_features_asof_dataframe(config)
    assert len(df) == 1
    row = df.iloc[0]
    assert row["revenue"] == 1000.0
    assert row["net_income"] == 100.0
    assert row["net_margin"] == 0.1
    assert row["cfo_to_net_income"] == 1.5
    assert row["liabilities_to_assets"] == 0.4
    assert row["debt_to_assets"] == 0.15
    assert row["cash_to_assets"] == 0.125
    assert row["capex_to_revenue"] == 0.05
    assert row["fundamental_coverage_count"] == 11
    assert row["fundamental_quality_flag"] == "GREEN"
    assert row["feature_asof_date"] == "2023-11-07"


def test_fundamental_quality_missing_core_is_red(tmp_path: Path):
    facts = make_selected_facts()
    facts = facts[facts["canonical_concept"] != "assets"]
    facts_path = tmp_path / "accounting_fact_selected.csv"
    facts.to_csv(facts_path, index=False)

    config = FundamentalFeaturesConfig(
        accounting_fact_selected_path=facts_path,
        filing_availability_path=None,
        output_table_path=tmp_path / "fundamental_features_asof.parquet",
        output_csv_path=tmp_path / "fundamental_features_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )

    df = build_fundamental_features_asof_dataframe(config)
    row = df.iloc[0]
    assert row["assets_available"] is False or row["assets_available"] == False
    assert row["fundamental_quality_flag"] == "RED"
    assert "missing_core_concepts=assets" in row["fundamental_quality_notes"]


def test_build_fundamental_diagnostics(tmp_path: Path):
    facts = make_selected_facts()
    facts_path = tmp_path / "accounting_fact_selected.csv"
    facts.to_csv(facts_path, index=False)
    config = FundamentalFeaturesConfig(
        accounting_fact_selected_path=facts_path,
        filing_availability_path=None,
        output_table_path=tmp_path / "fundamental_features_asof.parquet",
        output_csv_path=tmp_path / "fundamental_features_asof.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )
    df = build_fundamental_features_asof_dataframe(config)
    diag = build_fundamental_diagnostics(df)
    assert "rows" in set(diag["diagnostic"])
    assert "revenue_coverage" in set(diag["diagnostic"])
