from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.release_checklist import ReleaseChecklistConfig, build_release_checklist


def test_build_release_checklist_outputs(tmp_path: Path):
    (tmp_path / "data/processed/reports").mkdir(parents=True)
    (tmp_path / "outputs/smoke/e2e_smoke_v0/outputs/smoke").mkdir(parents=True)
    (tmp_path / "outputs/diagnostics").mkdir(parents=True)
    (tmp_path / "outputs/audit").mkdir(parents=True)

    pd.DataFrame([{"final_verdict": "PASS"}]).to_csv(tmp_path / "data/processed/reports/final_research_verdict.csv", index=False)
    pd.DataFrame([{"status": "PASS", "steps": 14, "artifact_checks": 20}]).to_csv(tmp_path / "outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_summary.csv", index=False)
    pd.DataFrame([{"schema_contract_status": "PASS", "contracts": 24, "blocking_failures": 0}]).to_csv(tmp_path / "data/processed/reports/schema_contract_summary.csv", index=False)
    pd.DataFrame([{"node_id": "n1", "node_type": "command"}]).to_csv(tmp_path / "data/processed/reports/data_lineage_nodes.csv", index=False)
    pd.DataFrame([{"edge_id": "e1", "source_node_id": "n1", "target_node_id": "n2", "edge_type": "produces"}]).to_csv(tmp_path / "data/processed/reports/data_lineage_edges.csv", index=False)
    pd.DataFrame([{"diagnostic": "command_nodes", "value": 1}]).to_csv(tmp_path / "outputs/diagnostics/data_lineage_graph_diagnostics.csv", index=False)
    (tmp_path / "outputs/audit/reproducibility_pack.zip").write_text("zip-stub", encoding="utf-8")
    pd.DataFrame([{"diagnostic": "manifest_rows", "value": 100}]).to_csv(tmp_path / "outputs/diagnostics/reproducibility_pack_diagnostics.csv", index=False)
    pd.DataFrame([{"live_readiness_status": "READY", "blocking_failures": 0}]).to_csv(tmp_path / "data/processed/reports/live_data_readiness_summary.csv", index=False)

    cfg = ReleaseChecklistConfig(
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
    )

    summary = build_release_checklist(cfg)

    assert summary.iloc[0]["release_gate_status"] == "PASS"
    assert cfg.release_checklist_output_csv_path.exists()
    assert cfg.release_summary_output_csv_path.exists()
    assert cfg.markdown_report_path.exists()
    assert cfg.diagnostics_path.exists()
    checklist = pd.read_csv(cfg.release_checklist_output_csv_path)
    assert "FINAL_VERDICT_PASS" in set(checklist["check_id"])
    assert checklist["status"].eq("PASS").all()
