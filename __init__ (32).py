from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


RELEASE_CHECKLIST_VERSION = "RELEASE_CHECKLIST_V0"


@dataclass(frozen=True)
class ReleaseChecklistConfig:
    final_verdict_path: Path
    smoke_summary_path: Path
    schema_contract_summary_path: Path
    data_lineage_nodes_path: Path
    data_lineage_edges_path: Path
    data_lineage_diagnostics_path: Path
    reproducibility_pack_zip_path: Path
    reproducibility_pack_diagnostics_path: Path
    live_readiness_summary_path: Path
    release_checklist_output_table_path: Path
    release_checklist_output_csv_path: Path
    release_summary_output_csv_path: Path
    markdown_report_path: Path
    diagnostics_path: Path
    live_readiness_required_for_publication: bool = False
    checklist_version: str = RELEASE_CHECKLIST_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _first_value(df: pd.DataFrame, column: str, default: Any = "") -> Any:
    if df.empty or column not in df.columns:
        return default
    return df.iloc[0].get(column, default)


def _diagnostic_value(df: pd.DataFrame, diagnostic: str, default: Any = "") -> Any:
    if df.empty or "diagnostic" not in df.columns or "value" not in df.columns:
        return default
    rows = df[df["diagnostic"].astype(str) == diagnostic]
    if rows.empty:
        return default
    return rows.iloc[0]["value"]


def _to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    clean = str(value).strip()
    if clean == "":
        return None
    try:
        return float(clean)
    except Exception:
        return None


def _boolish(value: Any) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes", "y", "pass", "ready", "success"}


def _check_row(
    *,
    check_id: str,
    category: str,
    check_name: str,
    status: str,
    critical: bool,
    expected: str,
    observed: Any,
    evidence_path: str,
    remediation: str,
    checklist_version: str = RELEASE_CHECKLIST_VERSION,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "category": category,
        "check_name": check_name,
        "status": status,
        "critical": bool(critical),
        "expected": expected,
        "observed": observed,
        "evidence_path": evidence_path,
        "remediation": remediation,
        "checked_at_utc": _utc_now(),
        "checklist_version": checklist_version,
    }


def _gate_status(passed: bool, warning: bool = False) -> str:
    if passed:
        return "PASS"
    if warning:
        return "WARN"
    return "FAIL"


def build_release_checklist_dataframe(config: ReleaseChecklistConfig) -> pd.DataFrame:
    final_verdict = _read_csv(config.final_verdict_path)
    smoke_summary = _read_csv(config.smoke_summary_path)
    schema_summary = _read_csv(config.schema_contract_summary_path)
    lineage_nodes = _read_csv(config.data_lineage_nodes_path)
    lineage_edges = _read_csv(config.data_lineage_edges_path)
    lineage_diagnostics = _read_csv(config.data_lineage_diagnostics_path)
    repro_diagnostics = _read_csv(config.reproducibility_pack_diagnostics_path)
    live_readiness = _read_csv(config.live_readiness_summary_path)

    rows: list[dict[str, Any]] = []

    final_value = str(_first_value(final_verdict, "final_verdict", "MISSING"))
    rows.append(
        _check_row(
            check_id="FINAL_VERDICT_PASS",
            category="research_verdict",
            check_name="Final research verdict is PASS",
            status=_gate_status(final_value == "PASS"),
            critical=True,
            expected="PASS",
            observed=final_value,
            evidence_path=config.final_verdict_path.as_posix(),
            remediation="Resolve failed final verdict criteria or keep release as non-public/internal research.",
            checklist_version=config.checklist_version,
        )
    )

    smoke_value = str(_first_value(smoke_summary, "status", "MISSING"))
    rows.append(
        _check_row(
            check_id="E2E_SMOKE_PASS",
            category="testing",
            check_name="End-to-end smoke run passed",
            status=_gate_status(smoke_value == "PASS"),
            critical=True,
            expected="PASS",
            observed=smoke_value,
            evidence_path=config.smoke_summary_path.as_posix(),
            remediation="Run `make run-e2e-smoke` and resolve failed smoke steps/artifacts.",
            checklist_version=config.checklist_version,
        )
    )

    schema_value = str(_first_value(schema_summary, "schema_contract_status", "MISSING"))
    rows.append(
        _check_row(
            check_id="SCHEMA_CONTRACTS_PASS",
            category="schema_governance",
            check_name="Schema contracts passed",
            status=_gate_status(schema_value == "PASS"),
            critical=True,
            expected="PASS",
            observed=schema_value,
            evidence_path=config.schema_contract_summary_path.as_posix(),
            remediation="Run `make validate-schema-contracts` and resolve missing columns, row-count gates, or quality-gate failures.",
            checklist_version=config.checklist_version,
        )
    )

    lineage_node_count = len(lineage_nodes)
    rows.append(
        _check_row(
            check_id="LINEAGE_NODES_AVAILABLE",
            category="lineage",
            check_name="Lineage node table is available",
            status=_gate_status(lineage_node_count > 0),
            critical=True,
            expected="> 0 nodes",
            observed=lineage_node_count,
            evidence_path=config.data_lineage_nodes_path.as_posix(),
            remediation="Run `make build-data-lineage-graph` and inspect node generation.",
            checklist_version=config.checklist_version,
        )
    )

    lineage_edge_count = len(lineage_edges)
    rows.append(
        _check_row(
            check_id="LINEAGE_EDGES_AVAILABLE",
            category="lineage",
            check_name="Lineage edge table is available",
            status=_gate_status(lineage_edge_count > 0),
            critical=True,
            expected="> 0 edges",
            observed=lineage_edge_count,
            evidence_path=config.data_lineage_edges_path.as_posix(),
            remediation="Run `make build-data-lineage-graph` and inspect edge generation.",
            checklist_version=config.checklist_version,
        )
    )

    command_nodes = _to_float(_diagnostic_value(lineage_diagnostics, "command_nodes", None))
    rows.append(
        _check_row(
            check_id="LINEAGE_COMMAND_NODES_AVAILABLE",
            category="lineage",
            check_name="Lineage command nodes are present",
            status=_gate_status(command_nodes is not None and command_nodes > 0),
            critical=True,
            expected="> 0 command nodes",
            observed=command_nodes if command_nodes is not None else "MISSING",
            evidence_path=config.data_lineage_diagnostics_path.as_posix(),
            remediation="Regenerate lineage graph and confirm command nodes are emitted.",
            checklist_version=config.checklist_version,
        )
    )

    repro_zip_exists = config.reproducibility_pack_zip_path.exists() and config.reproducibility_pack_zip_path.is_file()
    rows.append(
        _check_row(
            check_id="REPRO_PACK_ZIP_EXISTS",
            category="reproducibility",
            check_name="Reproducibility pack ZIP exists",
            status=_gate_status(repro_zip_exists),
            critical=True,
            expected="ZIP exists",
            observed=repro_zip_exists,
            evidence_path=config.reproducibility_pack_zip_path.as_posix(),
            remediation="Run `make build-reproducibility-pack`.",
            checklist_version=config.checklist_version,
        )
    )

    manifest_rows = _to_float(_diagnostic_value(repro_diagnostics, "manifest_rows", None))
    rows.append(
        _check_row(
            check_id="REPRO_PACK_MANIFEST_NONEMPTY",
            category="reproducibility",
            check_name="Reproducibility manifest is non-empty",
            status=_gate_status(manifest_rows is not None and manifest_rows > 0),
            critical=True,
            expected="manifest_rows > 0",
            observed=manifest_rows if manifest_rows is not None else "MISSING",
            evidence_path=config.reproducibility_pack_diagnostics_path.as_posix(),
            remediation="Regenerate reproducibility pack and inspect manifest diagnostics.",
            checklist_version=config.checklist_version,
        )
    )

    live_status = str(_first_value(live_readiness, "live_readiness_status", "MISSING"))
    live_ready = live_status == "READY"
    live_warn = live_status in {"READY_WITH_WARNINGS", "BLOCKED", "MISSING"} and not config.live_readiness_required_for_publication
    rows.append(
        _check_row(
            check_id="LIVE_READINESS_REVIEWED",
            category="operations",
            check_name="Live-data readiness status reviewed",
            status=_gate_status(live_ready, warning=live_warn),
            critical=bool(config.live_readiness_required_for_publication),
            expected="READY" if config.live_readiness_required_for_publication else "READY preferred; warnings allowed for code-only publication",
            observed=live_status,
            evidence_path=config.live_readiness_summary_path.as_posix(),
            remediation="Run `make check-live-readiness`; configure SEC User-Agent and provide required source inputs before live-data release.",
            checklist_version=config.checklist_version,
        )
    )

    return pd.DataFrame(rows)


def build_release_summary_dataframe(checklist: pd.DataFrame, config: ReleaseChecklistConfig) -> pd.DataFrame:
    if checklist.empty:
        status = "BLOCKED"
        critical_failures = 1
        warnings = 0
        passed = 0
    else:
        critical_failures = int(((checklist["critical"].astype(bool)) & (checklist["status"] == "FAIL")).sum())
        warnings = int((checklist["status"] == "WARN").sum())
        passed = int((checklist["status"] == "PASS").sum())
        status = "PASS" if critical_failures == 0 and warnings == 0 else ("PASS_WITH_WARNINGS" if critical_failures == 0 else "BLOCKED")

    return pd.DataFrame(
        [
            {
                "release_gate_status": status,
                "critical_failures": critical_failures,
                "warnings": warnings,
                "passed_checks": passed,
                "total_checks": len(checklist),
                "live_readiness_required_for_publication": config.live_readiness_required_for_publication,
                "checked_at_utc": _utc_now(),
                "checklist_version": config.checklist_version,
            }
        ]
    )


def build_release_diagnostics(checklist: pd.DataFrame, summary: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "checklist_rows", "value": len(checklist)},
        {"diagnostic": "summary_rows", "value": len(summary)},
    ]
    if not summary.empty:
        for col in ["release_gate_status", "critical_failures", "warnings", "passed_checks", "total_checks"]:
            rows.append({"diagnostic": col, "value": summary.iloc[0].get(col, "")})
    if not checklist.empty:
        for status, count in checklist["status"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"status_{status}", "value": int(count)})
        for category, count in checklist["category"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"category_{category}", "value": int(count)})
    return pd.DataFrame(rows)


def render_markdown_report(checklist: pd.DataFrame, summary: pd.DataFrame) -> str:
    status = summary.iloc[0]["release_gate_status"] if not summary.empty else "BLOCKED"
    lines = [
        "# Release Checklist",
        "",
        f"Version: `{RELEASE_CHECKLIST_VERSION}`",
        "",
        f"Release gate status: **{status}**",
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
            "## Checks",
            "",
            "| Category | Check | Status | Critical | Observed | Evidence |",
            "|---|---|---:|---:|---|---|",
        ]
    )
    if not checklist.empty:
        for _, row in checklist.iterrows():
            lines.append(
                "| "
                + f"{row.get('category', '')} | "
                + f"{row.get('check_name', '')} | "
                + f"{row.get('status', '')} | "
                + f"{row.get('critical', '')} | "
                + f"{row.get('observed', '')} | "
                + f"`{row.get('evidence_path', '')}` |"
            )

    failed = checklist[checklist["status"] == "FAIL"] if not checklist.empty else pd.DataFrame()
    warned = checklist[checklist["status"] == "WARN"] if not checklist.empty else pd.DataFrame()
    lines.extend(["", "## Required actions", ""])
    if failed.empty and warned.empty:
        lines.append("No required actions. All release gates passed.")
    else:
        for _, row in failed.iterrows():
            lines.append(f"- **FAIL** `{row.get('check_id')}`: {row.get('remediation')}")
        for _, row in warned.iterrows():
            lines.append(f"- **WARN** `{row.get('check_id')}`: {row.get('remediation')}")

    lines.extend(
        [
            "",
            "## Release rule",
            "",
            "`PASS` means every critical publication gate passed and there are no warnings. `PASS_WITH_WARNINGS` means every critical gate passed but non-critical issues remain. `BLOCKED` means at least one critical gate failed.",
            "",
        ]
    )
    return "\n".join(lines)


def write_release_checklist_outputs(
    checklist: pd.DataFrame,
    summary: pd.DataFrame,
    diagnostics: pd.DataFrame,
    *,
    config: ReleaseChecklistConfig,
) -> None:
    safe_write_table(checklist, parquet_path=config.release_checklist_output_table_path, csv_path=config.release_checklist_output_csv_path)
    config.release_summary_output_csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(config.release_summary_output_csv_path, index=False)
    config.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(config.diagnostics_path, index=False)
    config.markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
    config.markdown_report_path.write_text(render_markdown_report(checklist, summary), encoding="utf-8")


def build_release_checklist(config: ReleaseChecklistConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.release_checklist",
        root() / "logs/pipeline/release_checklist.log",
    )
    logger.info("Building release checklist.")
    checklist = build_release_checklist_dataframe(config)
    summary = build_release_summary_dataframe(checklist, config)
    diagnostics = build_release_diagnostics(checklist, summary)
    write_release_checklist_outputs(checklist, summary, diagnostics, config=config)
    logger.info("Release gate status: %s", summary.iloc[0]["release_gate_status"])
    return summary


def default_config(repo_root: Path | None = None, live_readiness_required_for_publication: bool = False) -> ReleaseChecklistConfig:
    r = repo_root or root()
    return ReleaseChecklistConfig(
        final_verdict_path=r / "data/processed/reports/final_research_verdict.csv",
        smoke_summary_path=r / "outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_summary.csv",
        schema_contract_summary_path=r / "data/processed/reports/schema_contract_summary.csv",
        data_lineage_nodes_path=r / "data/processed/reports/data_lineage_nodes.csv",
        data_lineage_edges_path=r / "data/processed/reports/data_lineage_edges.csv",
        data_lineage_diagnostics_path=r / "outputs/diagnostics/data_lineage_graph_diagnostics.csv",
        reproducibility_pack_zip_path=r / "outputs/audit/reproducibility_pack.zip",
        reproducibility_pack_diagnostics_path=r / "outputs/diagnostics/reproducibility_pack_diagnostics.csv",
        live_readiness_summary_path=r / "data/processed/reports/live_data_readiness_summary.csv",
        release_checklist_output_table_path=r / "data/processed/reports/release_checklist.parquet",
        release_checklist_output_csv_path=r / "data/processed/reports/release_checklist.csv",
        release_summary_output_csv_path=r / "data/processed/reports/release_gate_summary.csv",
        markdown_report_path=r / "outputs/reports/release_checklist.md",
        diagnostics_path=r / "outputs/diagnostics/release_checklist_diagnostics.csv",
        live_readiness_required_for_publication=live_readiness_required_for_publication,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build release checklist v0.")
    parser.add_argument("--final-verdict-path", default="data/processed/reports/final_research_verdict.csv")
    parser.add_argument("--smoke-summary-path", default="outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_summary.csv")
    parser.add_argument("--schema-contract-summary-path", default="data/processed/reports/schema_contract_summary.csv")
    parser.add_argument("--data-lineage-nodes-path", default="data/processed/reports/data_lineage_nodes.csv")
    parser.add_argument("--data-lineage-edges-path", default="data/processed/reports/data_lineage_edges.csv")
    parser.add_argument("--data-lineage-diagnostics-path", default="outputs/diagnostics/data_lineage_graph_diagnostics.csv")
    parser.add_argument("--reproducibility-pack-zip-path", default="outputs/audit/reproducibility_pack.zip")
    parser.add_argument("--reproducibility-pack-diagnostics-path", default="outputs/diagnostics/reproducibility_pack_diagnostics.csv")
    parser.add_argument("--live-readiness-summary-path", default="data/processed/reports/live_data_readiness_summary.csv")
    parser.add_argument("--release-checklist-output-table", default="data/processed/reports/release_checklist.parquet")
    parser.add_argument("--release-checklist-output-csv", default="data/processed/reports/release_checklist.csv")
    parser.add_argument("--release-summary-output-csv", default="data/processed/reports/release_gate_summary.csv")
    parser.add_argument("--markdown-report-path", default="outputs/reports/release_checklist.md")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/release_checklist_diagnostics.csv")
    parser.add_argument("--require-live-readiness", action="store_true")
    args = parser.parse_args()

    r = root()
    config = ReleaseChecklistConfig(
        final_verdict_path=r / args.final_verdict_path,
        smoke_summary_path=r / args.smoke_summary_path,
        schema_contract_summary_path=r / args.schema_contract_summary_path,
        data_lineage_nodes_path=r / args.data_lineage_nodes_path,
        data_lineage_edges_path=r / args.data_lineage_edges_path,
        data_lineage_diagnostics_path=r / args.data_lineage_diagnostics_path,
        reproducibility_pack_zip_path=r / args.reproducibility_pack_zip_path,
        reproducibility_pack_diagnostics_path=r / args.reproducibility_pack_diagnostics_path,
        live_readiness_summary_path=r / args.live_readiness_summary_path,
        release_checklist_output_table_path=r / args.release_checklist_output_table,
        release_checklist_output_csv_path=r / args.release_checklist_output_csv,
        release_summary_output_csv_path=r / args.release_summary_output_csv,
        markdown_report_path=r / args.markdown_report_path,
        diagnostics_path=r / args.diagnostics_path,
        live_readiness_required_for_publication=args.require_live_readiness,
    )
    build_release_checklist(config)


if __name__ == "__main__":
    main()
