from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.data_lineage_graph import DataLineageGraphConfig, build_data_lineage_graph


def test_build_data_lineage_graph_outputs(tmp_path: Path):
    (tmp_path / "configs").mkdir(parents=True)
    (tmp_path / "configs/01_data_sources.yaml").write_text("sec:\n", encoding="utf-8")
    (tmp_path / "data/processed/reports").mkdir(parents=True)

    config = DataLineageGraphConfig(
        repo_root=tmp_path,
        nodes_output_table_path=tmp_path / "data/processed/reports/data_lineage_nodes.parquet",
        nodes_output_csv_path=tmp_path / "data/processed/reports/data_lineage_nodes.csv",
        edges_output_table_path=tmp_path / "data/processed/reports/data_lineage_edges.parquet",
        edges_output_csv_path=tmp_path / "data/processed/reports/data_lineage_edges.csv",
        markdown_report_path=tmp_path / "outputs/reports/data_lineage_map.md",
        diagnostics_path=tmp_path / "outputs/diagnostics/data_lineage_graph_diagnostics.csv",
    )
    nodes, edges = build_data_lineage_graph(config)

    assert not nodes.empty
    assert not edges.empty
    assert config.nodes_output_csv_path.exists()
    assert config.edges_output_csv_path.exists()
    assert config.markdown_report_path.exists()
    assert config.diagnostics_path.exists()

    node_df = pd.read_csv(config.nodes_output_csv_path)
    edge_df = pd.read_csv(config.edges_output_csv_path)
    assert len(node_df) == len(nodes)
    assert len(edge_df) == len(edges)
    assert {"source_node_id", "target_node_id", "edge_type"}.issubset(edge_df.columns)
