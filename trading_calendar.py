from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from fvn_dfm.utils.logging import get_logger
from fvn_dfm.utils.paths import root


PUBLIC_README_POLISH_VERSION = "PUBLIC_README_POLISH_V0"


@dataclass(frozen=True)
class PublicReadmePolishConfig:
    publication_package_dir: Path
    output_path: Path
    publication_manifest_path: Path
    publication_exclusions_path: Path
    publication_sanitization_path: Path
    release_summary_path: Path
    final_verdict_path: Path
    schema_summary_path: Path
    live_readiness_summary_path: Path
    diagnostics_path: Path
    polish_version: str = PUBLIC_README_POLISH_VERSION


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def _first_value(df: pd.DataFrame, column: str, default: Any = "not available") -> Any:
    if df.empty or column not in df.columns:
        return default
    value = df.iloc[0].get(column, default)
    if pd.isna(value):
        return default
    return value


def _count_section(manifest: pd.DataFrame, section: str) -> int:
    if manifest.empty or "section" not in manifest.columns:
        return 0
    return int((manifest["section"] == section).sum())


def _status_badge(status: Any) -> str:
    clean = str(status or "not available").strip()
    if clean in {"PASS", "READY", "SUCCESS"}:
        return f"`{clean}`"
    if clean in {"PASS_WITH_WARNINGS", "READY_WITH_WARNINGS", "WARN"}:
        return f"`{clean}`"
    if clean in {"FAIL", "BLOCKED"}:
        return f"`{clean}`"
    return f"`{clean}`"


def _manifest_rows(manifest: pd.DataFrame) -> list[str]:
    if manifest.empty:
        return ["| no files indexed | — | — |"]
    grouped = manifest.groupby("section", dropna=False).size().reset_index(name="files")
    lines = []
    for _, row in grouped.sort_values("section").iterrows():
        lines.append(f"| {row['section']} | {int(row['files'])} | included |")
    return lines


def _sanitization_status(sanitization: pd.DataFrame) -> str:
    if sanitization.empty or "status" not in sanitization.columns:
        return "not available"
    failures = int((sanitization["status"] == "FAIL").sum())
    return "PASS" if failures == 0 else "FAIL"


def render_public_landing_readme(
    *,
    manifest: pd.DataFrame,
    exclusions: pd.DataFrame,
    sanitization: pd.DataFrame,
    release_summary: pd.DataFrame,
    final_verdict: pd.DataFrame,
    schema_summary: pd.DataFrame,
    live_readiness: pd.DataFrame,
    version: str = PUBLIC_README_POLISH_VERSION,
) -> str:
    release_status = _first_value(release_summary, "release_gate_status")
    final_status = _first_value(final_verdict, "final_verdict")
    schema_status = _first_value(schema_summary, "schema_contract_status")
    live_status = _first_value(live_readiness, "live_readiness_status")
    sanitation_status = _sanitization_status(sanitization)

    manifest_lines = _manifest_rows(manifest)
    excluded_count = len(exclusions) if not exclusions.empty else 0

    return "\n".join(
        [
            "# FVN Research Archive 001 — Disclosure–Fundamental Mismatch",
            "",
            f"Public README polish: `{version}`",
            "",
            "This package is a sanitized public-facing release of a reproducible quant research archive. It is designed to let a reviewer understand the thesis, inspect the evidence trail, and reproduce the pipeline controls without exposing raw filings, raw prices, intermediate model data, or private runtime logs.",
            "",
            "## Research thesis",
            "",
            "The core hypothesis is that a stock’s future return can contain signal when hard fundamentals and management disclosure tone disagree. The archive tests a Disclosure–Fundamental Mismatch signal built from public SEC filings, public accounting facts, dictionary-based disclosure features, point-in-time as-of controls, walk-forward modeling, and a conservative long-short portfolio evaluation.",
            "",
            "The public package is not a trading recommendation. It is an audit-oriented research artifact: the important claim is whether the evidence chain is reproducible, controlled, and strong enough to pass the repository’s own conservative gates.",
            "",
            "## Current release status",
            "",
            "| Gate | Status | Evidence |",
            "|---|---:|---|",
            f"| Final research verdict | {_status_badge(final_status)} | `data/processed/reports/final_research_verdict.csv` |",
            f"| Release checklist | {_status_badge(release_status)} | `data/processed/reports/release_gate_summary.csv` |",
            f"| Schema contracts | {_status_badge(schema_status)} | `data/processed/reports/schema_contract_summary.csv` |",
            f"| Publication sanitization | {_status_badge(sanitation_status)} | `publication_sanitization_checks.csv` |",
            f"| Live-data readiness | {_status_badge(live_status)} | `data/processed/reports/live_data_readiness_summary.csv` |",
            "",
            "## Pipeline diagram",
            "",
            "```mermaid",
            "flowchart TD",
            "    A[Public SEC filings and FSDS] --> B[Point-in-time filing availability]",
            "    B --> C[Text extraction and section parsing]",
            "    B --> D[Accounting fact selection]",
            "    C --> E[Disclosure text features]",
            "    D --> F[Fundamental features and deltas]",
            "    E --> G[Disclosure-Fundamental Mismatch features]",
            "    F --> G",
            "    G --> H[Model research panel]",
            "    I[Adjusted public prices] --> J[Forward return targets]",
            "    H --> K[Model dataset and walk-forward splits]",
            "    J --> K",
            "    K --> L[Baseline models and model selection]",
            "    L --> M[Long-short decile portfolio]",
            "    M --> N[Performance report]",
            "    K --> O[Ablation study]",
            "    N --> P[Final research verdict]",
            "    O --> P",
            "    P --> Q[Release checklist]",
            "    Q --> R[Sanitized publication package]",
            "```",
            "",
            "## Audit controls included",
            "",
            "The package includes the controls needed to review the research without trusting hidden state:",
            "",
            "- point-in-time as-of design and delay assumptions",
            "- walk-forward train/validation/test split logic",
            "- model selection report with primary-model evidence",
            "- portfolio construction and performance diagnostics",
            "- ablation study against DFM, fundamentals-only, text-only, and naive baselines",
            "- final PASS/FAIL research verdict criteria",
            "- schema contract registry and validation summary",
            "- data lineage node and edge tables",
            "- reproducibility index and pipeline run order",
            "- release checklist and publication sanitization checks",
            "",
            "## Reproduction commands",
            "",
            "From the repository root, the main audit commands are:",
            "",
            "```bash",
            "make run-e2e-smoke",
            "make build-data-lineage-graph",
            "make validate-schema-contracts",
            "make build-reproducibility-pack",
            "make build-release-checklist",
            "make build-publication-package",
            "```",
            "",
            "For live-data execution, the repository intentionally requires an operational gate first:",
            "",
            "```bash",
            "make check-live-readiness",
            "make run-live-pipeline-dry",
            "make run-live-pipeline",
            "```",
            "",
            "The live pipeline wrapper blocks execution unless readiness is `READY`, unless an explicit override is used and logged.",
            "",
            "## Package contents",
            "",
            "| Section | Files | Status |",
            "|---|---:|---|",
            *manifest_lines,
            "",
            f"Requested files excluded or missing: `{excluded_count}`.",
            "",
            "## What is deliberately excluded",
            "",
            "Excluded by design: the public package intentionally excludes raw and private material:",
            "",
            "- raw SEC filing documents",
            "- raw price files",
            "- intermediate source tables",
            "- intermediate feature/model/target/portfolio datasets",
            "- runtime logs",
            "- nested ZIP archives",
            "- private or local execution artifacts",
            "",
            "This is intentional: the public package should be small, reviewable, and safe to share, while the full repository keeps the executable code and contracts needed to rebuild the artifacts.",
            "",
            "## Generated package indexes",
            "",
            "- `publication_manifest.csv`: included package files with SHA256 checksums",
            "- `publication_exclusions.csv`: missing or intentionally excluded requested files",
            "- `publication_sanitization_checks.csv`: public-package sanitization gate results",
            "",
            "## Reading order for reviewers",
            "",
            "A reviewer can follow this order:",
            "",
            "1. `outputs/reports/release_checklist.md`",
            "2. `outputs/reports/final_research_verdict.md`",
            "3. `outputs/reports/portfolio_performance_report.md`",
            "4. `outputs/reports/ablation_study_report.md`",
            "5. `outputs/reports/data_lineage_map.md`",
            "6. `outputs/audit/reproducibility_pack/pipeline_run_order.md`",
            "",
            "## Caveat",
            "",
            "The package is a publication artifact, not a live trading system. Any live-data run must first pass the readiness checker and should be treated as a fresh evidence generation process.",
            "",
            f"Generated at: `{_utc_now()}`",
            "",
        ]
    )


def build_public_readme_diagnostics(readme_text: str, config: PublicReadmePolishConfig) -> pd.DataFrame:
    required_phrases = [
        "Research thesis",
        "Pipeline diagram",
        "Audit controls included",
        "Reproduction commands",
        "What is deliberately excluded",
    ]
    rows = [
        {"diagnostic": "polish_version", "value": config.polish_version},
        {"diagnostic": "output_path", "value": config.output_path.as_posix()},
        {"diagnostic": "readme_length_chars", "value": len(readme_text)},
    ]
    for phrase in required_phrases:
        rows.append({"diagnostic": f"contains_{phrase.lower().replace(' ', '_')}", "value": phrase in readme_text})
    return pd.DataFrame(rows)


def build_public_readme_polish(config: PublicReadmePolishConfig) -> str:
    logger = get_logger(
        "fvn_dfm.public_readme_polish",
        root() / "logs/pipeline/public_readme_polish.log",
    )
    logger.info("Building public README polish at %s", config.output_path)

    manifest = _read_csv(config.publication_manifest_path)
    exclusions = _read_csv(config.publication_exclusions_path)
    sanitization = _read_csv(config.publication_sanitization_path)
    release_summary = _read_csv(config.release_summary_path)
    final_verdict = _read_csv(config.final_verdict_path)
    schema_summary = _read_csv(config.schema_summary_path)
    live_readiness = _read_csv(config.live_readiness_summary_path)

    readme = render_public_landing_readme(
        manifest=manifest,
        exclusions=exclusions,
        sanitization=sanitization,
        release_summary=release_summary,
        final_verdict=final_verdict,
        schema_summary=schema_summary,
        live_readiness=live_readiness,
        version=config.polish_version,
    )

    config.output_path.parent.mkdir(parents=True, exist_ok=True)
    config.output_path.write_text(readme, encoding="utf-8")

    diagnostics = build_public_readme_diagnostics(readme, config)
    config.diagnostics_path.parent.mkdir(parents=True, exist_ok=True)
    diagnostics.to_csv(config.diagnostics_path, index=False)

    logger.info("Wrote public README polish with %d chars.", len(readme))
    return readme


def default_config(repo_root: Path | None = None) -> PublicReadmePolishConfig:
    r = repo_root or root()
    package_dir = r / "outputs/publication/publication_package_v0"
    return PublicReadmePolishConfig(
        publication_package_dir=package_dir,
        output_path=package_dir / "PUBLICATION_README.md",
        publication_manifest_path=package_dir / "publication_manifest.csv",
        publication_exclusions_path=package_dir / "publication_exclusions.csv",
        publication_sanitization_path=package_dir / "publication_sanitization_checks.csv",
        release_summary_path=r / "data/processed/reports/release_gate_summary.csv",
        final_verdict_path=r / "data/processed/reports/final_research_verdict.csv",
        schema_summary_path=r / "data/processed/reports/schema_contract_summary.csv",
        live_readiness_summary_path=r / "data/processed/reports/live_data_readiness_summary.csv",
        diagnostics_path=r / "outputs/diagnostics/public_readme_polish_diagnostics.csv",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build public README polish v0.")
    parser.add_argument("--publication-package-dir", default="outputs/publication/publication_package_v0")
    parser.add_argument("--output-path", default="outputs/publication/publication_package_v0/PUBLICATION_README.md")
    parser.add_argument("--publication-manifest-path", default="outputs/publication/publication_package_v0/publication_manifest.csv")
    parser.add_argument("--publication-exclusions-path", default="outputs/publication/publication_package_v0/publication_exclusions.csv")
    parser.add_argument("--publication-sanitization-path", default="outputs/publication/publication_package_v0/publication_sanitization_checks.csv")
    parser.add_argument("--release-summary-path", default="data/processed/reports/release_gate_summary.csv")
    parser.add_argument("--final-verdict-path", default="data/processed/reports/final_research_verdict.csv")
    parser.add_argument("--schema-summary-path", default="data/processed/reports/schema_contract_summary.csv")
    parser.add_argument("--live-readiness-summary-path", default="data/processed/reports/live_data_readiness_summary.csv")
    parser.add_argument("--diagnostics-path", default="outputs/diagnostics/public_readme_polish_diagnostics.csv")
    args = parser.parse_args()

    r = root()
    config = PublicReadmePolishConfig(
        publication_package_dir=r / args.publication_package_dir,
        output_path=r / args.output_path,
        publication_manifest_path=r / args.publication_manifest_path,
        publication_exclusions_path=r / args.publication_exclusions_path,
        publication_sanitization_path=r / args.publication_sanitization_path,
        release_summary_path=r / args.release_summary_path,
        final_verdict_path=r / args.final_verdict_path,
        schema_summary_path=r / args.schema_summary_path,
        live_readiness_summary_path=r / args.live_readiness_summary_path,
        diagnostics_path=r / args.diagnostics_path,
    )
    build_public_readme_polish(config)


if __name__ == "__main__":
    main()
