from pathlib import Path

import pandas as pd

from fvn_dfm.reporting.public_readme_polish import PublicReadmePolishConfig, build_public_readme_polish


def test_build_public_readme_polish_integration(tmp_path: Path):
    package_dir = tmp_path / "outputs/publication/publication_package_v0"
    package_dir.mkdir(parents=True)
    (tmp_path / "data/processed/reports").mkdir(parents=True)

    pd.DataFrame(
        [
            {"section": "public_documents", "package_path": "README.md"},
            {"section": "public_reports", "package_path": "outputs/reports/final_research_verdict.md"},
            {"section": "public_tables", "package_path": "data/processed/reports/release_gate_summary.csv"},
        ]
    ).to_csv(package_dir / "publication_manifest.csv", index=False)
    pd.DataFrame([], columns=["relative_path", "reason"]).to_csv(package_dir / "publication_exclusions.csv", index=False)
    pd.DataFrame([{"check_id": "NO_FORBIDDEN_PATHS_INCLUDED", "status": "PASS"}]).to_csv(package_dir / "publication_sanitization_checks.csv", index=False)
    pd.DataFrame([{"release_gate_status": "PASS"}]).to_csv(tmp_path / "data/processed/reports/release_gate_summary.csv", index=False)
    pd.DataFrame([{"final_verdict": "PASS"}]).to_csv(tmp_path / "data/processed/reports/final_research_verdict.csv", index=False)
    pd.DataFrame([{"schema_contract_status": "PASS"}]).to_csv(tmp_path / "data/processed/reports/schema_contract_summary.csv", index=False)
    pd.DataFrame([{"live_readiness_status": "READY_WITH_WARNINGS"}]).to_csv(tmp_path / "data/processed/reports/live_data_readiness_summary.csv", index=False)

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
    build_public_readme_polish(cfg)

    text = cfg.output_path.read_text(encoding="utf-8")
    assert "Disclosure–Fundamental Mismatch" in text
    assert "READY_WITH_WARNINGS" in text
    assert "make build-publication-package" in text
    assert cfg.diagnostics_path.exists()
