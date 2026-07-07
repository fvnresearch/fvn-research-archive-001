from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.release_checklist import (
    ReleaseChecklistConfig,
    build_release_checklist_dataframe,
    build_release_summary_dataframe,
    render_markdown_report,
)


def config(tmp_path: Path, *, require_live: bool = False) -> ReleaseChecklistConfig:
    return ReleaseChecklistConfig(
        final_verdict_path=tmp_path / "data/processed/reports/final_research_verdict.csv",
        smoke_summary_path=tmp_path / "outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_summary.csv",
        schema_contract_summary_path=tmp_path / "data/processed/reports/schema_contract_summary.csv",
        data_lineage_nodes_path=tmp_path / "data/processed/reports/data_lineage_nodes.csv",
        data_lineage_edges_path=tmp_path / "data/processed/reports/data_lineage_edges.csv",
        data_lineage_diagnostics_path=tmp_path / "outputs/diagnostics/data_lineage_graph_diagnostics.csv",
        reproducibility_pack_zip_path=tmp_path / "outputs/audit/reproducibility_pack.zip",
        reproducibility_pack_diagnostics_path=tmp_path / "outputs/diagnostics/reproducibility_pack_diagnostics.csv",
        live_readiness_summary_path=tmp_path / "data/processed/reports/live_data_readiness_summary.csv",
        release_checklist_output_table_path=tmp_path / "data/processed/reports/release_checklist.parquet",
        release_checklist_output_csv_path=tmp_path / "data/processed/reports/release_checklist.csv",
        release_summary_output_csv_path=tmp_path / "data/processed/reports/release_gate_summary.csv",
        markdown_report_path=tmp_path / "outputs/reports/release_checklist.md",
        diagnostics_path=tmp_path / "outputs/diagnostics/release_checklist_diagnostics.csv",
        live_readiness_required_for_publication=require_live,
    )


def write_release_inputs(tmp_path: Path, *, final="PASS", smoke="PASS", schema="PASS", live="READY"):
    (tmp_path / "data/processed/reports").mkdir(parents=True)
    (tmp_path / "outputs/smoke/e2e_smoke_v0/outputs/smoke").mkdir(parents=True)
    (tmp_path / "outputs/diagnostics").mkdir(parents=True)
    (tmp_path / "outputs/audit").mkdir(parents=True)

    pd.DataFrame([{"final_verdict": final}]).to_csv(tmp_path / "data/processed/reports/final_research_verdict.csv", index=False)
    pd.DataFrame([{"status": smoke, "steps": 14, "artifact_checks": 20}]).to_csv(tmp_path / "outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_summary.csv", index=False)
    pd.DataFrame([{"schema_contract_status": schema, "contracts": 24, "blocking_failures": 0}]).to_csv(tmp_path / "data/processed/reports/schema_contract_summary.csv", index=False)
    pd.DataFrame([{"node_id": "n1", "node_type": "command"}, {"node_id": "n2", "node_type": "processed_artifact"}]).to_csv(tmp_path / "data/processed/reports/data_lineage_nodes.csv", index=False)
    pd.DataFrame([{"edge_id": "e1", "source_node_id": "n1", "target_node_id": "n2", "edge_type": "produces"}]).to_csv(tmp_path / "data/processed/reports/data_lineage_edges.csv", index=False)
    pd.DataFrame([{"diagnostic": "command_nodes", "value": 1}]).to_csv(tmp_path / "outputs/diagnostics/data_lineage_graph_diagnostics.csv", index=False)
    (tmp_path / "outputs/audit/reproducibility_pack.zip").write_text("zip-stub", encoding="utf-8")
    pd.DataFrame([{"diagnostic": "manifest_rows", "value": 100}]).to_csv(tmp_path / "outputs/diagnostics/reproducibility_pack_diagnostics.csv", index=False)
    pd.DataFrame([{"live_readiness_status": live, "blocking_failures": 0}]).to_csv(tmp_path / "data/processed/reports/live_data_readiness_summary.csv", index=False)


def test_release_checklist_pass(tmp_path: Path):
    write_release_inputs(tmp_path)
    checklist = build_release_checklist_dataframe(config(tmp_path))
    summary = build_release_summary_dataframe(checklist, config(tmp_path))
    assert summary.iloc[0]["release_gate_status"] == "PASS"
    assert checklist["status"].eq("PASS").all()


def test_release_checklist_warns_when_live_not_ready_but_not_required(tmp_path: Path):
    write_release_inputs(tmp_path, live="BLOCKED")
    checklist = build_release_checklist_dataframe(config(tmp_path, require_live=False))
    summary = build_release_summary_dataframe(checklist, config(tmp_path, require_live=False))
    assert summary.iloc[0]["release_gate_status"] == "PASS_WITH_WARNINGS"
    live_row = checklist[checklist["check_id"] == "LIVE_READINESS_REVIEWED"].iloc[0]
    assert live_row["status"] == "WARN"
    assert not bool(live_row["critical"])


def test_release_checklist_blocks_when_live_required(tmp_path: Path):
    write_release_inputs(tmp_path, live="BLOCKED")
    checklist = build_release_checklist_dataframe(config(tmp_path, require_live=True))
    summary = build_release_summary_dataframe(checklist, config(tmp_path, require_live=True))
    assert summary.iloc[0]["release_gate_status"] == "BLOCKED"
    live_row = checklist[checklist["check_id"] == "LIVE_READINESS_REVIEWED"].iloc[0]
    assert live_row["status"] == "FAIL"
    assert bool(live_row["critical"])


def test_release_checklist_blocks_on_final_verdict_fail(tmp_path: Path):
    write_release_inputs(tmp_path, final="FAIL")
    checklist = build_release_checklist_dataframe(config(tmp_path))
    summary = build_release_summary_dataframe(checklist, config(tmp_path))
    assert summary.iloc[0]["release_gate_status"] == "BLOCKED"
    verdict_row = checklist[checklist["check_id"] == "FINAL_VERDICT_PASS"].iloc[0]
    assert verdict_row["status"] == "FAIL"


def test_render_markdown_report(tmp_path: Path):
    write_release_inputs(tmp_path)
    cfg = config(tmp_path)
    checklist = build_release_checklist_dataframe(cfg)
    summary = build_release_summary_dataframe(checklist, cfg)
    md = render_markdown_report(checklist, summary)
    assert "# Release Checklist" in md
    assert "Release gate status" in md
    assert "Final research verdict" in md
