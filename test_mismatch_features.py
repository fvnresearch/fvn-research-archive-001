from pathlib import Path

import pandas as pd

from fvn_dfm.operations.live_data_readiness import (
    LiveDataReadinessConfig,
    build_readiness_dataframe,
    build_readiness_summary,
    check_sec_user_agent,
    render_markdown_report,
)


def make_config(tmp_path: Path, *, user_agent: str = "FVN Research test@fvn-research.org", price: bool = True, lm: bool = True, fsds: bool = True) -> LiveDataReadinessConfig:
    (tmp_path / "configs").mkdir(parents=True, exist_ok=True)
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
    - volume
""",
        encoding="utf-8",
    )
    if price:
        (tmp_path / "data/raw/prices").mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {"date": "2023-01-03", "ticker": "ABC", "sector": "Tech", "adjusted_close": 10.0, "volume": 1000}
            ]
        ).to_csv(tmp_path / "data/raw/prices/adjusted_prices.csv", index=False)
    if lm:
        (tmp_path / "data/raw/dictionaries/loughran_mcdonald").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data/raw/dictionaries/loughran_mcdonald/lm.csv").write_text("word,negative\nbad,1\n", encoding="utf-8")
    if fsds:
        (tmp_path / "data/raw/sec/financial_statement_data_sets").mkdir(parents=True, exist_ok=True)
        (tmp_path / "data/raw/sec/financial_statement_data_sets/2023q1.zip").write_text("stub", encoding="utf-8")

    (tmp_path / "data/raw/sec/submissions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "data/raw/sec/primary_documents").mkdir(parents=True, exist_ok=True)

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


def test_sec_user_agent_placeholder_blocks(tmp_path: Path):
    cfg = make_config(tmp_path, user_agent="FVN Research contact_email_to_be_set")
    checks = pd.DataFrame(check_sec_user_agent(cfg))
    failed = checks[checks["check_id"] == "SEC_USER_AGENT_NOT_PLACEHOLDER"].iloc[0]
    assert failed["status"] == "FAIL"
    assert failed["blocker"] is True or failed["blocker"] == True


def test_build_readiness_ready(tmp_path: Path):
    cfg = make_config(tmp_path)
    readiness = build_readiness_dataframe(cfg)
    summary = build_readiness_summary(readiness, cfg)
    assert summary.iloc[0]["live_readiness_status"] == "READY"
    assert readiness["status"].eq("PASS").all()


def test_missing_price_blocks(tmp_path: Path):
    cfg = make_config(tmp_path, price=False)
    readiness = build_readiness_dataframe(cfg)
    summary = build_readiness_summary(readiness, cfg)
    assert summary.iloc[0]["live_readiness_status"] == "BLOCKED"
    assert "PRICE_RAW_FILE_AVAILABLE" in set(readiness[readiness["status"] == "FAIL"]["check_id"])


def test_render_markdown_report(tmp_path: Path):
    cfg = make_config(tmp_path)
    readiness = build_readiness_dataframe(cfg)
    summary = build_readiness_summary(readiness, cfg)
    md = render_markdown_report(readiness, summary)
    assert "# Live Data Readiness Report" in md
    assert "Live readiness status" in md
    assert "SEC User-Agent" in md
