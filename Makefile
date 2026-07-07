SHELL := /bin/bash

.PHONY: setup check-configs audit-skeleton download-data build-source-tables build-pit-tables extract-text extract-xbrl build-features build-labels build-panel audit-dataset run-oos run-portfolio run-baselines run-ablations run-failure-tests tearsheet verdict clean-outputs

setup:
	python -m pip install -e .

check-configs:
	python scripts/00_setup_project.py --check-configs

audit-skeleton:
	python scripts/00_setup_project.py --audit-skeleton

download-data:
	python scripts/01_download_raw_data.py --source sec-submissions --cik-file data/raw/sec/cik_download_list.txt

build-source-tables:
	python scripts/02_build_source_tables.py --table sec-filing-event

build-pit-tables:
	python scripts/03_build_point_in_time_tables.py --table filing-availability

extract-text:
	python scripts/04_extract_text.py --layer filing-text-raw

extract-xbrl:
	python scripts/05_extract_xbrl_facts.py --source sec-fsds

build-features:
	python scripts/06_build_features.py --layer text-features-asof

build-labels:
	python scripts/07_build_labels.py

build-panel:
	python scripts/08_build_model_panel.py

audit-dataset:
	python scripts/09_run_dataset_integrity_checks.py

run-oos:
	python scripts/10_run_oos_engine.py

run-portfolio:
	python scripts/11_run_portfolio.py

run-baselines:
	python scripts/12_run_baselines.py

run-ablations:
	python scripts/13_run_ablations.py

run-failure-tests:
	python scripts/14_run_failure_tests.py

tearsheet:
	python scripts/15_generate_institutional_tearsheet.py

verdict:
	python scripts/16_generate_final_verdict.py

clean-outputs:
	find outputs reports logs -type f ! -name '.gitkeep' -delete

download-complete-submissions:
	python scripts/01_download_raw_data.py --source sec-complete-submissions --filing-refs-csv data/raw/sec/filing_refs_sample.csv

download-primary-documents:
	python scripts/01_download_raw_data.py --source sec-primary-documents

extract-sections:
	python scripts/04_extract_text.py --layer filing-section-text

lm-summary:
	python -m fvn_dfm.data_ingestion.loughran_mcdonald

download-fsds:
	python scripts/01_download_raw_data.py --source sec-fsds --years 2009-2025

select-accounting-facts:
	python scripts/05_extract_xbrl_facts.py --source accounting-fact-selected

build-fundamental-features:
	python scripts/06_build_features.py --layer fundamental-features-asof

build-fundamental-deltas:
	python scripts/06_build_features.py --layer fundamental-delta-features-asof

build-fundamental-composites:
	python scripts/06_build_features.py --layer fundamental-composite-features-asof

build-mismatch-features:
	python scripts/06_build_features.py --layer mismatch-features-asof

build-research-panel:
	python scripts/07_build_model_matrix.py --layer model-research-panel

build-price-return-source:
	python scripts/08_build_targets.py --layer price-return-source --raw-price-path data/raw/prices/adjusted_prices.csv

build-return-targets:
	python scripts/08_build_targets.py --layer return-targets-asof

build-model-dataset:
	python scripts/07_build_model_matrix.py --layer model-dataset-v0

build-walk-forward-splits:
	python scripts/07_build_model_matrix.py --layer model-dataset-with-splits

train-baseline-models:
	python scripts/09_train_models.py --layer baseline-models-v0

build-model-selection-report:
	python scripts/10_evaluate_models.py --layer model-selection-report-v0

build-long-short-decile:
	python scripts/11_build_portfolio.py --layer long-short-decile-v0

build-portfolio-performance:
	python scripts/11_build_portfolio.py --layer portfolio-performance-report-v0

build-ablation-study:
	python scripts/10_evaluate_models.py --layer ablation-study-v0

build-final-verdict:
	python scripts/12_generate_reports.py --layer final-research-verdict-v0

build-reproducibility-pack:
	python scripts/12_generate_reports.py --layer reproducibility-pack-v0

run-e2e-smoke:
	python scripts/13_run_smoke_pipeline.py

check-live-readiness:
	python scripts/14_check_live_readiness.py

check-live-readiness-strict:
	python scripts/14_check_live_readiness.py --fail-on-blocked

run-live-pipeline:
	python scripts/15_run_live_pipeline.py --stage full-live

run-live-pipeline-dry:
	python scripts/15_run_live_pipeline.py --stage full-live --dry-run

run-live-pipeline-override:
	python scripts/15_run_live_pipeline.py --stage full-live --override-readiness

build-data-lineage-graph:
	python scripts/12_generate_reports.py --layer data-lineage-graph-v0

validate-schema-contracts:
	python scripts/16_validate_schema_contracts.py

validate-schema-contracts-strict:
	python scripts/16_validate_schema_contracts.py --fail-on-blockers

validate-smoke-schema-contracts:
	python scripts/16_validate_schema_contracts.py --base-dir outputs/smoke/e2e_smoke_v0

build-release-checklist:
	python scripts/12_generate_reports.py --layer release-checklist-v0

build-release-checklist-strict-live:
	python scripts/12_generate_reports.py --layer release-checklist-v0 --require-live-readiness

build-publication-package:
	python scripts/12_generate_reports.py --layer publication-package-v0

build-public-readme-polish:
	python scripts/12_generate_reports.py --layer public-readme-polish-v0

build-final-archive-freeze:
	python scripts/12_generate_reports.py --layer final-archive-freeze-v0

build-final-archive-freeze-relaxed:
	python scripts/12_generate_reports.py --layer final-archive-freeze-v0 --allow-release-gate-warning
