from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


SCHEMA_CONTRACT_REGISTRY_VERSION = "SCHEMA_CONTRACT_REGISTRY_V0"


@dataclass(frozen=True)
class SchemaContract:
    artifact_id: str
    artifact_path: str
    artifact_group: str
    required_columns: tuple[str, ...]
    min_rows: int = 1
    non_null_columns: tuple[str, ...] = ()
    numeric_columns: tuple[str, ...] = ()
    unique_columns: tuple[str, ...] = ()
    allowed_values: dict[str, tuple[str, ...]] | None = None
    description: str = ""


@dataclass(frozen=True)
class SchemaContractValidationConfig:
    base_dir: Path
    registry_output_table_path: Path
    registry_output_csv_path: Path
    validation_output_table_path: Path
    validation_output_csv_path: Path
    summary_output_csv_path: Path
    markdown_report_path: Path
    diagnostics_path: Path
    include_optional_missing: bool = True
    fail_on_blockers: bool = False
    contract_version: str = SCHEMA_CONTRACT_REGISTRY_VERSION


CONTRACTS: tuple[SchemaContract, ...] = (
    SchemaContract(
        artifact_id="raw_adjusted_prices",
        artifact_path="data/raw/prices/adjusted_prices.csv",
        artifact_group="raw_input",
        required_columns=("date",),
        min_rows=1,
        non_null_columns=("date",),
        description="Raw adjusted price file. Identifier/price aliases are checked by live readiness; this contract checks base CSV readability.",
    ),
    SchemaContract(
        artifact_id="text_features_asof",
        artifact_path="data/processed/features/text_features_asof.csv",
        artifact_group="feature",
        required_columns=("cik10", "accession_number", "primary_document", "feature_asof_date"),
        min_rows=1,
        non_null_columns=("cik10", "accession_number", "feature_asof_date"),
        description="As-of disclosure text features.",
    ),
    SchemaContract(
        artifact_id="fundamental_features_asof",
        artifact_path="data/processed/features/fundamental_features_asof.csv",
        artifact_group="feature",
        required_columns=("cik10", "accession_number", "primary_document", "feature_asof_date"),
        min_rows=1,
        non_null_columns=("cik10", "accession_number", "feature_asof_date"),
        description="As-of hard-fundamental feature table.",
    ),
    SchemaContract(
        artifact_id="mismatch_features_asof",
        artifact_path="data/processed/features/mismatch_features_asof.csv",
        artifact_group="feature",
        required_columns=("cik10", "accession_number", "primary_document", "feature_asof_date", "dfm_score_simple"),
        min_rows=1,
        non_null_columns=("cik10", "accession_number", "feature_asof_date", "dfm_score_simple"),
        numeric_columns=("dfm_score_simple",),
        description="Disclosure-fundamental mismatch features.",
    ),
    SchemaContract(
        artifact_id="model_research_panel",
        artifact_path="data/processed/model/model_research_panel.csv",
        artifact_group="model_input",
        required_columns=("panel_row_id", "cik10", "ticker", "sector", "accession_number", "primary_document", "feature_asof_date", "model_research_panel_eligible", "model_research_panel_quality_flag"),
        min_rows=1,
        non_null_columns=("panel_row_id", "cik10", "accession_number", "feature_asof_date"),
        unique_columns=("panel_row_id",),
        allowed_values={"model_research_panel_quality_flag": ("GREEN", "YELLOW", "RED")},
        description="Joined research panel before targets.",
    ),
    SchemaContract(
        artifact_id="price_return_source",
        artifact_path="data/processed/source_tables/price_return_source.csv",
        artifact_group="target_input",
        required_columns=("date", "ticker", "adjusted_close"),
        min_rows=1,
        non_null_columns=("date", "ticker", "adjusted_close"),
        numeric_columns=("adjusted_close",),
        description="Normalized price source for return target construction.",
    ),
    SchemaContract(
        artifact_id="return_targets_asof",
        artifact_path="data/processed/targets/return_targets_asof.csv",
        artifact_group="target",
        required_columns=("panel_row_id", "target_entry_date", "target_exit_date", "forward_63d_sector_adjusted_return", "return_target_quality_flag", "target_available"),
        min_rows=1,
        non_null_columns=("panel_row_id", "target_entry_date", "target_exit_date"),
        numeric_columns=("forward_63d_sector_adjusted_return",),
        allowed_values={"return_target_quality_flag": ("GREEN", "YELLOW", "RED")},
        description="Forward return targets aligned to feature as-of dates.",
    ),
    SchemaContract(
        artifact_id="model_dataset_v0",
        artifact_path="data/processed/model/model_dataset_v0.csv",
        artifact_group="model_input",
        required_columns=("model_row_id", "panel_row_id", "feature_asof_date", "y_forward_63d_sector_adjusted_return", "model_dataset_eligible", "model_dataset_quality_flag", "model_feature_columns"),
        min_rows=1,
        non_null_columns=("model_row_id", "panel_row_id", "feature_asof_date"),
        unique_columns=("model_row_id",),
        numeric_columns=("y_forward_63d_sector_adjusted_return",),
        allowed_values={"model_dataset_quality_flag": ("GREEN", "YELLOW", "RED")},
        description="Final model-ready dataset before walk-forward expansion.",
    ),
    SchemaContract(
        artifact_id="model_dataset_with_splits",
        artifact_path="data/processed/model/model_dataset_with_splits.csv",
        artifact_group="model_input",
        required_columns=("model_row_id", "walk_forward_fold_id", "walk_forward_role", "feature_asof_date", "y_forward_63d_sector_adjusted_return", "model_feature_columns"),
        min_rows=1,
        non_null_columns=("model_row_id", "walk_forward_fold_id", "walk_forward_role", "feature_asof_date"),
        numeric_columns=("y_forward_63d_sector_adjusted_return",),
        allowed_values={"walk_forward_role": ("train", "validation", "test")},
        description="Walk-forward expanded model dataset.",
    ),
    SchemaContract(
        artifact_id="baseline_fold_predictions",
        artifact_path="data/processed/model/baseline_fold_predictions.csv",
        artifact_group="prediction",
        required_columns=("walk_forward_fold_id", "walk_forward_role", "model_name", "model_row_id", "y_true", "y_pred"),
        min_rows=1,
        non_null_columns=("walk_forward_fold_id", "walk_forward_role", "model_name", "model_row_id"),
        numeric_columns=("y_true", "y_pred"),
        allowed_values={"walk_forward_role": ("train", "validation", "test")},
        description="Baseline model predictions by fold and role.",
    ),
    SchemaContract(
        artifact_id="model_selection_report",
        artifact_path="data/processed/model/model_selection_report.csv",
        artifact_group="report_input",
        required_columns=("model_name", "model_selection_rank", "is_primary_model", "validation_mean_spearman_ic", "validation_mean_mae", "validation_mean_rmse"),
        min_rows=1,
        non_null_columns=("model_name", "model_selection_rank", "is_primary_model"),
        numeric_columns=("model_selection_rank",),
        description="Model ranking and primary model selection report.",
    ),
    SchemaContract(
        artifact_id="portfolio_holdings",
        artifact_path="data/processed/portfolio/portfolio_holdings.csv",
        artifact_group="portfolio",
        required_columns=("rebalance_period", "primary_model_name", "model_row_id", "portfolio_leg", "portfolio_weight", "y_true", "y_pred"),
        min_rows=1,
        non_null_columns=("rebalance_period", "primary_model_name", "model_row_id", "portfolio_leg"),
        numeric_columns=("portfolio_weight", "y_true", "y_pred"),
        allowed_values={"portfolio_leg": ("long", "short", "excluded")},
        description="Long-short decile portfolio holdings.",
    ),
    SchemaContract(
        artifact_id="portfolio_monthly_returns",
        artifact_path="data/processed/portfolio/portfolio_monthly_returns.csv",
        artifact_group="portfolio",
        required_columns=("rebalance_period", "portfolio_gross_return", "portfolio_turnover", "transaction_cost_return", "portfolio_net_return", "gross_exposure", "net_exposure", "portfolio_quality_flag"),
        min_rows=1,
        non_null_columns=("rebalance_period", "portfolio_gross_return", "portfolio_net_return"),
        numeric_columns=("portfolio_gross_return", "portfolio_turnover", "transaction_cost_return", "portfolio_net_return", "gross_exposure", "net_exposure"),
        allowed_values={"portfolio_quality_flag": ("GREEN", "YELLOW", "RED")},
        description="Monthly portfolio return stream.",
    ),
    SchemaContract(
        artifact_id="portfolio_performance_summary",
        artifact_path="data/processed/portfolio/portfolio_performance_summary.csv",
        artifact_group="report_input",
        required_columns=("metric", "value"),
        min_rows=5,
        non_null_columns=("metric",),
        description="Key-value portfolio performance summary.",
    ),
    SchemaContract(
        artifact_id="ablation_summary",
        artifact_path="data/processed/model/ablation_summary.csv",
        artifact_group="report_input",
        required_columns=("ablation_name", "mean_spearman_ic", "mean_mae", "mean_rmse", "portfolio_cumulative_net_return", "ablation_score_rank"),
        min_rows=1,
        non_null_columns=("ablation_name",),
        numeric_columns=("ablation_score_rank",),
        description="Ablation comparison summary.",
    ),
    SchemaContract(
        artifact_id="final_research_verdict",
        artifact_path="data/processed/reports/final_research_verdict.csv",
        artifact_group="final_report",
        required_columns=("final_verdict", "passed_critical_criteria", "total_critical_criteria", "verdict_notes", "verdict_version"),
        min_rows=1,
        non_null_columns=("final_verdict", "verdict_version"),
        allowed_values={"final_verdict": ("PASS", "FAIL")},
        description="Final conservative PASS/FAIL verdict.",
    ),
    SchemaContract(
        artifact_id="final_research_evidence",
        artifact_path="data/processed/reports/final_research_evidence.csv",
        artifact_group="final_report",
        required_columns=("evidence_source", "evidence_metric", "evidence_value", "verdict_version"),
        min_rows=1,
        non_null_columns=("evidence_source", "evidence_metric"),
        description="Evidence table supporting final verdict.",
    ),
    SchemaContract(
        artifact_id="final_research_criteria",
        artifact_path="data/processed/reports/final_research_criteria.csv",
        artifact_group="final_report",
        required_columns=("criterion", "threshold", "observed_value", "passed", "critical", "verdict_version"),
        min_rows=1,
        non_null_columns=("criterion", "passed", "critical"),
        description="Criterion-level final verdict gates.",
    ),
    SchemaContract(
        artifact_id="reproducibility_file_manifest",
        artifact_path="data/processed/reports/reproducibility_file_manifest.csv",
        artifact_group="audit",
        required_columns=("relative_path", "file_name", "size_bytes", "sha256", "pack_version"),
        min_rows=1,
        non_null_columns=("relative_path", "sha256"),
        description="Reproducibility manifest with checksums.",
    ),
    SchemaContract(
        artifact_id="data_lineage_nodes",
        artifact_path="data/processed/reports/data_lineage_nodes.csv",
        artifact_group="audit",
        required_columns=("node_id", "node_type", "node_label", "artifact_path", "stage", "lineage_version"),
        min_rows=1,
        non_null_columns=("node_id", "node_type", "node_label"),
        unique_columns=("node_id",),
        description="Data lineage node table.",
    ),
    SchemaContract(
        artifact_id="data_lineage_edges",
        artifact_path="data/processed/reports/data_lineage_edges.csv",
        artifact_group="audit",
        required_columns=("edge_id", "source_node_id", "target_node_id", "edge_type", "stage", "lineage_version"),
        min_rows=1,
        non_null_columns=("edge_id", "source_node_id", "target_node_id", "edge_type"),
        unique_columns=("edge_id",),
        allowed_values={"edge_type": ("consumes", "produces", "runs_before")},
        description="Data lineage edge table.",
    ),
    SchemaContract(
        artifact_id="live_data_readiness_summary",
        artifact_path="data/processed/reports/live_data_readiness_summary.csv",
        artifact_group="operations",
        required_columns=("live_readiness_status", "blocking_failures", "failures", "warnings", "checks", "readiness_version"),
        min_rows=1,
        non_null_columns=("live_readiness_status", "readiness_version"),
        allowed_values={"live_readiness_status": ("READY", "READY_WITH_WARNINGS", "BLOCKED")},
        description="Live-data readiness summary.",
    ),
    SchemaContract(
        artifact_id="live_pipeline_execution_log",
        artifact_path="outputs/logs/live_pipeline_execution_log.csv",
        artifact_group="operations",
        required_columns=("execution_id", "stage", "stage_command_index", "command", "status", "readiness_status", "override_readiness", "dry_run", "executor_version"),
        min_rows=1,
        non_null_columns=("execution_id", "stage", "command", "status"),
        allowed_values={"status": ("success", "failed", "blocked", "dry_run")},
        description="Readiness-gated live execution command log.",
    ),
    SchemaContract(
        artifact_id="smoke_summary",
        artifact_path="outputs/smoke/smoke_summary.csv",
        artifact_group="smoke",
        required_columns=("smoke_version", "status", "work_dir", "steps", "artifact_checks"),
        min_rows=1,
        non_null_columns=("smoke_version", "status"),
        allowed_values={"status": ("PASS", "FAIL")},
        description="End-to-end smoke runner summary. For default smoke work dir, validate with --base-dir outputs/smoke/e2e_smoke_v0.",
    ),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_tuple(values: tuple[str, ...]) -> str:
    return json.dumps(list(values))


def contract_registry_dataframe(contracts: tuple[SchemaContract, ...] = CONTRACTS) -> pd.DataFrame:
    rows = []
    for contract in contracts:
        rows.append(
            {
                "artifact_id": contract.artifact_id,
                "artifact_path": contract.artifact_path,
                "artifact_group": contract.artifact_group,
                "required_columns": _json_tuple(contract.required_columns),
                "min_rows": contract.min_rows,
                "non_null_columns": _json_tuple(contract.non_null_columns),
                "numeric_columns": _json_tuple(contract.numeric_columns),
                "unique_columns": _json_tuple(contract.unique_columns),
                "allowed_values": json.dumps({k: list(v) for k, v in (contract.allowed_values or {}).items()}, sort_keys=True),
                "description": contract.description,
                "contract_version": SCHEMA_CONTRACT_REGISTRY_VERSION,
            }
        )
    return pd.DataFrame(rows)


def _read_artifact(path: Path) -> pd.DataFrame:
    if path.suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _record(
    *,
    artifact_id: str,
    artifact_path: str,
    artifact_group: str,
    gate: str,
    status: str,
    blocker: bool,
    expected: str,
    observed: Any,
    message: str,
    contract_version: str,
) -> dict[str, Any]:
    return {
        "artifact_id": artifact_id,
        "artifact_path": artifact_path,
        "artifact_group": artifact_group,
        "quality_gate": gate,
        "status": status,
        "blocker": bool(blocker),
        "expected": expected,
        "observed": observed,
        "message": message,
        "checked_at_utc": _utc_now(),
        "contract_version": contract_version,
    }


def validate_contract(contract: SchemaContract, config: SchemaContractValidationConfig) -> list[dict[str, Any]]:
    path = config.base_dir / contract.artifact_path
    rows: list[dict[str, Any]] = []

    exists = path.exists() and path.is_file()
    rows.append(
        _record(
            artifact_id=contract.artifact_id,
            artifact_path=contract.artifact_path,
            artifact_group=contract.artifact_group,
            gate="exists",
            status="PASS" if exists else "FAIL",
            blocker=True,
            expected="file exists",
            observed=exists,
            message="Artifact file exists." if exists else "Artifact file is missing.",
            contract_version=config.contract_version,
        )
    )
    if not exists:
        return rows

    try:
        df = _read_artifact(path)
        readable = True
        read_error = ""
    except Exception as exc:
        df = pd.DataFrame()
        readable = False
        read_error = repr(exc)

    rows.append(
        _record(
            artifact_id=contract.artifact_id,
            artifact_path=contract.artifact_path,
            artifact_group=contract.artifact_group,
            gate="readable",
            status="PASS" if readable else "FAIL",
            blocker=True,
            expected="readable CSV/parquet table",
            observed=readable if readable else read_error,
            message="Artifact table is readable." if readable else "Artifact table could not be read.",
            contract_version=config.contract_version,
        )
    )
    if not readable:
        return rows

    row_count = len(df)
    rows.append(
        _record(
            artifact_id=contract.artifact_id,
            artifact_path=contract.artifact_path,
            artifact_group=contract.artifact_group,
            gate="min_rows",
            status="PASS" if row_count >= contract.min_rows else "FAIL",
            blocker=True,
            expected=f">= {contract.min_rows}",
            observed=row_count,
            message="Row-count gate passed." if row_count >= contract.min_rows else "Row-count gate failed.",
            contract_version=config.contract_version,
        )
    )

    columns = set(df.columns.astype(str))
    missing_cols = [col for col in contract.required_columns if col not in columns]
    rows.append(
        _record(
            artifact_id=contract.artifact_id,
            artifact_path=contract.artifact_path,
            artifact_group=contract.artifact_group,
            gate="required_columns",
            status="PASS" if not missing_cols else "FAIL",
            blocker=True,
            expected=",".join(contract.required_columns),
            observed="missing=" + ",".join(missing_cols) if missing_cols else "all_present",
            message="Required columns are present." if not missing_cols else "Required columns are missing.",
            contract_version=config.contract_version,
        )
    )

    for col in contract.non_null_columns:
        if col not in df.columns:
            status = "FAIL"
            observed = "column_missing"
            message = f"Non-null column {col} is missing."
        else:
            null_count = int(df[col].isna().sum() + (df[col].astype(str).str.strip() == "").sum())
            status = "PASS" if null_count == 0 else "FAIL"
            observed = null_count
            message = f"Column {col} has no null/blank values." if status == "PASS" else f"Column {col} has null/blank values."
        rows.append(
            _record(
                artifact_id=contract.artifact_id,
                artifact_path=contract.artifact_path,
                artifact_group=contract.artifact_group,
                gate=f"non_null:{col}",
                status=status,
                blocker=True,
                expected="0 null/blank values",
                observed=observed,
                message=message,
                contract_version=config.contract_version,
            )
        )

    for col in contract.numeric_columns:
        if col not in df.columns:
            status = "FAIL"
            observed = "column_missing"
            message = f"Numeric column {col} is missing."
        else:
            numeric = pd.to_numeric(df[col], errors="coerce")
            bad_count = int(numeric.isna().sum() - df[col].isna().sum())
            status = "PASS" if bad_count == 0 else "FAIL"
            observed = bad_count
            message = f"Column {col} is numeric-compatible." if status == "PASS" else f"Column {col} contains non-numeric values."
        rows.append(
            _record(
                artifact_id=contract.artifact_id,
                artifact_path=contract.artifact_path,
                artifact_group=contract.artifact_group,
                gate=f"numeric:{col}",
                status=status,
                blocker=True,
                expected="numeric-compatible values",
                observed=observed,
                message=message,
                contract_version=config.contract_version,
            )
        )

    for col in contract.unique_columns:
        if col not in df.columns:
            status = "FAIL"
            observed = "column_missing"
            message = f"Unique-key column {col} is missing."
        else:
            duplicate_count = int(df[col].duplicated().sum())
            status = "PASS" if duplicate_count == 0 else "FAIL"
            observed = duplicate_count
            message = f"Column {col} is unique." if status == "PASS" else f"Column {col} contains duplicates."
        rows.append(
            _record(
                artifact_id=contract.artifact_id,
                artifact_path=contract.artifact_path,
                artifact_group=contract.artifact_group,
                gate=f"unique:{col}",
                status=status,
                blocker=True,
                expected="0 duplicate values",
                observed=observed,
                message=message,
                contract_version=config.contract_version,
            )
        )

    for col, allowed in (contract.allowed_values or {}).items():
        if col not in df.columns:
            status = "FAIL"
            observed = "column_missing"
            message = f"Allowed-values column {col} is missing."
        else:
            values = set(df[col].dropna().astype(str).str.strip())
            bad = sorted(v for v in values if v not in set(allowed))
            status = "PASS" if not bad else "FAIL"
            observed = ",".join(bad) if bad else "all_allowed"
            message = f"Column {col} only contains allowed values." if status == "PASS" else f"Column {col} contains values outside contract."
        rows.append(
            _record(
                artifact_id=contract.artifact_id,
                artifact_path=contract.artifact_path,
                artifact_group=contract.artifact_group,
                gate=f"allowed_values:{col}",
                status=status,
                blocker=True,
                expected=",".join(allowed),
                observed=observed,
                message=message,
                contract_version=config.contract_version,
            )
        )

    return rows


def validate_schema_contracts(config: SchemaContractValidationConfig, contracts: tuple[SchemaContract, ...] | None = None) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    contracts = contracts or CONTRACTS
    registry = contract_registry_dataframe(contracts)
    rows: list[dict[str, Any]] = []
    for contract in contracts:
        rows.extend(validate_contract(contract, config))
    validation = pd.DataFrame(rows)

    if validation.empty:
        blocked = True
        failures = 1
        status = "FAIL"
    else:
        failures = int((validation["status"] == "FAIL").sum())
        blockers = int(((validation["status"] == "FAIL") & validation["blocker"].astype(bool)).sum())
        blocked = blockers > 0
        status = "FAIL" if blocked else "PASS"

    summary = pd.DataFrame(
        [
            {
                "schema_contract_status": status,
                "base_dir": str(config.base_dir),
                "contracts": len(contracts),
                "validation_rows": len(validation),
                "failures": failures,
                "blocking_failures": int(((validation["status"] == "FAIL") & validation["blocker"].astype(bool)).sum()) if not validation.empty else 1,
                "checked_at_utc": _utc_now(),
                "contract_version": config.contract_version,
            }
        ]
    )
    return registry, validation, summary


def build_schema_contract_diagnostics(registry: pd.DataFrame, validation: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "registry_rows", "value": len(registry)},
        {"diagnostic": "validation_rows", "value": len(validation)},
        {"diagnostic": "summary_rows", "value": len(summary)},
    ]
    if not summary.empty:
        for col in ["schema_contract_status", "contracts", "failures", "blocking_failures"]:
            rows.append({"diagnostic": col, "value": summary.iloc[0].get(col, "")})
    if not registry.empty:
        for group, count in registry["artifact_group"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"contracts_{group}", "value": int(count)})
    if not validation.empty:
        for status, count in validation["status"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"status_{status}", "value": int(count)})
    return pd.DataFrame(rows)


def render_markdown_report(registry: pd.DataFrame, validation: pd.DataFrame, summary: pd.DataFrame) -> str:
    status = summary.iloc[0]["schema_contract_status"] if not summary.empty else "FAIL"
    lines = [
        "# Schema Contract Validation Report",
        "",
        f"Version: `{SCHEMA_CONTRACT_REGISTRY_VERSION}`",
        "",
        f"Schema contract status: **{status}**",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    if not summary.empty:
        for key, value in summary.iloc[0].items():
            lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Contract registry",
            "",
            "| Artifact | Group | Path | Min rows | Required columns |",
            "|---|---|---|---:|---|",
        ]
    )
    if not registry.empty:
        for _, row in registry.iterrows():
            lines.append(
                "| "
                + f"{row.get('artifact_id', '')} | "
                + f"{row.get('artifact_group', '')} | "
                + f"`{row.get('artifact_path', '')}` | "
                + f"{row.get('min_rows', '')} | "
                + f"`{row.get('required_columns', '')}` |"
            )

    lines.extend(
        [
            "",
            "## Failed gates",
            "",
            "| Artifact | Gate | Observed | Message |",
            "|---|---|---|---|",
        ]
    )
    failed = validation[validation["status"] == "FAIL"] if not validation.empty else pd.DataFrame()
    if failed.empty:
        lines.append("| none | none | none | all gates passed |")
    else:
        for _, row in failed.iterrows():
            lines.append(
                "| "
                + f"{row.get('artifact_id', '')} | "
                + f"{row.get('quality_gate', '')} | "
                + f"{row.get('observed', '')} | "
                + f"{row.get('message', '')} |"
            )

    lines.extend(
        [
            "",
            "## Usage",
            "",
            "Validate the main repository outputs:",
            "",
            "```bash",
            "make validate-schema-contracts",
            "```",
            "",
            "Validate the end-to-end smoke output tree:",
            "",
            "```bash",
            "python scripts/16_validate_schema_contracts.py --base-dir outputs/smoke/e2e_smoke_v0",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def write_schema_contract_outputs(
    registry: pd.DataFrame,
    validation: pd.DataFrame,
    summary: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    config: SchemaContractValidationConfig,
) -> None:
    safe_write_table(registry, parquet_path=config.registry_output_table_path, csv_path=config.registry_output_csv_path)
    safe_write_table(validation, parquet_path=config.validation_output_table_path, csv_path=config.validation_output_csv_path)
    config.summary_output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(config.summary_output_csv_path, index=False)
    config.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(config.diagnostics_path, index=False)
    config.markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
    config.markdown_report_path.write_text(render_markdown_report(registry, validation, summary), encoding="utf-8")


def run_schema_contract_validation(config: SchemaContractValidationConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.schema_contracts",
        root() / "logs/pipeline/schema_contracts.log",
    )
    logger.info("Validating schema contracts under %s", config.base_dir)
    registry, validation, summary = validate_schema_contracts(config)
    diagnostics = build_schema_contract_diagnostics(registry, validation, summary)
    write_schema_contract_outputs(registry, validation, summary, diagnostics, config=config)
    logger.info("Schema contract validation status: %s", summary.iloc[0]["schema_contract_status"])
    if config.fail_on_blockers and summary.iloc[0]["schema_contract_status"] == "FAIL":
        raise SystemExit(2)
    return summary


def default_config(base_dir: Path | None = None, repo_root: Path | None = None, fail_on_blockers: bool = False) -> SchemaContractValidationConfig:
    r = repo_root or root()
    b = base_dir or r
    return SchemaContractValidationConfig(
        base_dir=b,
        registry_output_table_path=r / "data/processed/reports/schema_contract_registry.parquet",
        registry_output_csv_path=r / "data/processed/reports/schema_contract_registry.csv",
        validation_output_table_path=r / "data/processed/reports/schema_contract_validation.parquet",
        validation_output_csv_path=r / "data/processed/reports/schema_contract_validation.csv",
        summary_output_csv_path=r / "data/processed/reports/schema_contract_summary.csv",
        markdown_report_path=r / "outputs/reports/schema_contract_validation_report.md",
        diagnostics_path=r / "outputs/diagnostics/schema_contract_validation_diagnostics.csv",
        fail_on_blockers=fail_on_blockers,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate schema contract registry v0.")
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--registry-output-table", default="data/processed/reports/schema_contract_registry.parquet")
    parser.add_argument("--registry-output-csv", default="data/processed/reports/schema_contract_registry.csv")
    parser.add_argument("--validation-output-table", default="data/processed/reports/schema_contract_validation.parquet")
    parser.add_argument("--validation-output-csv", default="data/processed/reports/schema_contract_validation.csv")
    parser.add_argument("--summary-output-csv", default="data/processed/reports/schema_contract_summary.csv")
    parser.add_argument("--markdown-report-path", default="outputs/reports/schema_contract_validation_report.md")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/schema_contract_validation_diagnostics.csv")
    parser.add_argument("--fail-on-blockers", action="store_true")
    args = parser.parse_args()

    r = root()
    base_dir = r / args.base_dir if not Path(args.base_dir).is_absolute() else Path(args.base_dir)
    config = SchemaContractValidationConfig(
        base_dir=base_dir,
        registry_output_table_path=r / args.registry_output_table,
        registry_output_csv_path=r / args.registry_output_csv,
        validation_output_table_path=r / args.validation_output_table,
        validation_output_csv_path=r / args.validation_output_csv,
        summary_output_csv_path=r / args.summary_output_csv,
        markdown_report_path=r / args.markdown_report_path,
        diagnostics_path=r / args.diagnostics_path,
        fail_on_blockers=args.fail_on_blockers,
    )
    run_schema_contract_validation(config)


if __name__ == "__main__":
    main()
