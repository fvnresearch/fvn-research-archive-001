from pathlib import Path

import pandas as pd

from fvn_dfm.operations.live_data_readiness import LiveDataReadinessConfig
from fvn_dfm.operations.live_pipeline_executor import (
    LivePipelineExecutionConfig,
    _commands_for_stages,
    build_execution_summary,
    run_live_pipeline,
)


def readiness_config(tmp_path: Path, *, ready: bool) -> LiveDataReadinessConfig:
    (tmp_path / "configs").mkdir(parents=True, exist_ok=True)
    user_agent = "FVN Research live@fvn-research.org" if ready else "FVN Research contact_email_to_be_set"
    (tmp_path / "configs/01_data_sources.yaml").write_text(
        f"""
sec:
  request_policy:
    user_agent: "{user_agent}"
price_data:
  required_fields:
    - date
    - ticker
    - adjusted_close
""",
        encoding="utf-8",
    )
    if ready:
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

    return LiveDataReadinessConfig(
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


def execution_config(tmp_path: Path, *, ready: bool, dry_run: bool = True, override: bool = False) -> LivePipelineExecutionConfig:
    return LivePipelineExecutionConfig(
        repo_root=tmp_path,
        stages=("targets",),
        execution_log_csv_path=tmp_path / "outputs/logs/live_pipeline_execution_log.csv",
        execution_summary_csv_path=tmp_path / "outputs/logs/live_pipeline_execution_summary.csv",
        markdown_report_path=tmp_path / "outputs/reports/live_pipeline_execution_report.md",
        refresh_readiness=True,
        override_readiness=override,
        dry_run=dry_run,
        readiness_config=readiness_config(tmp_path, ready=ready),
    )


def test_commands_for_stages():
    commands = _commands_for_stages(("targets",))
    assert len(commands) == 2
    assert commands[0][0] == "targets"
    assert "08_build_targets.py" in commands[0][2]


def test_run_live_pipeline_blocks_when_not_ready(tmp_path: Path):
    cfg = execution_config(tmp_path, ready=False, dry_run=True, override=False)
    summary = run_live_pipeline(cfg)
    assert summary.iloc[0]["live_pipeline_execution_status"] == "BLOCKED"
    log = pd.read_csv(cfg.execution_log_csv_path)
    assert log["status"].eq("blocked").all()
    assert (tmp_path / "outputs/reports/live_pipeline_execution_report.md").exists()


def test_run_live_pipeline_dry_run_when_ready(tmp_path: Path):
    cfg = execution_config(tmp_path, ready=True, dry_run=True, override=False)
    summary = run_live_pipeline(cfg)
    assert summary.iloc[0]["live_pipeline_execution_status"] == "DRY_RUN"
    log = pd.read_csv(cfg.execution_log_csv_path)
    assert log["status"].eq("dry_run").all()
    assert log["readiness_status"].eq("READY").all()


def test_run_live_pipeline_override_allows_dry_run_when_blocked(tmp_path: Path):
    cfg = execution_config(tmp_path, ready=False, dry_run=True, override=True)
    summary = run_live_pipeline(cfg)
    assert summary.iloc[0]["live_pipeline_execution_status"] == "DRY_RUN"
    log = pd.read_csv(cfg.execution_log_csv_path)
    assert log["override_readiness"].astype(bool).all()


def test_build_execution_summary_failed():
    log = pd.DataFrame([{"status": "failed"}])
    readiness = pd.DataFrame([{"live_readiness_status": "READY"}])
    cfg = LivePipelineExecutionConfig(
        repo_root=Path("."),
        stages=("targets",),
        execution_log_csv_path=Path("log.csv"),
        execution_summary_csv_path=Path("summary.csv"),
        markdown_report_path=Path("report.md"),
    )
    summary = build_execution_summary(log, readiness, cfg)
    assert summary.iloc[0]["live_pipeline_execution_status"] == "FAILED"
