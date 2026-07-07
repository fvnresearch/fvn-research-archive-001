from pathlib import Path

import pandas as pd

from fvn_dfm.operations.live_data_readiness import LiveDataReadinessConfig
from fvn_dfm.operations.live_pipeline_executor import LivePipelineExecutionConfig, run_live_pipeline


def test_live_pipeline_executor_writes_logs(tmp_path: Path):
    (tmp_path / "configs").mkdir(parents=True)
    (tmp_path / "configs/01_data_sources.yaml").write_text(
        """
sec:
  request_policy:
    user_agent: "FVN Research live@fvn-research.org"
price_data:
  required_fields:
    - date
    - ticker
    - adjusted_close
""",
        encoding="utf-8",
    )
    (tmp_path / "data/raw/prices").mkdir(parents=True)
    pd.DataFrame([{"date": "2023-01-03", "ticker": "ABC", "sector": "Tech", "adjusted_close": 10.0}]).to_csv(
        tmp_path / "data/raw/prices/adjusted_prices.csv", index=False
    )
    (tmp_path / "data/raw/dictionaries/loughran_mcdonald").mkdir(parents=True)
    (tmp_path / "data/raw/dictionaries/loughran_mcdonald/lm.csv").write_text("word,negative\nbad,1\n", encoding="utf-8")
    (tmp_path / "data/raw/sec/financial_statement_data_sets").mkdir(parents=True)
    (tmp_path / "data/raw/sec/financial_statement_data_sets/2023q1.zip").write_text("stub", encoding="utf-8")
    (tmp_path / "data/raw/sec/submissions").mkdir(parents=True)
    (tmp_path / "data/raw/sec/primary_documents").mkdir(parents=True)

    readiness = LiveDataReadinessConfig(
        repo_root=tmp_path,
        sec_config_path=tmp_path / "configs/01_data_sources.yaml",
        readiness_output_table_path=tmp_path / "data/processed/reports/live_data_readiness_report.parquet",
        readiness_output_csv_path=tmp_path / "data/processed/reports/live_data_readiness_report.csv",
        summary_output_csv_path=tmp_path / "data/processed/reports/live_data_readiness_summary.csv",
        markdown_report_path=tmp_path / "outputs/reports/live_data_readiness_report.md",
        diagnostics_path=tmp_path / "outputs/diagnostics/live_data_readiness_diagnostics.csv",
        raw_price_path=tmp_path / "data/raw/prices/adjusted_prices.csv",
        lm_dictionary_dir=tmp_path / "data/raw/dictionaries/loughran_mcdonald",
        fsds_raw_dir=tmp_path / "data/raw/sec/financial_statement_data_sets",
        submissions_raw_dir=tmp_path / "data/raw/sec/submissions",
        primary_documents_raw_dir=tmp_path / "data/raw/sec/primary_documents",
    )
    cfg = LivePipelineExecutionConfig(
        repo_root=tmp_path,
        stages=("targets",),
        execution_log_csv_path=tmp_path / "outputs/logs/live_pipeline_execution_log.csv",
        execution_summary_csv_path=tmp_path / "outputs/logs/live_pipeline_execution_summary.csv",
        markdown_report_path=tmp_path / "outputs/reports/live_pipeline_execution_report.md",
        refresh_readiness=True,
        override_readiness=False,
        dry_run=True,
        readiness_config=readiness,
    )
    summary = run_live_pipeline(cfg)

    assert summary.iloc[0]["live_pipeline_execution_status"] == "DRY_RUN"
    assert cfg.execution_log_csv_path.exists()
    assert cfg.execution_summary_csv_path.exists()
    assert cfg.markdown_report_path.exists()
    log = pd.read_csv(cfg.execution_log_csv_path)
    assert len(log) == 2
    assert log["status"].eq("dry_run").all()
    assert log["readiness_status"].eq("READY").all()
