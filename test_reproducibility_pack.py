from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.public_readme_polish import (
    PublicReadmePolishConfig,
    build_public_readme_diagnostics,
    build_public_readme_polish,
    render_public_landing_readme,
)


def sample_frames():
    manifest = pd.DataFrame(
        [
            {"section": "public_reports", "package_path": "outputs/reports/final_research_verdict.md"},
            {"section": "public_tables", "package_path": "data/processed/reports/release_gate_summary.csv"},
        ]
    )
    exclusions = pd.DataFrame([{"relative_path": "missing.md", "reason": "missing_optional"}])
    sanitization = pd.DataFrame([{"check_id": "NO_FORBIDDEN_PATHS_INCLUDED", "status": "PASS"}])
    release_summary = pd.DataFrame([{"release_gate_status": "PASS"}])
    final_verdict = pd.DataFrame([{"final_verdict": "PASS"}])
    schema_summary = pd.DataFrame([{"schema_contract_status": "PASS"}])
    live_readiness = pd.DataFrame([{"live_readiness_status": "READY"}])
    return manifest, exclusions, sanitization, release_summary, final_verdict, schema_summary, live_readiness


def test_render_public_landing_readme_contains_core_sections():
    frames = sample_frames()
    readme = render_public_landing_readme(
        manifest=frames[0],
        exclusions=frames[1],
        sanitization=frames[2],
        release_summary=frames[3],
        final_verdict=frames[4],
        schema_summary=frames[5],
        live_readiness=frames[6],
    )

    assert "# FVN Research Archive 001" in readme
    assert "## Research thesis" in readme
    assert "```mermaid" in readme
    assert "## Audit controls included" in readme
    assert "make run-e2e-smoke" in readme
    assert "What is deliberately excluded" in readme


def test_public_readme_diagnostics():
    frames = sample_frames()
    readme = render_public_landing_readme(
        manifest=frames[0],
        exclusions=frames[1],
        sanitization=frames[2],
        release_summary=frames[3],
        final_verdict=frames[4],
        schema_summary=frames[5],
        live_readiness=frames[6],
    )
    cfg = PublicReadmePolishConfig(
        publication_package_dir=Path("package"),
        output_path=Path("package/PUBLICATION_README.md"),
        publication_manifest_path=Path("package/publication_manifest.csv"),
        publication_exclusions_path=Path("package/publication_exclusions.csv"),
        publication_sanitization_path=Path("package/publication_sanitization_checks.csv"),
        release_summary_path=Path("release.csv"),
        final_verdict_path=Path("verdict.csv"),
        schema_summary_path=Path("schema.csv"),
        live_readiness_summary_path=Path("live.csv"),
        diagnostics_path=Path("diagnostics.csv"),
    )
    diagnostics = build_public_readme_diagnostics(readme, cfg)
    assert diagnostics[diagnostics["diagnostic"] == "contains_research_thesis"].iloc[0]["value"] is True or diagnostics[diagnostics["diagnostic"] == "contains_research_thesis"].iloc[0]["value"] == True


def test_build_public_readme_polish_outputs(tmp_path: Path):
    package_dir = tmp_path / "outputs/publication/publication_package_v0"
    package_dir.mkdir(parents=True)

    frames = sample_frames()
    frames[0].to_csv(package_dir / "publication_manifest.csv", index=False)
    frames[1].to_csv(package_dir / "publication_exclusions.csv", index=False)
    frames[2].to_csv(package_dir / "publication_sanitization_checks.csv", index=False)

    (tmp_path / "data/processed/reports").mkdir(parents=True)
    frames[3].to_csv(tmp_path / "data/processed/reports/release_gate_summary.csv", index=False)
    frames[4].to_csv(tmp_path / "data/processed/reports/final_research_verdict.csv", index=False)
    frames[5].to_csv(tmp_path / "data/processed/reports/schema_contract_summary.csv", index=False)
    frames[6].to_csv(tmp_path / "data/processed/reports/live_data_readiness_summary.csv", index=False)

    cfg = PublicReadmePolishConfig(
        publication_package_dir=package_dir,
        output_path=package_dir / "PUBLICATION_README.md",
        publication_manifest_path=package_dir / "publication_manifest.csv",
        publication_exclusions_path=package_dir / "publication_exclusions.csv",
        publication_sanitization_path=package_dir / "publication_sanitization_checks.csv",
        release_summary_path=tmp_path / "data/processed/reports/release_gate_summary.csv",
        final_verdict_path=tmp_path / "data/processed/reports/final_research_verdict.csv",
        schema_summary_path=tmp_path / "data/processed/reports/schema_contract_summary.csv",
        live_readiness_summary_path=tmp_path / "data/processed/reports/live_data_readiness_summary.csv",
        diagnostics_path=tmp_path / "outputs/diagnostics/public_readme_polish_diagnostics.csv",
    )

    readme = build_public_readme_polish(cfg)
    assert cfg.output_path.exists()
    assert cfg.diagnostics_path.exists()
    assert "Pipeline diagram" in readme
