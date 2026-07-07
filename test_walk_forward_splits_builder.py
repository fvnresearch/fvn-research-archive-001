from pathlib import Path

import pandas as pd

from fvn_dfm.operations.schema_contracts import (
    SchemaContract,
    SchemaContractValidationConfig,
    run_schema_contract_validation,
    validate_schema_contracts,
)


def test_run_schema_contract_validation_outputs(tmp_path: Path):
    contract = SchemaContract(
        artifact_id="example",
        artifact_path="data/processed/model/example.csv",
        artifact_group="test",
        required_columns=("id", "value"),
        min_rows=1,
        non_null_columns=("id",),
        numeric_columns=("value",),
    )
    path = tmp_path / "data/processed/model/example.csv"
    path.parent.mkdir(parents=True)
    pd.DataFrame([{"id": "a", "value": 1.0}]).to_csv(path, index=False)

    cfg = SchemaContractValidationConfig(
        base_dir=tmp_path,
        registry_output_table_path=tmp_path / "data/processed/reports/schema_contract_registry.parquet",
        registry_output_csv_path=tmp_path / "data/processed/reports/schema_contract_registry.csv",
        validation_output_table_path=tmp_path / "data/processed/reports/schema_contract_validation.parquet",
        validation_output_csv_path=tmp_path / "data/processed/reports/schema_contract_validation.csv",
        summary_output_csv_path=tmp_path / "data/processed/reports/schema_contract_summary.csv",
        markdown_report_path=tmp_path / "outputs/reports/schema_contract_validation_report.md",
        diagnostics_path=tmp_path / "outputs/diagnostics/schema_contract_validation_diagnostics.csv",
    )
    registry, validation, summary = validate_schema_contracts(cfg, contracts=(contract,))
    assert summary.iloc[0]["schema_contract_status"] == "PASS"

    from fvn_dfm.operations import schema_contracts as module
    original = module.CONTRACTS
    module.CONTRACTS = (contract,)
    try:
        result = run_schema_contract_validation(cfg)
    finally:
        module.CONTRACTS = original

    assert result.iloc[0]["schema_contract_status"] == "PASS"
    assert cfg.registry_output_csv_path.exists()
    assert cfg.validation_output_csv_path.exists()
    assert cfg.summary_output_csv_path.exists()
    assert cfg.markdown_report_path.exists()
    assert cfg.diagnostics_path.exists()
