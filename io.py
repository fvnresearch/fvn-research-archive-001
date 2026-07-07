from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


DATA_LINEAGE_GRAPH_VERSION = "DATA_LINEAGE_GRAPH_V0"


@dataclass(frozen=True)
class LineageStep:
    step_order: int
    step_name: str
    command: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    stage: str
    description: str


@dataclass(frozen=True)
class DataLineageGraphConfig:
    repo_root: Path
    nodes_output_table_path: Path
    nodes_output_csv_path: Path
    edges_output_table_path: Path
    edges_output_csv_path: Path
    markdown_report_path: Path
    diagnostics_path: Path
    include_missing_artifacts: bool = True
    lineage_version: str = DATA_LINEAGE_GRAPH_VERSION


LINEAGE_STEPS: tuple[LineageStep, ...] = (
    LineageStep(
        1,
        "setup-checks",
        "python scripts/00_setup_project.py --check-configs --audit-skeleton",
        ("configs/00_project.yaml", "configs/01_data_sources.yaml", "REPO_SKELETON_MANIFEST.json"),
        ("logs/pipeline/project_setup.log",),
        "governance",
        "Validate configs and repository skeleton before pipeline execution.",
    ),
    LineageStep(
        2,
        "download-sec-submissions",
        "python scripts/01_download_raw_data.py --source sec-submissions",
        ("configs/01_data_sources.yaml",),
        ("data/raw/sec/submissions", "data/manifests/raw/sec_submissions_manifest.csv"),
        "raw-ingestion",
        "Download SEC submissions metadata.",
    ),
    LineageStep(
        3,
        "download-sec-complete-submissions",
        "python scripts/01_download_raw_data.py --source sec-complete-submissions",
        ("configs/01_data_sources.yaml", "data/raw/sec/submissions"),
        ("data/raw/sec/complete_submissions", "data/manifests/raw/sec_complete_submissions_manifest.csv"),
        "raw-ingestion",
        "Download complete SEC submission histories.",
    ),
    LineageStep(
        4,
        "build-filing-events",
        "python scripts/02_build_source_tables.py --source sec-filing-events",
        ("data/raw/sec/submissions", "data/raw/sec/complete_submissions"),
        ("data/processed/source_tables/sec_filing_events.parquet", "data/processed/source_tables/sec_filing_events.csv"),
        "source-tables",
        "Create filing event source table.",
    ),
    LineageStep(
        5,
        "build-filing-availability",
        "python scripts/03_build_point_in_time_tables.py --layer filing-availability",
        ("data/processed/source_tables/sec_filing_events.csv",),
        ("data/processed/point_in_time/filing_availability.parquet", "data/processed/point_in_time/filing_availability.csv"),
        "point-in-time",
        "Build filing availability table using accepted timestamps.",
    ),
    LineageStep(
        6,
        "discover-primary-documents",
        "python scripts/02_build_source_tables.py --source sec-primary-documents",
        ("data/processed/point_in_time/filing_availability.csv", "data/raw/sec/primary_documents"),
        ("data/processed/source_tables/sec_primary_documents.parquet", "data/processed/source_tables/sec_primary_documents.csv"),
        "source-tables",
        "Discover primary 10-K/10-Q filing documents.",
    ),
    LineageStep(
        7,
        "extract-filing-text",
        "python scripts/04_extract_text.py --layer filing-text-raw",
        ("data/processed/source_tables/sec_primary_documents.csv", "data/raw/sec/primary_documents"),
        ("data/processed/text/filing_text_raw.parquet", "data/processed/text/filing_text_raw.csv"),
        "text",
        "Extract raw cleaned filing text.",
    ),
    LineageStep(
        8,
        "extract-filing-sections",
        "python scripts/04_extract_text.py --layer filing-section-text",
        ("data/processed/text/filing_text_raw.csv",),
        ("data/processed/text/filing_section_text.parquet", "data/processed/text/filing_section_text.csv"),
        "text",
        "Extract MD&A, risk, liquidity and other filing sections.",
    ),
    LineageStep(
        9,
        "build-text-features",
        "python scripts/06_build_features.py --layer text-features-asof",
        ("data/processed/text/filing_section_text.csv", "data/raw/dictionaries/loughran_mcdonald"),
        ("data/processed/features/text_features_asof.parquet", "data/processed/features/text_features_asof.csv"),
        "features",
        "Build as-of disclosure text features.",
    ),
    LineageStep(
        10,
        "download-fsds",
        "python scripts/01_download_raw_data.py --source sec-fsds --years 2009-2025",
        ("configs/01_data_sources.yaml",),
        ("data/raw/sec/financial_statement_data_sets",),
        "raw-ingestion",
        "Download SEC Financial Statement Data Sets.",
    ),
    LineageStep(
        11,
        "extract-xbrl-facts",
        "python scripts/05_extract_xbrl_facts.py --source sec-fsds",
        ("data/raw/sec/financial_statement_data_sets",),
        ("data/processed/source_tables/sec_fsds_facts.parquet", "data/processed/source_tables/sec_fsds_facts.csv"),
        "xbrl",
        "Normalize SEC FSDS accounting facts.",
    ),
    LineageStep(
        12,
        "select-accounting-facts",
        "python scripts/05_extract_xbrl_facts.py --source accounting-fact-selected",
        ("data/processed/source_tables/sec_fsds_facts.csv",),
        ("data/processed/source_tables/accounting_fact_selected.parquet", "data/processed/source_tables/accounting_fact_selected.csv"),
        "xbrl",
        "Select canonical accounting facts for feature construction.",
    ),
    LineageStep(
        13,
        "build-fundamental-features",
        "python scripts/06_build_features.py --layer fundamental-features-asof",
        ("data/processed/source_tables/accounting_fact_selected.csv", "data/processed/point_in_time/filing_availability.csv"),
        ("data/processed/features/fundamental_features_asof.parquet", "data/processed/features/fundamental_features_asof.csv"),
        "features",
        "Build as-of hard-fundamental features.",
    ),
    LineageStep(
        14,
        "build-fundamental-deltas",
        "python scripts/06_build_features.py --layer fundamental-delta-features-asof",
        ("data/processed/features/fundamental_features_asof.csv",),
        ("data/processed/features/fundamental_delta_features_asof.parquet", "data/processed/features/fundamental_delta_features_asof.csv"),
        "features",
        "Build comparable-period accounting deltas.",
    ),
    LineageStep(
        15,
        "build-fundamental-composites",
        "python scripts/06_build_features.py --layer fundamental-composite-features-asof",
        ("data/processed/features/fundamental_delta_features_asof.csv",),
        ("data/processed/features/fundamental_composite_features_asof.parquet", "data/processed/features/fundamental_composite_features_asof.csv"),
        "features",
        "Build fundamental stress and improvement composites.",
    ),
    LineageStep(
        16,
        "build-mismatch-features",
        "python scripts/06_build_features.py --layer mismatch-features-asof",
        ("data/processed/features/fundamental_composite_features_asof.csv", "data/processed/features/text_features_asof.csv"),
        ("data/processed/features/mismatch_features_asof.parquet", "data/processed/features/mismatch_features_asof.csv"),
        "features",
        "Build disclosure-fundamental mismatch features.",
    ),
    LineageStep(
        17,
        "build-research-panel",
        "python scripts/07_build_model_matrix.py --layer model-research-panel",
        (
            "data/processed/features/mismatch_features_asof.csv",
            "data/processed/features/fundamental_features_asof.csv",
            "data/processed/features/text_features_asof.csv",
            "data/processed/point_in_time/filing_availability.csv",
        ),
        ("data/processed/model/model_research_panel.parquet", "data/processed/model/model_research_panel.csv"),
        "model-panel",
        "Assemble model research panel and quality gates.",
    ),
    LineageStep(
        18,
        "build-price-return-source",
        "python scripts/08_build_targets.py --layer price-return-source --raw-price-path data/raw/prices/adjusted_prices.csv",
        ("data/raw/prices/adjusted_prices.csv",),
        ("data/processed/source_tables/price_return_source.parquet", "data/processed/source_tables/price_return_source.csv"),
        "targets",
        "Normalize adjusted price source.",
    ),
    LineageStep(
        19,
        "build-return-targets",
        "python scripts/08_build_targets.py --layer return-targets-asof",
        ("data/processed/model/model_research_panel.csv", "data/processed/source_tables/price_return_source.csv"),
        ("data/processed/targets/return_targets_asof.parquet", "data/processed/targets/return_targets_asof.csv"),
        "targets",
        "Build forward sector-adjusted return targets.",
    ),
    LineageStep(
        20,
        "build-model-dataset",
        "python scripts/07_build_model_matrix.py --layer model-dataset-v0",
        ("data/processed/model/model_research_panel.csv", "data/processed/targets/return_targets_asof.csv"),
        ("data/processed/model/model_dataset_v0.parquet", "data/processed/model/model_dataset_v0.csv"),
        "modeling",
        "Join features and labels into final modeling dataset.",
    ),
    LineageStep(
        21,
        "build-walk-forward-splits",
        "python scripts/07_build_model_matrix.py --layer model-dataset-with-splits",
        ("data/processed/model/model_dataset_v0.csv",),
        ("data/processed/model/model_dataset_with_splits.parquet", "data/processed/model/model_dataset_with_splits.csv"),
        "modeling",
        "Assign walk-forward train/validation/test folds.",
    ),
    LineageStep(
        22,
        "train-baseline-models",
        "python scripts/09_train_models.py --layer baseline-models-v0",
        ("data/processed/model/model_dataset_with_splits.csv",),
        ("data/processed/model/baseline_fold_predictions.parquet", "data/processed/model/baseline_fold_predictions.csv", "outputs/diagnostics/baseline_model_diagnostics.csv"),
        "modeling",
        "Train baseline models and output fold predictions.",
    ),
    LineageStep(
        23,
        "build-model-selection-report",
        "python scripts/10_evaluate_models.py --layer model-selection-report-v0",
        ("data/processed/model/baseline_fold_predictions.csv", "outputs/diagnostics/baseline_model_diagnostics.csv"),
        ("data/processed/model/model_selection_report.parquet", "data/processed/model/model_selection_report.csv", "outputs/reports/model_selection_report.md"),
        "evaluation",
        "Rank baseline models and select primary model.",
    ),
    LineageStep(
        24,
        "build-long-short-decile",
        "python scripts/11_build_portfolio.py --layer long-short-decile-v0",
        ("data/processed/model/baseline_fold_predictions.csv", "data/processed/model/model_selection_report.csv"),
        ("data/processed/portfolio/portfolio_holdings.parquet", "data/processed/portfolio/portfolio_holdings.csv", "data/processed/portfolio/portfolio_monthly_returns.parquet", "data/processed/portfolio/portfolio_monthly_returns.csv"),
        "portfolio",
        "Build primary-model long-short decile portfolio.",
    ),
    LineageStep(
        25,
        "build-portfolio-performance",
        "python scripts/11_build_portfolio.py --layer portfolio-performance-report-v0",
        ("data/processed/portfolio/portfolio_monthly_returns.csv",),
        ("data/processed/portfolio/portfolio_performance_summary.parquet", "data/processed/portfolio/portfolio_performance_summary.csv", "data/processed/portfolio/portfolio_monthly_diagnostics.parquet", "data/processed/portfolio/portfolio_monthly_diagnostics.csv", "outputs/reports/portfolio_performance_report.md"),
        "portfolio",
        "Compute performance and monthly diagnostics.",
    ),
    LineageStep(
        26,
        "build-ablation-study",
        "python scripts/10_evaluate_models.py --layer ablation-study-v0",
        ("data/processed/model/model_dataset_with_splits.csv",),
        ("data/processed/model/ablation_summary.parquet", "data/processed/model/ablation_summary.csv", "data/processed/model/ablation_metrics.csv", "data/processed/model/ablation_predictions.csv", "data/processed/portfolio/ablation_portfolio_returns.csv", "outputs/reports/ablation_study_report.md"),
        "evaluation",
        "Compare DFM score to fundamentals-only, text-only, and naive baselines.",
    ),
    LineageStep(
        27,
        "build-final-verdict",
        "python scripts/12_generate_reports.py --layer final-research-verdict-v0",
        ("data/processed/portfolio/portfolio_performance_summary.csv", "data/processed/model/model_selection_report.csv", "data/processed/model/ablation_summary.csv"),
        ("data/processed/reports/final_research_verdict.csv", "data/processed/reports/final_research_evidence.csv", "data/processed/reports/final_research_criteria.csv", "outputs/reports/final_research_verdict.md"),
        "reporting",
        "Build conservative final PASS/FAIL research verdict.",
    ),
    LineageStep(
        28,
        "build-reproducibility-pack",
        "python scripts/12_generate_reports.py --layer reproducibility-pack-v0",
        ("data/processed/reports/final_research_verdict.csv", "outputs/reports/final_research_verdict.md"),
        ("outputs/audit/reproducibility_pack.zip", "data/processed/reports/reproducibility_file_manifest.csv"),
        "audit",
        "Build reproducibility pack with manifests, checksums, config snapshot, and run order.",
    ),
    LineageStep(
        29,
        "check-live-readiness",
        "python scripts/14_check_live_readiness.py",
        ("configs/01_data_sources.yaml", "data/raw/prices/adjusted_prices.csv", "data/raw/dictionaries/loughran_mcdonald", "data/raw/sec/financial_statement_data_sets"),
        ("data/processed/reports/live_data_readiness_report.csv", "data/processed/reports/live_data_readiness_summary.csv", "outputs/reports/live_data_readiness_report.md"),
        "operations",
        "Check live-data source and compliance readiness.",
    ),
    LineageStep(
        30,
        "run-live-pipeline",
        "python scripts/15_run_live_pipeline.py --stage full-live",
        ("data/processed/reports/live_data_readiness_summary.csv",),
        ("outputs/logs/live_pipeline_execution_log.csv", "outputs/logs/live_pipeline_execution_summary.csv", "outputs/reports/live_pipeline_execution_report.md"),
        "operations",
        "Run live pipeline behind readiness gate and command audit log.",
    ),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _node_id(kind: str, value: str) -> str:
    stable = f"{kind}:{value}".encode("utf-8")
    return hashlib.sha1(stable).hexdigest()[:16]


def _artifact_group(path: str) -> str:
    if path.startswith("data/raw"):
        return "raw"
    if path.startswith("data/processed"):
        return "processed"
    if path.startswith("outputs/reports"):
        return "report"
    if path.startswith("outputs/diagnostics"):
        return "diagnostic"
    if path.startswith("outputs/logs") or path.startswith("logs/"):
        return "log"
    if path.startswith("outputs/audit"):
        return "audit"
    if path.startswith("configs/"):
        return "config"
    if path.endswith(".md"):
        return "documentation"
    return "repository"


def _artifact_type(path: str) -> str:
    group = _artifact_group(path)
    if group == "raw":
        return "raw_input"
    if group == "processed":
        return "processed_artifact"
    if group == "report":
        return "report"
    if group == "diagnostic":
        return "diagnostic"
    if group == "audit":
        return "audit_artifact"
    if group == "config":
        return "config"
    if group == "log":
        return "log"
    return "repository_file"


def _path_status(repo_root: Path, path: str) -> tuple[bool, int | None]:
    full = repo_root / path
    if not full.exists():
        return False, None
    if full.is_file():
        return True, int(full.stat().st_size)
    if full.is_dir():
        count = sum(1 for p in full.rglob("*") if p.is_file())
        return True, count


def _add_node(nodes: dict[str, dict[str, Any]], *, node_type: str, label: str, artifact_path: str, stage: str, command: str, repo_root: Path, description: str, version: str) -> str:
    node_id = _node_id(node_type, label)
    if node_id in nodes:
        return node_id

    exists, size_or_count = _path_status(repo_root, artifact_path) if artifact_path else (False, None)
    nodes[node_id] = {
        "node_id": node_id,
        "node_type": node_type,
        "node_label": label,
        "artifact_path": artifact_path,
        "artifact_group": _artifact_group(artifact_path) if artifact_path else "command",
        "stage": stage,
        "command": command,
        "exists": exists if artifact_path else "",
        "size_bytes_or_file_count": size_or_count,
        "description": description,
        "created_at_utc": _utc_now(),
        "lineage_version": version,
    }
    return node_id


def build_lineage_nodes_and_edges(config: DataLineageGraphConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    previous_command_id: str | None = None
    edge_counter = 0

    for step in LINEAGE_STEPS:
        command_id = _add_node(
            nodes,
            node_type="command",
            label=step.step_name,
            artifact_path="",
            stage=step.stage,
            command=step.command,
            repo_root=config.repo_root,
            description=step.description,
            version=config.lineage_version,
        )

        if previous_command_id is not None:
            edge_counter += 1
            edges.append(
                {
                    "edge_id": f"E{edge_counter:05d}",
                    "source_node_id": previous_command_id,
                    "target_node_id": command_id,
                    "source_label": nodes[previous_command_id]["node_label"],
                    "target_label": step.step_name,
                    "edge_type": "runs_before",
                    "stage": step.stage,
                    "step_order": step.step_order,
                    "command": step.command,
                    "notes": "Pipeline run-order dependency.",
                    "lineage_version": config.lineage_version,
                }
            )
        previous_command_id = command_id

        for input_path in step.inputs:
            node_type = _artifact_type(input_path)
            input_id = _add_node(
                nodes,
                node_type=node_type,
                label=input_path,
                artifact_path=input_path,
                stage=step.stage,
                command="",
                repo_root=config.repo_root,
                description=f"Input for {step.step_name}.",
                version=config.lineage_version,
            )
            exists, _ = _path_status(config.repo_root, input_path)
            if exists or config.include_missing_artifacts:
                edge_counter += 1
                edges.append(
                    {
                        "edge_id": f"E{edge_counter:05d}",
                        "source_node_id": input_id,
                        "target_node_id": command_id,
                        "source_label": input_path,
                        "target_label": step.step_name,
                        "edge_type": "consumes",
                        "stage": step.stage,
                        "step_order": step.step_order,
                        "command": step.command,
                        "notes": "Command consumes input artifact.",
                        "lineage_version": config.lineage_version,
                    }
                )

        for output_path in step.outputs:
            node_type = _artifact_type(output_path)
            output_id = _add_node(
                nodes,
                node_type=node_type,
                label=output_path,
                artifact_path=output_path,
                stage=step.stage,
                command="",
                repo_root=config.repo_root,
                description=f"Output produced by {step.step_name}.",
                version=config.lineage_version,
            )
            exists, _ = _path_status(config.repo_root, output_path)
            if exists or config.include_missing_artifacts:
                edge_counter += 1
                edges.append(
                    {
                        "edge_id": f"E{edge_counter:05d}",
                        "source_node_id": command_id,
                        "target_node_id": output_id,
                        "source_label": step.step_name,
                        "target_label": output_path,
                        "edge_type": "produces",
                        "stage": step.stage,
                        "step_order": step.step_order,
                        "command": step.command,
                        "notes": "Command produces output artifact.",
                        "lineage_version": config.lineage_version,
                    }
                )

    node_df = pd.DataFrame(nodes.values()).sort_values(["node_type", "stage", "node_label"]).reset_index(drop=True)
    edge_df = pd.DataFrame(edges).sort_values(["step_order", "edge_id"]).reset_index(drop=True)
    return node_df, edge_df


def build_lineage_diagnostics(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = [
        {"diagnostic": "lineage_version", "value": DATA_LINEAGE_GRAPH_VERSION},
        {"diagnostic": "node_rows", "value": len(nodes)},
        {"diagnostic": "edge_rows", "value": len(edges)},
        {"diagnostic": "command_nodes", "value": int((nodes["node_type"] == "command").sum()) if not nodes.empty else 0},
    ]
    if not nodes.empty:
        rows.append({"diagnostic": "existing_artifact_nodes", "value": int(nodes["exists"].astype(str).str.lower().isin(["true"]).sum())})
        for node_type, count in nodes["node_type"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"nodes_{node_type}", "value": int(count)})
    if not edges.empty:
        for edge_type, count in edges["edge_type"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"edges_{edge_type}", "value": int(count)})
        for stage, count in edges["stage"].value_counts(dropna=False).items():
            rows.append({"diagnostic": f"edges_stage_{stage}", "value": int(count)})
    return pd.DataFrame(rows)


def render_markdown_lineage_map(nodes: pd.DataFrame, edges: pd.DataFrame) -> str:
    lines = [
        "# Data Lineage Map",
        "",
        f"Version: `{DATA_LINEAGE_GRAPH_VERSION}`",
        "",
        "This map links raw inputs, processed artifacts, reports, and commands through machine-readable dependency edges.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Nodes | {len(nodes)} |",
        f"| Edges | {len(edges)} |",
        f"| Commands | {int((nodes['node_type'] == 'command').sum()) if not nodes.empty else 0} |",
        "",
        "## Pipeline stages",
        "",
        "| Step | Stage | Command | Inputs | Outputs |",
        "|---:|---|---|---:|---:|",
    ]
    for step in LINEAGE_STEPS:
        lines.append(
            f"| {step.step_order} | {step.stage} | `{step.step_name}` | {len(step.inputs)} | {len(step.outputs)} |"
        )

    lines.extend(
        [
            "",
            "## Edges by stage",
            "",
            "| Stage | Edges |",
            "|---|---:|",
        ]
    )
    if not edges.empty:
        for stage, count in edges["stage"].value_counts().sort_index().items():
            lines.append(f"| {stage} | {int(count)} |")

    lines.extend(
        [
            "",
            "## Critical terminal artifacts",
            "",
            "| Artifact | Exists | Node type |",
            "|---|---:|---|",
        ]
    )
    critical = [
        "data/processed/model/model_dataset_with_splits.csv",
        "data/processed/model/baseline_fold_predictions.csv",
        "data/processed/model/model_selection_report.csv",
        "data/processed/portfolio/portfolio_monthly_returns.csv",
        "data/processed/portfolio/portfolio_performance_summary.csv",
        "data/processed/model/ablation_summary.csv",
        "data/processed/reports/final_research_verdict.csv",
        "outputs/audit/reproducibility_pack.zip",
        "outputs/logs/live_pipeline_execution_log.csv",
    ]
    if not nodes.empty:
        lookup = nodes.set_index("artifact_path", drop=False)
        for artifact in critical:
            if artifact in lookup.index:
                row = lookup.loc[artifact]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                lines.append(f"| `{artifact}` | {row.get('exists', '')} | {row.get('node_type', '')} |")
            else:
                lines.append(f"| `{artifact}` | False | missing |")

    lines.extend(
        [
            "",
            "## Machine-readable outputs",
            "",
            "- `data_lineage_nodes.csv`: one row per command or artifact node.",
            "- `data_lineage_edges.csv`: dependency edges connecting inputs, commands, outputs, and run order.",
            "",
        ]
    )
    return "\n".join(lines)


def write_lineage_outputs(nodes: pd.DataFrame, edges: pd.DataFrame, diagnostics: pd.DataFrame, *, config: DataLineageGraphConfig) -> None:
    safe_write_table(nodes, parquet_path=config.nodes_output_table_path, csv_path=config.nodes_output_csv_path)
    safe_write_table(edges, parquet_path=config.edges_output_table_path, csv_path=config.edges_output_csv_path)
    config.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(config.diagnostics_path, index=False)
    config.markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
    config.markdown_report_path.write_text(render_markdown_lineage_map(nodes, edges), encoding="utf-8")


def build_data_lineage_graph(config: DataLineageGraphConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    logger = get_logger(
        "fvn_dfm.data_lineage_graph",
        root() / "logs/pipeline/data_lineage_graph.log",
    )
    logger.info("Building data lineage graph.")
    nodes, edges = build_lineage_nodes_and_edges(config)
    diagnostics = build_lineage_diagnostics(nodes, edges)
    write_lineage_outputs(nodes, edges, diagnostics, config=config)
    logger.info("Wrote data lineage graph with %d nodes and %d edges.", len(nodes), len(edges))
    return nodes, edges


def default_config(repo_root: Path | None = None) -> DataLineageGraphConfig:
    r = repo_root or root()
    return DataLineageGraphConfig(
        repo_root=r,
        nodes_output_table_path=r / "data/processed/reports/data_lineage_nodes.parquet",
        nodes_output_csv_path=r / "data/processed/reports/data_lineage_nodes.csv",
        edges_output_table_path=r / "data/processed/reports/data_lineage_edges.parquet",
        edges_output_csv_path=r / "data/processed/reports/data_lineage_edges.csv",
        markdown_report_path=r / "outputs/reports/data_lineage_map.md",
        diagnostics_path=r / "outputs/diagnostics/data_lineage_graph_diagnostics.csv",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build data lineage graph v0.")
    parser.add_argument("--nodes-output-table", default="data/processed/reports/data_lineage_nodes.parquet")
    parser.add_argument("--nodes-output-csv", default="data/processed/reports/data_lineage_nodes.csv")
    parser.add_argument("--edges-output-table", default="data/processed/reports/data_lineage_edges.parquet")
    parser.add_argument("--edges-output-csv", default="data/processed/reports/data_lineage_edges.csv")
    parser.add_argument("--markdown-report-path", default="outputs/reports/data_lineage_map.md")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/data_lineage_graph_diagnostics.csv")
    parser.add_argument("--exclude-missing-artifacts", action="store_true")
    args = parser.parse_args()

    r = root()
    config = DataLineageGraphConfig(
        repo_root=r,
        nodes_output_table_path=r / args.nodes_output_table,
        nodes_output_csv_path=r / args.nodes_output_csv,
        edges_output_table_path=r / args.edges_output_table,
        edges_output_csv_path=r / args.edges_output_csv,
        markdown_report_path=r / args.markdown_report_path,
        diagnostics_path=r / args.diagnostics_path,
        include_missing_artifacts=not args.exclude_missing_artifacts,
    )
    build_data_lineage_graph(config)


if __name__ == "__main__":
    main()
