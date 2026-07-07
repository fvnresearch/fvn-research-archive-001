from pathlib import Path

import pandas as pd

from fvn_dfm.operations.schema_contracts import (
    CONTRACTS,
    SchemaContract,
    SchemaContractValidationConfig,
    contract_registry_dataframe,
    render_markdown_report,
    validate_contract,
    validate_schema_contracts,
)


def config(tmp_path: Path) -> SchemaContractValidationConfig:
    return SchemaContractValidationConfig(
        base_dir=tmp_path,
        registry_output_table_path=tmp_path / "data/processed/reports/schema_contract_registry.parquet",
        registry_output_csv_path=tmp_path / "data/processed/reports/schema_contract_registry.csv",
        validation_output_table_path=tmp_path / "data/processed/reports/schema_contract_validation.parquet",
        validation_output_csv_path=tmp_path / "data/processed/reports/schema_contract_validation.csv",
        summary_output_csv_path=tmp_path / "data/processed/reports/schema_contract_summary.csv",
        markdown_report_path=tmp_path / "outputs/reports/schema_contract_validation_report.md",
        diagnostics_path=tmp_path / "outputs/diagnostics/schema_contract_validation_diagnostics.csv",
    )


def test_contract_registry_dataframe():
    registry = contract_registry_dataframe()
    assert not registry.empty
    assert "model_dataset_with_splits" in set(registry["artifact_id"])
    assert "required_columns" in registry.columns
    assert len(CONTRACTS) >= 20


def test_validate_contract_passes(tmp_path: Path):
    path = tmp_path / "data/processed/model/example.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame(
        [
            {"id": "a", "value": 1.0, "flag": "GREEN"},
            {"id": "b", "value": 2.0, "flag": "YELLOW"},
        ]
    ).to_csv(path, index=False)
    contract = SchemaContract(
        artifact_id="example",
        artifact_path="data/processed/model/example.csv",
        artifact_group="test",
        required_columns=("id", "value", "flag"),
        min_rows=2,
        non_null_columns=("id",),
        numeric_columns=("value",),
        unique_columns=("id",),
        allowed_values={"flag": ("GREEN", "YELLOW", "RED")},
    )
    rows = validate_contract(contract, config(tmp_path))
    assert rows
    assert all(row["status"] == "PASS" for row in rows)


def test_validate_contract_fails_missing_column(tmp_path: Path):
    path = tmp_path / "data/processed/model/example.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame([{"id": "a"}]).to_csv(path, index=False)
    contract = SchemaContract(
        artifact_id="example",
        artifact_path="data/processed/model/example.csv",
        artifact_group="test",
        required_columns=("id", "missing"),
        min_rows=1,
    )
    rows = validate_contract(contract, config(tmp_path))
    assert any(row["quality_gate"] == "required_columns" and row["status"] == "FAIL" for row in rows)


def test_validate_schema_contracts_summary_fail_on_empty_repo(tmp_path: Path):
    registry, validation, summary = validate_schema_contracts(config(tmp_path))
    assert not registry.empty
    assert not validation.empty
    assert summary.iloc[0]["schema_contract_status"] == "FAIL"


def test_render_markdown_report(tmp_path: Path):
    registry, validation, summary = validate_schema_contracts(config(tmp_path))
    md = render_markdown_report(registry, validation, summary)
    assert "# Schema Contract Validation Report" in md
    assert "Failed gates" in md
    assert "validate-smoke" not in md or "outputs/smoke/e2e_smoke_v0" in md
