from pathlib import Path

from fvn_dfm.reporting.data_lineage_graph import (
    DataLineageGraphConfig,
    LINEAGE_STEPS,
    build_lineage_diagnostics,
    build_lineage_nodes_and_edges,
    render_markdown_lineage_map,
)


def config(tmp_path: Path) -> DataLineageGraphConfig:
    return DataLineageGraphConfig(
        repo_root=tmp_path,
        nodes_output_table_path=tmp_path / "data/processed/reports/data_lineage_nodes.parquet",
        nodes_output_csv_path=tmp_path / "data/processed/reports/data_lineage_nodes.csv",
        edges_output_table_path=tmp_path / "data/processed/reports/data_lineage_edges.parquet",
        edges_output_csv_path=tmp_path / "data/processed/reports/data_lineage_edges.csv",
        markdown_report_path=tmp_path / "outputs/reports/data_lineage_map.md",
        diagnostics_path=tmp_path / "outputs/diagnostics/data_lineage_graph_diagnostics.csv",
    )


def test_lineage_steps_are_ordered():
    orders = [step.step_order for step in LINEAGE_STEPS]
    assert orders == sorted(orders)
    assert len(orders) >= 25


def test_build_lineage_nodes_and_edges(tmp_path: Path):
    (tmp_path / "configs").mkdir(parents=True)
    (tmp_path / "configs/01_data_sources.yaml").write_text("sec:\n", encoding="utf-8")
    (tmp_path / "data/raw/prices").mkdir(parents=True)
    (tmp_path / "data/raw/prices/adjusted_prices.csv").write_text("date,ticker,adjusted_close\n", encoding="utf-8")

    nodes, edges = build_lineage_nodes_and_edges(config(tmp_path))
    assert not nodes.empty
    assert not edges.empty
    assert "command" in set(nodes["node_type"])
    assert "consumes" in set(edges["edge_type"])
    assert "produces" in set(edges["edge_type"])
    assert "runs_before" in set(edges["edge_type"])
    assert "data/raw/prices/adjusted_prices.csv" in set(nodes["artifact_path"])


def test_build_lineage_diagnostics(tmp_path: Path):
    nodes, edges = build_lineage_nodes_and_edges(config(tmp_path))
    diagnostics = build_lineage_diagnostics(nodes, edges)
    assert "node_rows" in set(diagnostics["diagnostic"])
    assert "edge_rows" in set(diagnostics["diagnostic"])
    assert "command_nodes" in set(diagnostics["diagnostic"])


def test_render_markdown_lineage_map(tmp_path: Path):
    nodes, edges = build_lineage_nodes_and_edges(config(tmp_path))
    md = render_markdown_lineage_map(nodes, edges)
    assert "# Data Lineage Map" in md
    assert "Pipeline stages" in md
    assert "Machine-readable outputs" in md
