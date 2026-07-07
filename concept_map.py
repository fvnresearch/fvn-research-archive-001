from __future__ import annotations

import argparse
import hashlib
import json
import platform
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.data_ingestion.sec_financial_statement_datasets import safe_write_table
from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


REPRODUCIBILITY_PACK_VERSION = "REPRODUCIBILITY_PACK_V0"

DEFAULT_PIPELINE_STEPS: tuple[tuple[str, str, str], ...] = (
    ("00", "setup-checks", "python scripts/00_setup_project.py --check-configs --audit-skeleton"),
    ("01", "download-sec-submissions", "python scripts/01_download_raw_data.py --source sec-submissions"),
    ("02", "download-sec-complete-submissions", "python scripts/01_download_raw_data.py --source sec-complete-submissions"),
    ("03", "build-filing-events", "python scripts/02_build_source_tables.py --source sec-filing-events"),
    ("04", "build-filing-availability", "python scripts/03_build_point_in_time_tables.py --layer filing-availability"),
    ("05", "discover-primary-documents", "python scripts/02_build_source_tables.py --source sec-primary-documents"),
    ("06", "extract-text", "python scripts/04_extract_text.py --layer filing-text-raw"),
    ("07", "extract-sections", "python scripts/04_extract_text.py --layer filing-section-text"),
    ("08", "download-fsds", "python scripts/01_download_raw_data.py --source sec-fsds --years 2009-2025"),
    ("09", "extract-xbrl", "python scripts/05_extract_xbrl_facts.py --source sec-fsds"),
    ("10", "select-accounting-facts", "python scripts/05_extract_xbrl_facts.py --source accounting-fact-selected"),
    ("11", "build-text-features", "python scripts/06_build_features.py --layer text-features-asof"),
    ("12", "build-fundamental-features", "python scripts/06_build_features.py --layer fundamental-features-asof"),
    ("13", "build-fundamental-deltas", "python scripts/06_build_features.py --layer fundamental-delta-features-asof"),
    ("14", "build-fundamental-composites", "python scripts/06_build_features.py --layer fundamental-composite-features-asof"),
    ("15", "build-mismatch-features", "python scripts/06_build_features.py --layer mismatch-features-asof"),
    ("16", "build-research-panel", "python scripts/07_build_model_matrix.py --layer model-research-panel"),
    ("17", "build-price-return-source", "python scripts/08_build_targets.py --layer price-return-source --raw-price-path data/raw/prices/adjusted_prices.csv"),
    ("18", "build-return-targets", "python scripts/08_build_targets.py --layer return-targets-asof"),
    ("19", "build-model-dataset", "python scripts/07_build_model_matrix.py --layer model-dataset-v0"),
    ("20", "build-walk-forward-splits", "python scripts/07_build_model_matrix.py --layer model-dataset-with-splits"),
    ("21", "train-baseline-models", "python scripts/09_train_models.py --layer baseline-models-v0"),
    ("22", "build-model-selection-report", "python scripts/10_evaluate_models.py --layer model-selection-report-v0"),
    ("23", "build-long-short-decile", "python scripts/11_build_portfolio.py --layer long-short-decile-v0"),
    ("24", "build-portfolio-performance", "python scripts/11_build_portfolio.py --layer portfolio-performance-report-v0"),
    ("25", "build-ablation-study", "python scripts/10_evaluate_models.py --layer ablation-study-v0"),
    ("26", "build-final-verdict", "python scripts/12_generate_reports.py --layer final-research-verdict-v0"),
    ("27", "build-reproducibility-pack", "python scripts/12_generate_reports.py --layer reproducibility-pack-v0"),
)


@dataclass(frozen=True)
class ReproducibilityPackConfig:
    output_dir: Path
    bundle_zip_path: Path
    diagnostics_path: Path
    manifest_output_table_path: Path
    manifest_output_csv_path: Path
    include_data: bool = False
    pack_version: str = REPRODUCIBILITY_PACK_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def _should_skip(path: Path, repo_root: Path, include_data: bool, output_dir: Path, bundle_zip_path: Path) -> bool:
    rel = path.relative_to(repo_root)
    parts = rel.parts
    if not path.is_file():
        return True
    if path == bundle_zip_path:
        return True
    if output_dir in path.parents or path == output_dir:
        return True
    if "__pycache__" in parts:
        return True
    if ".pytest_cache" in parts:
        return True
    if ".git" in parts:
        return True
    if path.suffix in {".pyc", ".pyo"}:
        return True
    if not include_data and len(parts) > 0 and parts[0] == "data":
        # Keep lightweight data documentation, but exclude generated/raw data by default.
        if not (len(parts) >= 2 and parts[-1].upper() == "README.MD"):
            return True
    if path.suffix == ".zip" and parts[0] != "outputs":
        return True
    return False


def build_file_manifest(repo_root: Path, config: ReproducibilityPackConfig) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for path in sorted(repo_root.rglob("*")):
        if _should_skip(path, repo_root, config.include_data, config.output_dir, config.bundle_zip_path):
            continue
        rel = path.relative_to(repo_root).as_posix()
        stat = path.stat()
        rows.append(
            {
                "relative_path": rel,
                "file_name": path.name,
                "suffix": path.suffix,
                "top_level_dir": rel.split("/")[0],
                "size_bytes": int(stat.st_size),
                "modified_time_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "sha256": _sha256_file(path),
                "pack_version": config.pack_version,
            }
        )
    return pd.DataFrame(rows)


def build_config_snapshot(repo_root: Path) -> dict[str, Any]:
    configs: dict[str, Any] = {}
    config_dir = repo_root / "configs"
    for path in sorted(config_dir.glob("*")) if config_dir.exists() else []:
        if path.is_file():
            try:
                configs[path.name] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                configs[path.name] = "<binary-or-non-utf8>"

    pyproject = repo_root / "pyproject.toml"
    requirements = repo_root / "requirements.txt"
    environment = repo_root / "environment.yml"

    return {
        "snapshot_created_at_utc": _utc_now(),
        "python_version": sys_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "pack_version": REPRODUCIBILITY_PACK_VERSION,
        "configs": configs,
        "pyproject_toml": pyproject.read_text(encoding="utf-8") if pyproject.exists() else "",
        "requirements_txt": requirements.read_text(encoding="utf-8") if requirements.exists() else "",
        "environment_yml": environment.read_text(encoding="utf-8") if environment.exists() else "",
    }


def sys_version() -> str:
    import sys
    return sys.version.replace("\n", " ")


def build_report_index(repo_root: Path, manifest: pd.DataFrame) -> pd.DataFrame:
    report_dirs = [repo_root / "outputs/reports", repo_root / "data/processed/reports"]
    rows: list[dict[str, Any]] = []
    for directory in report_dirs:
        if not directory.exists():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(repo_root).as_posix()
            rows.append(
                {
                    "report_path": rel,
                    "report_name": path.name,
                    "report_type": "markdown" if path.suffix.lower() == ".md" else path.suffix.lower().lstrip("."),
                    "size_bytes": path.stat().st_size,
                    "sha256": _sha256_file(path),
                    "pack_version": REPRODUCIBILITY_PACK_VERSION,
                }
            )
    return pd.DataFrame(rows)


def build_pipeline_run_order() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "step_order": order,
                "step_name": name,
                "command": command,
                "pack_version": REPRODUCIBILITY_PACK_VERSION,
            }
            for order, name, command in DEFAULT_PIPELINE_STEPS
        ]
    )


def render_pipeline_run_order_markdown(pipeline: pd.DataFrame) -> str:
    lines = [
        "# Pipeline Run Order",
        "",
        "This is the conservative full pipeline order for reproducing the research archive from public/source inputs through final verdict.",
        "",
        "| Step | Name | Command |",
        "|---:|---|---|",
    ]
    for _, row in pipeline.iterrows():
        lines.append(f"| {row['step_order']} | {row['step_name']} | `{row['command']}` |")
    lines.append("")
    return "\n".join(lines)


def render_bundle_index_markdown(
    manifest: pd.DataFrame,
    report_index: pd.DataFrame,
    pipeline: pd.DataFrame,
    config: ReproducibilityPackConfig,
) -> str:
    lines = [
        "# Reproducibility Pack",
        "",
        f"Version: `{config.pack_version}`",
        "",
        "## Contents",
        "",
        "| Artifact | Description |",
        "|---|---|",
        "| `file_manifest.csv` | Manifest of included repository files with SHA256 checksums. |",
        "| `file_checksums.csv` | Path/checksum table for quick integrity checks. |",
        "| `config_snapshot.json` | Config, environment, and dependency snapshot. |",
        "| `report_index.csv` | Index of generated reports and final evidence artifacts. |",
        "| `pipeline_run_order.csv` | Machine-readable pipeline execution order. |",
        "| `pipeline_run_order.md` | Human-readable pipeline execution order. |",
        "| `reproducibility_pack_diagnostics.csv` | Pack construction diagnostics. |",
        "",
        "## Summary",
        "",
        f"- Included files: {len(manifest)}",
        f"- Indexed reports: {len(report_index)}",
        f"- Pipeline steps: {len(pipeline)}",
        f"- Data files included: {config.include_data}",
        "",
        "## Audit command",
        "",
        "```bash",
        "make build-reproducibility-pack",
        "```",
        "",
    ]
    return "\n".join(lines)


def build_diagnostics(
    manifest: pd.DataFrame,
    report_index: pd.DataFrame,
    pipeline: pd.DataFrame,
    config: ReproducibilityPackConfig,
) -> pd.DataFrame:
    rows = [
        {"diagnostic": "pack_version", "value": config.pack_version},
        {"diagnostic": "manifest_rows", "value": len(manifest)},
        {"diagnostic": "report_index_rows", "value": len(report_index)},
        {"diagnostic": "pipeline_steps", "value": len(pipeline)},
        {"diagnostic": "include_data", "value": config.include_data},
        {"diagnostic": "output_dir", "value": str(config.output_dir)},
        {"diagnostic": "bundle_zip_path", "value": str(config.bundle_zip_path)},
    ]
    if not manifest.empty:
        rows.append({"diagnostic": "total_manifest_size_bytes", "value": int(manifest["size_bytes"].sum())})
        for top, count in manifest["top_level_dir"].value_counts().items():
            rows.append({"diagnostic": f"files_in_{top}", "value": int(count)})
    return pd.DataFrame(rows)


def write_reproducibility_pack_outputs(
    *,
    manifest: pd.DataFrame,
    report_index: pd.DataFrame,
    pipeline: pd.DataFrame,
    config_snapshot: dict[str, Any],
    diagnostics: pd.DataFrame,
    config: ReproducibilityPackConfig,
) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = config.output_dir / "file_manifest.csv"
    checksums_path = config.output_dir / "file_checksums.csv"
    config_snapshot_path = config.output_dir / "config_snapshot.json"
    report_index_path = config.output_dir / "report_index.csv"
    pipeline_csv_path = config.output_dir / "pipeline_run_order.csv"
    pipeline_md_path = config.output_dir / "pipeline_run_order.md"
    diagnostics_pack_path = config.output_dir / "reproducibility_pack_diagnostics.csv"
    index_md_path = config.output_dir / "README.md"

    manifest.to_csv(manifest_path, index=False)
    manifest[["relative_path", "sha256", "size_bytes"]].to_csv(checksums_path, index=False)
    config_snapshot_path.write_text(json.dumps(config_snapshot, indent=2, sort_keys=True), encoding="utf-8")
    report_index.to_csv(report_index_path, index=False)
    pipeline.to_csv(pipeline_csv_path, index=False)
    pipeline_md_path.write_text(render_pipeline_run_order_markdown(pipeline), encoding="utf-8")
    diagnostics.to_csv(diagnostics_pack_path, index=False)
    index_md_path.write_text(render_bundle_index_markdown(manifest, report_index, pipeline, config), encoding="utf-8")

    safe_write_table(manifest, parquet_path=config.manifest_output_table_path, csv_path=config.manifest_output_csv_path)

    config.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(config.diagnostics_path, index=False)

    if config.bundle_zip_path.exists():
        config.bundle_zip_path.unlink()
    config.bundle_zip_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.make_archive(str(config.bundle_zip_path.with_suffix("")), "zip", config.output_dir)


def build_reproducibility_pack(config: ReproducibilityPackConfig) -> pd.DataFrame:
    logger = get_logger(
        "fvn_dfm.reproducibility_pack",
        root() / "logs/pipeline/reproducibility_pack.log",
    )
    logger.info("Building reproducibility pack in %s", config.output_dir)

    repo_root = root()
    manifest = build_file_manifest(repo_root, config)
    report_index = build_report_index(repo_root, manifest)
    pipeline = build_pipeline_run_order()
    config_snapshot = build_config_snapshot(repo_root)
    diagnostics = build_diagnostics(manifest, report_index, pipeline, config)

    write_reproducibility_pack_outputs(
        manifest=manifest,
        report_index=report_index,
        pipeline=pipeline,
        config_snapshot=config_snapshot,
        diagnostics=diagnostics,
        config=config,
    )

    logger.info("Built reproducibility pack with %d manifest rows", len(manifest))
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Build reproducibility pack v0.")
    parser.add_argument("--output-dir", default="outputs/audit/reproducibility_pack")
    parser.add_argument("--bundle-zip-path", default="outputs/audit/reproducibility_pack.zip")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/reproducibility_pack_diagnostics.csv")
    parser.add_argument("--manifest-output-table", default="data/processed/reports/reproducibility_file_manifest.parquet")
    parser.add_argument("--manifest-output-csv", default="data/processed/reports/reproducibility_file_manifest.csv")
    parser.add_argument("--include-data", action="store_true")
    args = parser.parse_args()

    config = ReproducibilityPackConfig(
        output_dir=root() / args.output_dir,
        bundle_zip_path=root() / args.bundle_zip_path,
        diagnostics_path=root() / args.diagnostics_path,
        manifest_output_table_path=root() / args.manifest_output_table,
        manifest_output_csv_path=root() / args.manifest_output_csv,
        include_data=args.include_data,
    )
    build_reproducibility_pack(config)


if __name__ == "__main__":
    main()
