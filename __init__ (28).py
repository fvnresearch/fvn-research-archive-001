from __future__ import annotations

import argparse
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from fvn_dfm.operations.live_data_readiness import (
    LiveDataReadinessConfig,
    default_config as default_readiness_config,
    run_live_data_readiness,
)
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


LIVE_PIPELINE_EXECUTION_VERSION = "LIVE_PIPELINE_EXECUTOR_V0"


PIPELINE_STAGE_COMMANDS: dict[str, list[str]] = {
    "raw-sec": [
        "python scripts/01_download_raw_data.py --source sec-submissions",
        "python scripts/01_download_raw_data.py --source sec-complete-submissions",
    ],
    "source-tables": [
        "python scripts/02_build_source_tables.py --source sec-filing-events",
        "python scripts/03_build_point_in_time_tables.py --layer filing-availability",
        "python scripts/02_build_source_tables.py --source sec-primary-documents",
    ],
    "text": [
        "python scripts/04_extract_text.py --layer filing-text-raw",
        "python scripts/04_extract_text.py --layer filing-section-text",
        "python scripts/06_build_features.py --layer text-features-asof",
    ],
    "xbrl": [
        "python scripts/01_download_raw_data.py --source sec-fsds --years 2009-2025",
        "python scripts/05_extract_xbrl_facts.py --source sec-fsds",
        "python scripts/05_extract_xbrl_facts.py --source accounting-fact-selected",
    ],
    "features": [
        "python scripts/06_build_features.py --layer fundamental-features-asof",
        "python scripts/06_build_features.py --layer fundamental-delta-features-asof",
        "python scripts/06_build_features.py --layer fundamental-composite-features-asof",
        "python scripts/06_build_features.py --layer mismatch-features-asof",
        "python scripts/07_build_model_matrix.py --layer model-research-panel",
    ],
    "targets": [
        "python scripts/08_build_targets.py --layer price-return-source --raw-price-path data/raw/prices/adjusted_prices.csv",
        "python scripts/08_build_targets.py --layer return-targets-asof",
    ],
    "modeling": [
        "python scripts/07_build_model_matrix.py --layer model-dataset-v0",
        "python scripts/07_build_model_matrix.py --layer model-dataset-with-splits",
        "python scripts/09_train_models.py --layer baseline-models-v0",
        "python scripts/10_evaluate_models.py --layer model-selection-report-v0",
    ],
    "portfolio": [
        "python scripts/11_build_portfolio.py --layer long-short-decile-v0",
        "python scripts/11_build_portfolio.py --layer portfolio-performance-report-v0",
    ],
    "reports": [
        "python scripts/10_evaluate_models.py --layer ablation-study-v0",
        "python scripts/12_generate_reports.py --layer final-research-verdict-v0",
        "python scripts/12_generate_reports.py --layer reproducibility-pack-v0",
    ],
}

PIPELINE_STAGE_COMMANDS["full-live"] = [
    command
    for stage in ["raw-sec", "source-tables", "text", "xbrl", "features", "targets", "modeling", "portfolio", "reports"]
    for command in PIPELINE_STAGE_COMMANDS[stage]
]


@dataclass(frozen=True)
class LivePipelineExecutionConfig:
    repo_root: Path
    stages: tuple[str, ...]
    execution_log_csv_path: Path
    execution_summary_csv_path: Path
    markdown_report_path: Path
    refresh_readiness: bool = True
    override_readiness: bool = False
    dry_run: bool = False
    stop_on_failure: bool = True
    readiness_config: LiveDataReadinessConfig | None = None
    executor_version: str = LIVE_PIPELINE_EXECUTION_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_csv_or_empty(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _shell_join(args: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in args)


def _commands_for_stages(stages: tuple[str, ...]) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for stage in stages:
        if stage not in PIPELINE_STAGE_COMMANDS:
            raise ValueError(f"Unknown live pipeline stage: {stage}")
        for index, command in enumerate(PIPELINE_STAGE_COMMANDS[stage], start=1):
            rows.append((stage, index, command))
    return rows


def _readiness_summary_value(readiness_summary: pd.DataFrame, column: str) -> Any:
    if readiness_summary.empty or column not in readiness_summary.columns:
        return ""
    return readiness_summary.iloc[0].get(column, "")


def _build_readiness_evidence(config: LivePipelineExecutionConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    readiness_config = config.readiness_config or default_readiness_config(config.repo_root)

    if config.refresh_readiness:
        summary = run_live_data_readiness(readiness_config)
        report = _read_csv_or_empty(readiness_config.readiness_output_csv_path)
        return summary, report

    summary = _read_csv_or_empty(readiness_config.summary_output_csv_path)
    report = _read_csv_or_empty(readiness_config.readiness_output_csv_path)
    if summary.empty:
        summary = run_live_data_readiness(readiness_config)
        report = _read_csv_or_empty(readiness_config.readiness_output_csv_path)
    return summary, report


def _make_log_row(
    *,
    execution_id: str,
    stage: str,
    stage_command_index: int,
    command: str,
    status: str,
    readiness_status: str,
    override_readiness: bool,
    dry_run: bool,
    start: str,
    end: str,
    elapsed_seconds: float,
    return_code: int | None,
    stdout_tail: str,
    stderr_tail: str,
    notes: str,
    config: LivePipelineExecutionConfig,
) -> dict[str, Any]:
    return {
        "execution_id": execution_id,
        "stage": stage,
        "stage_command_index": stage_command_index,
        "command": command,
        "status": status,
        "readiness_status": readiness_status,
        "override_readiness": override_readiness,
        "dry_run": dry_run,
        "started_at_utc": start,
        "finished_at_utc": end,
        "elapsed_seconds": round(elapsed_seconds, 6),
        "return_code": return_code,
        "stdout_tail": stdout_tail[-1000:] if stdout_tail else "",
        "stderr_tail": stderr_tail[-1000:] if stderr_tail else "",
        "notes": notes,
        "executor_version": config.executor_version,
    }


def _execute_command(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        shlex.split(command),
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def build_execution_summary(log_df: pd.DataFrame, readiness_summary: pd.DataFrame, config: LivePipelineExecutionConfig) -> pd.DataFrame:
    status = "NO_COMMANDS"
    if not log_df.empty:
        if (log_df["status"] == "failed").any():
            status = "FAILED"
        elif (log_df["status"] == "blocked").any():
            status = "BLOCKED"
        elif (log_df["status"] == "dry_run").all():
            status = "DRY_RUN"
        else:
            status = "SUCCESS"

    return pd.DataFrame(
        [
            {
                "live_pipeline_execution_status": status,
                "commands": len(log_df),
                "executed_commands": int((log_df["status"] == "success").sum()) if not log_df.empty else 0,
                "blocked_commands": int((log_df["status"] == "blocked").sum()) if not log_df.empty else 0,
                "failed_commands": int((log_df["status"] == "failed").sum()) if not log_df.empty else 0,
                "dry_run_commands": int((log_df["status"] == "dry_run").sum()) if not log_df.empty else 0,
                "readiness_status": _readiness_summary_value(readiness_summary, "live_readiness_status"),
                "override_readiness": config.override_readiness,
                "dry_run": config.dry_run,
                "stages": ",".join(config.stages),
                "executed_at_utc": _utc_now(),
                "executor_version": config.executor_version,
            }
        ]
    )


def render_markdown_report(log_df: pd.DataFrame, summary: pd.DataFrame, readiness_summary: pd.DataFrame) -> str:
    status = summary.iloc[0]["live_pipeline_execution_status"] if not summary.empty else "UNKNOWN"
    readiness_status = _readiness_summary_value(readiness_summary, "live_readiness_status")
    lines = [
        "# Live Pipeline Execution Report",
        "",
        f"Version: `{LIVE_PIPELINE_EXECUTION_VERSION}`",
        "",
        f"Execution status: **{status}**",
        "",
        f"Readiness status: **{readiness_status}**",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    if not summary.empty:
        for key, value in summary.iloc[0].items():
            lines.append(f"| {key} | {value} |")

    lines.extend(
        [
            "",
            "## Command log",
            "",
            "| Stage | # | Status | Command | Return code |",
            "|---|---:|---:|---|---:|",
        ]
    )
    if not log_df.empty:
        for _, row in log_df.iterrows():
            lines.append(
                "| "
                + f"{row.get('stage', '')} | "
                + f"{row.get('stage_command_index', '')} | "
                + f"{row.get('status', '')} | "
                + f"`{row.get('command', '')}` | "
                + f"{row.get('return_code', '')} |"
            )

    lines.extend(
        [
            "",
            "## Execution rule",
            "",
            "Commands execute only when live readiness is `READY`, unless `--override-readiness` is explicitly supplied. Dry-runs record the planned command sequence without executing commands.",
            "",
        ]
    )
    return "\n".join(lines)


def write_execution_outputs(
    log_df: pd.DataFrame,
    summary: pd.DataFrame,
    readiness_summary: pd.DataFrame,
    *,
    config: LivePipelineExecutionConfig,
) -> None:
    config.execution_log_csv_path.parent.mkdir(parents=True, exist_ok=True)
    log_df.to_csv(config.execution_log_csv_path, index=False)
    config.execution_summary_csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(config.execution_summary_csv_path, index=False)
    config.markdown_report_path.parent.mkdir(parents=True, exist_ok=True)
    config.markdown_report_path.write_text(render_markdown_report(log_df, summary, readiness_summary), encoding="utf-8")


def run_live_pipeline(config: LivePipelineExecutionConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.live_pipeline_executor",
        root() / "logs/pipeline/live_pipeline_executor.log",
    )
    logger.info("Running live pipeline wrapper for stages: %s", ",".join(config.stages))

    readiness_summary, readiness_report = _build_readiness_evidence(config)
    readiness_status = str(_readiness_summary_value(readiness_summary, "live_readiness_status") or "BLOCKED")
    allow_execute = readiness_status == "READY" or config.override_readiness
    execution_id = f"LIVE_EXEC_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    log_rows: list[dict[str, Any]] = []
    commands = _commands_for_stages(config.stages)

    for stage, index, command in commands:
        start = _utc_now()
        t0 = perf_counter()

        if not allow_execute:
            end = _utc_now()
            log_rows.append(
                _make_log_row(
                    execution_id=execution_id,
                    stage=stage,
                    stage_command_index=index,
                    command=command,
                    status="blocked",
                    readiness_status=readiness_status,
                    override_readiness=config.override_readiness,
                    dry_run=config.dry_run,
                    start=start,
                    end=end,
                    elapsed_seconds=perf_counter() - t0,
                    return_code=None,
                    stdout_tail="",
                    stderr_tail="",
                    notes="Blocked because live readiness is not READY and no override was provided.",
                    config=config,
                )
            )
            continue

        if config.dry_run:
            end = _utc_now()
            log_rows.append(
                _make_log_row(
                    execution_id=execution_id,
                    stage=stage,
                    stage_command_index=index,
                    command=command,
                    status="dry_run",
                    readiness_status=readiness_status,
                    override_readiness=config.override_readiness,
                    dry_run=config.dry_run,
                    start=start,
                    end=end,
                    elapsed_seconds=perf_counter() - t0,
                    return_code=0,
                    stdout_tail="",
                    stderr_tail="",
                    notes="Dry-run only; command not executed.",
                    config=config,
                )
            )
            continue

        result = _execute_command(command, config.repo_root)
        end = _utc_now()
        status = "success" if result.returncode == 0 else "failed"
        log_rows.append(
            _make_log_row(
                execution_id=execution_id,
                stage=stage,
                stage_command_index=index,
                command=command,
                status=status,
                readiness_status=readiness_status,
                override_readiness=config.override_readiness,
                dry_run=config.dry_run,
                start=start,
                end=end,
                elapsed_seconds=perf_counter() - t0,
                return_code=result.returncode,
                stdout_tail=result.stdout,
                stderr_tail=result.stderr,
                notes="" if status == "success" else "Command returned non-zero exit code.",
                config=config,
            )
        )

        if status == "failed" and config.stop_on_failure:
            break

    log_df = pd.DataFrame(log_rows)
    summary = build_execution_summary(log_df, readiness_summary, config)
    write_execution_outputs(log_df, summary, readiness_summary, config=config)

    logger.info("Live pipeline execution status: %s", summary.iloc[0]["live_pipeline_execution_status"])
    return summary


def default_config(
    *,
    stages: tuple[str, ...],
    repo_root: Path | None = None,
    override_readiness: bool = False,
    dry_run: bool = False,
    refresh_readiness: bool = True,
    stop_on_failure: bool = True,
) -> LivePipelineExecutionConfig:
    r = repo_root or root()
    return LivePipelineExecutionConfig(
        repo_root=r,
        stages=stages,
        execution_log_csv_path=r / "outputs/logs/live_pipeline_execution_log.csv",
        execution_summary_csv_path=r / "outputs/logs/live_pipeline_execution_summary.csv",
        markdown_report_path=r / "outputs/reports/live_pipeline_execution_report.md",
        refresh_readiness=refresh_readiness,
        override_readiness=override_readiness,
        dry_run=dry_run,
        stop_on_failure=stop_on_failure,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run live-data pipeline stages behind readiness gate.")
    parser.add_argument(
        "--stage",
        action="append",
        choices=sorted(PIPELINE_STAGE_COMMANDS.keys()),
        help="Stage to run. Can be supplied multiple times. Defaults to full-live.",
    )
    parser.add_argument("--override-readiness", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-refresh-readiness", action="store_true")
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--execution-log-csv-path", default="outputs/logs/live_pipeline_execution_log.csv")
    parser.add_argument("--execution-summary-csv-path", default="outputs/logs/live_pipeline_execution_summary.csv")
    parser.add_argument("--markdown-report-path", default="outputs/reports/live_pipeline_execution_report.md")
    parser.add_argument("--fail-on-blocked", action="store_true")
    args = parser.parse_args()

    stages = tuple(args.stage) if args.stage else ("full-live",)
    r = root()
    config = LivePipelineExecutionConfig(
        repo_root=r,
        stages=stages,
        execution_log_csv_path=r / args.execution_log_csv_path,
        execution_summary_csv_path=r / args.execution_summary_csv_path,
        markdown_report_path=r / args.markdown_report_path,
        refresh_readiness=not args.no_refresh_readiness,
        override_readiness=args.override_readiness,
        dry_run=args.dry_run,
        stop_on_failure=not args.continue_on_failure,
    )
    summary = run_live_pipeline(config)
    status = summary.iloc[0]["live_pipeline_execution_status"]
    if args.fail_on_blocked and status == "BLOCKED":
        raise SystemExit(2)
    if status == "FAILED":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
