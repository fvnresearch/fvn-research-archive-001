from __future__ import annotations

import argparse

from fvn_dfm.reporting.data_lineage_graph import DataLineageGraphConfig, build_data_lineage_graph
from fvn_dfm.reporting.final_research_verdict import FinalResearchVerdictConfig, build_final_research_verdict
from fvn_dfm.reporting.final_archive_freeze import FinalArchiveFreezeConfig, build_final_archive_freeze
from fvn_dfm.reporting.release_checklist import ReleaseChecklistConfig, build_release_checklist
from fvn_dfm.reporting.publication_package import PublicationPackageConfig, build_publication_package
from fvn_dfm.reporting.public_readme_polish import PublicReadmePolishConfig, build_public_readme_polish
from fvn_dfm.reporting.reproducibility_pack import ReproducibilityPackConfig, build_reproducibility_pack
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(description="Report generation entrypoint.")
    parser.add_argument(
        "--layer",
        choices=["final-research-verdict-v0", "reproducibility-pack-v0", "data-lineage-graph-v0", "release-checklist-v0", "publication-package-v0", "public-readme-polish-v0", "final-archive-freeze-v0"],
        required=True,
        help="Report layer to build.",
    )

    # Final verdict args
    parser.add_argument("--portfolio-performance-summary-path", default="data/processed/portfolio/portfolio_performance_summary.csv")
    parser.add_argument("--model-selection-report-path", default="data/processed/model/model_selection_report.csv")
    parser.add_argument("--ablation-summary-path", default="data/processed/model/ablation_summary.csv")
    parser.add_argument("--verdict-output-table", default="data/processed/reports/final_research_verdict.parquet")
    parser.add_argument("--verdict-output-csv", default="data/processed/reports/final_research_verdict.csv")
    parser.add_argument("--evidence-output-table", default="data/processed/reports/final_research_evidence.parquet")
    parser.add_argument("--evidence-output-csv", default="data/processed/reports/final_research_evidence.csv")
    parser.add_argument("--criteria-output-table", default="data/processed/reports/final_research_criteria.parquet")
    parser.add_argument("--criteria-output-csv", default="data/processed/reports/final_research_criteria.csv")
    parser.add_argument("--markdown-report-path", default=None)
    parser.add_argument("--min-period-count", type=int, default=12)
    parser.add_argument("--min-net-sharpe", type=float, default=0.5)
    parser.add_argument("--min-cumulative-net-return", type=float, default=0.0)
    parser.add_argument("--max-net-drawdown-abs", type=float, default=0.25)
    parser.add_argument("--min-validation-ic", type=float, default=0.0)
    parser.add_argument("--do-not-require-dfm-best-ablation", action="store_true")

    # Reproducibility pack args
    parser.add_argument("--output-dir", default="outputs/audit/reproducibility_pack")
    parser.add_argument("--bundle-zip-path", default="outputs/audit/reproducibility_pack.zip")
    parser.add_argument("--manifest-output-table", default="data/processed/reports/reproducibility_file_manifest.parquet")
    parser.add_argument("--manifest-output-csv", default="data/processed/reports/reproducibility_file_manifest.csv")
    parser.add_argument("--include-data", action="store_true")

    # Data lineage args
    parser.add_argument("--nodes-output-table", default="data/processed/reports/data_lineage_nodes.parquet")
    parser.add_argument("--nodes-output-csv", default="data/processed/reports/data_lineage_nodes.csv")
    parser.add_argument("--edges-output-table", default="data/processed/reports/data_lineage_edges.parquet")
    parser.add_argument("--edges-output-csv", default="data/processed/reports/data_lineage_edges.csv")
    parser.add_argument("--exclude-missing-artifacts", action="store_true")

    # Release checklist args
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
    parser.add_argument("--require-live-readiness", action="store_true")

    # Publication package args
    parser.add_argument("--publication-package-dir", default="outputs/publication/publication_package_v0")
    parser.add_argument("--publication-package-zip-path", default="outputs/publication/publication_package_v0.zip")
    parser.add_argument("--publication-manifest-output-table", default="data/processed/reports/publication_manifest.parquet")
    parser.add_argument("--publication-manifest-output-csv", default="data/processed/reports/publication_manifest.csv")
    parser.add_argument("--publication-exclusions-output-csv", default="data/processed/reports/publication_exclusions.csv")
    parser.add_argument("--publication-sanitization-output-csv", default="data/processed/reports/publication_sanitization_checks.csv")

    # Public README polish args
    parser.add_argument("--public-readme-output-path", default="outputs/publication/publication_package_v0/PUBLICATION_README.md")

    # Final archive freeze args
    parser.add_argument("--freeze-release-version", default="v0.1.0-freeze")
    parser.add_argument("--freeze-release-title", default="FVN Research Archive 001 — Disclosure–Fundamental Mismatch")
    parser.add_argument("--freeze-manifest-output-table", default="data/processed/reports/final_archive_freeze_manifest.parquet")
    parser.add_argument("--freeze-manifest-output-csv", default="data/processed/reports/final_archive_freeze_manifest.csv")
    parser.add_argument("--freeze-release-metadata-output-csv", default="data/processed/reports/final_archive_release_metadata.csv")
    parser.add_argument("--freeze-release-metadata-output-json", default="outputs/audit/final_archive_release_metadata.json")
    parser.add_argument("--freeze-release-notes-output-path", default="outputs/reports/final_archive_release_notes.md")
    parser.add_argument("--freeze-frozen-audit-manifest-path", default="outputs/audit/final_archive_frozen_manifest.json")
    parser.add_argument("--allow-release-gate-warning", action="store_true")
    parser.add_argument("--allow-missing-publication-package", action="store_true")

    # Shared diagnostics
    parser.add_argument("--diagnostics-path")
    args = parser.parse_args()

    if args.layer == "final-research-verdict-v0":
        config = FinalResearchVerdictConfig(
            portfolio_performance_summary_path=root() / args.portfolio_performance_summary_path,
            model_selection_report_path=root() / args.model_selection_report_path,
            ablation_summary_path=root() / args.ablation_summary_path,
            verdict_output_table_path=root() / args.verdict_output_table,
            verdict_output_csv_path=root() / args.verdict_output_csv,
            evidence_output_table_path=root() / args.evidence_output_table,
            evidence_output_csv_path=root() / args.evidence_output_csv,
            criteria_output_table_path=root() / args.criteria_output_table,
            criteria_output_csv_path=root() / args.criteria_output_csv,
            markdown_report_path=root() / (args.markdown_report_path or "outputs/reports/final_research_verdict.md"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/final_research_verdict_diagnostics.csv"),
            min_period_count=args.min_period_count,
            min_net_sharpe=args.min_net_sharpe,
            min_cumulative_net_return=args.min_cumulative_net_return,
            max_net_drawdown_abs=args.max_net_drawdown_abs,
            min_validation_ic=args.min_validation_ic,
            require_dfm_ablation_best_or_tied=not args.do_not_require_dfm_best_ablation,
        )
        build_final_research_verdict(config)
        return

    if args.layer == "reproducibility-pack-v0":
        config = ReproducibilityPackConfig(
            output_dir=root() / args.output_dir,
            bundle_zip_path=root() / args.bundle_zip_path,
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/reproducibility_pack_diagnostics.csv"),
            manifest_output_table_path=root() / args.manifest_output_table,
            manifest_output_csv_path=root() / args.manifest_output_csv,
            include_data=args.include_data,
        )
        build_reproducibility_pack(config)
        return

    if args.layer == "data-lineage-graph-v0":
        config = DataLineageGraphConfig(
            repo_root=root(),
            nodes_output_table_path=root() / args.nodes_output_table,
            nodes_output_csv_path=root() / args.nodes_output_csv,
            edges_output_table_path=root() / args.edges_output_table,
            edges_output_csv_path=root() / args.edges_output_csv,
            markdown_report_path=root() / (args.markdown_report_path or "outputs/reports/data_lineage_map.md"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/data_lineage_graph_diagnostics.csv"),
            include_missing_artifacts=not args.exclude_missing_artifacts,
        )
        build_data_lineage_graph(config)
        return

    if args.layer == "release-checklist-v0":
        config = ReleaseChecklistConfig(
            final_verdict_path=root() / args.final_verdict_path,
            smoke_summary_path=root() / args.smoke_summary_path,
            schema_contract_summary_path=root() / args.schema_contract_summary_path,
            data_lineage_nodes_path=root() / args.data_lineage_nodes_path,
            data_lineage_edges_path=root() / args.data_lineage_edges_path,
            data_lineage_diagnostics_path=root() / args.data_lineage_diagnostics_path,
            reproducibility_pack_zip_path=root() / args.reproducibility_pack_zip_path,
            reproducibility_pack_diagnostics_path=root() / args.reproducibility_pack_diagnostics_path,
            live_readiness_summary_path=root() / args.live_readiness_summary_path,
            release_checklist_output_table_path=root() / args.release_checklist_output_table,
            release_checklist_output_csv_path=root() / args.release_checklist_output_csv,
            release_summary_output_csv_path=root() / args.release_summary_output_csv,
            markdown_report_path=root() / (args.markdown_report_path or "outputs/reports/release_checklist.md"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/release_checklist_diagnostics.csv"),
            live_readiness_required_for_publication=args.require_live_readiness,
        )
        build_release_checklist(config)
        return

    if args.layer == "publication-package-v0":
        config = PublicationPackageConfig(
            package_dir=root() / args.publication_package_dir,
            package_zip_path=root() / args.publication_package_zip_path,
            manifest_output_table_path=root() / args.publication_manifest_output_table,
            manifest_output_csv_path=root() / args.publication_manifest_output_csv,
            exclusions_output_csv_path=root() / args.publication_exclusions_output_csv,
            sanitization_output_csv_path=root() / args.publication_sanitization_output_csv,
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/publication_package_diagnostics.csv"),
        )
        build_publication_package(config)
        return

    if args.layer == "public-readme-polish-v0":
        package_dir = root() / args.publication_package_dir
        config = PublicReadmePolishConfig(
            publication_package_dir=package_dir,
            output_path=root() / args.public_readme_output_path,
            publication_manifest_path=package_dir / "publication_manifest.csv",
            publication_exclusions_path=package_dir / "publication_exclusions.csv",
            publication_sanitization_path=package_dir / "publication_sanitization_checks.csv",
            release_summary_path=root() / args.release_summary_path,
            final_verdict_path=root() / args.final_verdict_path,
            schema_summary_path=root() / args.schema_contract_summary_path,
            live_readiness_summary_path=root() / args.live_readiness_summary_path,
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/public_readme_polish_diagnostics.csv"),
        )
        build_public_readme_polish(config)
        return

    if args.layer == "final-archive-freeze-v0":
        config = FinalArchiveFreezeConfig(
            repo_root=root(),
            release_version=args.freeze_release_version,
            release_title=args.freeze_release_title,
            freeze_manifest_output_table_path=root() / args.freeze_manifest_output_table,
            freeze_manifest_output_csv_path=root() / args.freeze_manifest_output_csv,
            release_metadata_output_csv_path=root() / args.freeze_release_metadata_output_csv,
            release_metadata_output_json_path=root() / args.freeze_release_metadata_output_json,
            release_notes_output_path=root() / args.freeze_release_notes_output_path,
            frozen_audit_manifest_path=root() / args.freeze_frozen_audit_manifest_path,
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/final_archive_freeze_diagnostics.csv"),
            require_release_gate_pass=not args.allow_release_gate_warning,
            require_publication_package=not args.allow_missing_publication_package,
        )
        build_final_archive_freeze(config)
        return


if __name__ == "__main__":
    main()
