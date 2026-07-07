from pathlib import Path

import pandas as pd

from fvn_dfm.operations.live_data_readiness import LiveDataReadinessConfig, run_live_data_readiness


def test_run_live_data_readiness_outputs(tmp_path: Path):
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

    cfg = LiveDataReadinessConfig(
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
    summary = run_live_data_readiness(cfg)

    assert summary.iloc[0]["live_readiness_status"] == "READY"
    assert (tmp_path / "data/processed/reports/live_data_readiness_report.csv").exists()
    assert (tmp_path / "data/processed/reports/live_data_readiness_summary.csv").exists()
    assert (tmp_path / "outputs/reports/live_data_readiness_report.md").exists()
    assert (tmp_path / "outputs/diagnostics/live_data_readiness_diagnostics.csv").exists()
