# FVN Research Archive 001 — Disclosure–Fundamental Mismatch

This repository implements a point-in-time public-markets research project testing whether U.S. equities exhibit delayed repricing when SEC filing language and accounting fundamentals diverge.

The project is deliberately falsification-first:

- no in-sample alpha claims
- no shuffled train/test split
- no OOS tuning
- no hidden survivorship assumptions
- no before-cost main result
- no public narrative before final verdict

Primary evidence standard:

`walk-forward OOS performance after transaction costs, beyond fundamentals-only, text-only, no-mismatch, controls-only, and known-anomaly baselines, with ablations and failure tests.`

## Current status

Sprint 01 — Research Infrastructure.

No raw data is included in this repository. Raw public data must be downloaded through the configured ingestion scripts and recorded in `data/manifests/raw_file_manifest.csv`.

## First commands

```bash
make setup
make check-configs
make audit-skeleton
```

## Research verdict classes

A — Archive Alpha Candidate  
B — Research Insight, Not Tradable Alpha  
C — Mechanism Rejected  
D — Inconclusive Due to Data Limitations


## Sprint 02 — SEC submissions ingestion

Before downloading from SEC, edit:

`configs/01_data_sources.yaml`

Replace:

`FVN Research contact_email_to_be_set`

with a valid research contact User-Agent string.

Example commands:

```bash
# Check config parsing and skeleton
make check-configs
make audit-skeleton

# Download one CIK
python scripts/01_download_raw_data.py --source sec-submissions --cik 0000320193

# Download a batch
python scripts/01_download_raw_data.py --source sec-submissions --cik-file data/raw/sec/cik_download_list.txt
```

Every successful raw download is appended to:

`data/manifests/raw_file_manifest.csv`

Raw files are immutable. Existing files are skipped by default. With `--force`, the downloader creates a timestamped copy rather than overwriting.


## Sprint 02 continuation — SEC complete submissions

Complete submission `.txt` files are required for EDGAR header reconstruction, `<ACCEPTANCE-DATETIME>`, raw filing text, and primary document discovery.

Example commands:

```bash
# One filing
python scripts/01_download_raw_data.py \
  --source sec-complete-submissions \
  --cik 0000320193 \
  --accession-number 0000320193-23-000106 \
  --form-type 10-K \
  --filing-date 2023-11-03

# Batch
python scripts/01_download_raw_data.py \
  --source sec-complete-submissions \
  --filing-refs-csv data/raw/sec/filing_refs_sample.csv
```

Expected SEC archive path format:

`https://www.sec.gov/Archives/edgar/data/{cik_without_leading_zeros}/{accession_no_dashes}/{accession_with_dashes}.txt`

Downloaded files are stored under:

`data/raw/sec/complete_submissions/{CIK10}/{accession}.txt`

and appended to:

`data/manifests/raw_file_manifest.csv`.


## Source table bridge — SEC filing events from submissions JSON

After downloading SEC submissions JSON files, build the normalized filing-event table and complete-submission candidate list:

```bash
make build-source-tables
```

Equivalent explicit command:

```bash
python scripts/02_build_source_tables.py   --table sec-filing-event   --forms 10-K,10-Q   --min-filing-date 2009-01-01
```

Outputs:

`data/processed/source_tables/sec_filing_event.parquet`  
`data/processed/source_tables/sec_filing_event.csv`  
`data/interim/sec/complete_submission_filing_refs.csv`

The candidate CSV can be passed directly into the complete-submission downloader:

```bash
python scripts/01_download_raw_data.py   --source sec-complete-submissions   --filing-refs-csv data/interim/sec/complete_submission_filing_refs.csv
```


## Point-in-time table — filing availability

After complete submission `.txt` files are downloaded, build canonical filing availability:

```bash
make build-pit-tables
```

Equivalent explicit command:

```bash
python scripts/03_build_point_in_time_tables.py   --table filing-availability   --complete-submissions-dir data/raw/sec/complete_submissions   --filing-event-path data/processed/source_tables/sec_filing_event.csv
```

Outputs:

`data/processed/point_in_time/filing_availability.parquet`  
`data/processed/point_in_time/filing_availability.csv`

The canonical timestamp is parsed from the complete submission header:

`<ACCEPTANCE-DATETIME>YYYYMMDDHHMMSS`

Execution-date policy:

- before 16:00 New York time: first allowed execution is T+1 trading day
- at/after 16:00 New York time: first allowed execution is T+2 trading days

The submissions JSON `acceptanceDateTime` is retained only as diagnostic metadata.


## Sprint 02 continuation — SEC primary documents

After `filing_availability` exists, discover and download the actual primary 10-K/10-Q HTML documents:

```bash
python scripts/01_download_raw_data.py   --source sec-primary-documents   --filing-availability-path data/processed/point_in_time/filing_availability.csv   --complete-submissions-dir data/raw/sec/complete_submissions
```

Discovery-only mode:

```bash
python scripts/01_download_raw_data.py   --source sec-primary-documents   --discover-only
```

Download from a prebuilt candidate CSV:

```bash
python scripts/01_download_raw_data.py   --source sec-primary-documents   --download-only   --primary-document-candidates-csv data/interim/sec/primary_document_candidates.csv
```

Outputs:

`data/interim/sec/primary_document_candidates.csv`  
`data/raw/sec/primary_documents/{CIK10}/{accession}/{primary_document}`

The primary document URL is built as:

`https://www.sec.gov/Archives/edgar/data/{cik_without_leading_zeros}/{accession_no_dashes}/{primary_document}`

Raw downloads are immutable and appended to `data/manifests/raw_file_manifest.csv`.


## Text extraction v0 — `filing_text_raw`

After primary documents are downloaded, build the raw-clean text source table:

```bash
make extract-text
```

Equivalent explicit command:

```bash
python scripts/04_extract_text.py   --layer filing-text-raw   --primary-documents-dir data/raw/sec/primary_documents
```

Outputs:

`data/processed/source_tables/filing_text_raw.parquet`  
`data/processed/source_tables/filing_text_raw.csv`

The v0 extractor:

- reads stored primary 10-K/10-Q HTML documents
- removes script/style/head noise
- removes tables by default
- normalizes whitespace
- infers CIK/accession/document lineage from path
- records raw character count
- records clean character count
- records clean word count
- records clean/raw ratio
- adds parse quality flags
- stores clean text for downstream dictionary and section extraction

Use `--keep-tables` only for diagnostics; primary text features should avoid numeric table dominance.


## Text extraction v0 — `filing_section_text`

After `filing_text_raw` exists, extract section-level text for MD&A, Risk Factors, and Liquidity:

```bash
make extract-sections
```

Equivalent explicit command:

```bash
python scripts/04_extract_text.py   --layer filing-section-text   --filing-text-raw-path data/processed/source_tables/filing_text_raw.csv
```

Outputs:

`data/processed/source_tables/filing_section_text.parquet`  
`data/processed/source_tables/filing_section_text.csv`

Sections produced:

- `mda`
- `risk_factors`
- `liquidity`

The v0 section extractor records:

- section text
- section character count
- section word count
- start/end offsets in source clean text
- extraction method
- section quality flag
- section quality notes
- accession lineage key
- text and section version

This is a heuristic v0 extractor. It is intentionally auditable and conservative; section failures become quality flags rather than silent deletions.


## Feature build v1 — `text_features_asof`

After `filing_text_raw`, `filing_section_text`, and the Loughran–McDonald dictionary are available, build the first Disclosure Narrative feature layer:

```bash
make build-features
```

Equivalent explicit command:

```bash
python scripts/06_build_features.py   --layer text-features-asof   --filing-text-raw-path data/processed/source_tables/filing_text_raw.csv   --filing-section-text-path data/processed/source_tables/filing_section_text.csv   --filing-availability-path data/processed/point_in_time/filing_availability.csv   --lm-dictionary-path data/raw/dictionaries/loughran_mcdonald
```

Outputs:

`data/processed/features/text_features_asof.parquet`  
`data/processed/features/text_features_asof.csv`

The first feature builder creates Loughran–McDonald counts and shares for:

- Negative
- Positive
- Uncertainty
- Litigious
- Constraining
- Strong Modal
- Weak Modal

Prefixes:

- `full_`
- `mda_`
- `risk_`
- `liquidity_`

The layer also carries:

- `feature_asof_date`
- `accepted_at_edgar`
- `timestamp_quality_flag`
- section availability flags
- section quality flags
- text feature version


## XBRL ingestion — SEC Financial Statement Data Sets

Download quarterly SEC Financial Statement Data Sets ZIP files:

```bash
python scripts/01_download_raw_data.py   --source sec-fsds   --years 2009-2025
```

Ingest local raw ZIP files into normalized source tables:

```bash
make extract-xbrl
```

Equivalent explicit command:

```bash
python scripts/05_extract_xbrl_facts.py   --source sec-fsds   --raw-fsds-dir data/raw/sec/financial_statement_data_sets   --output-dir data/processed/source_tables   --forms 10-K,10-Q
```

Expected raw ZIP names:

`YYYYqN.zip`, for example `2023q4.zip`

Each ZIP must contain:

- `sub.txt`
- `num.txt`
- `tag.txt`
- `pre.txt`

Outputs:

`data/processed/source_tables/xbrl_submission_metadata.parquet`  
`data/processed/source_tables/xbrl_submission_metadata.csv`  
`data/processed/source_tables/xbrl_fact_accession_raw.parquet`  
`data/processed/source_tables/xbrl_fact_accession_raw.csv`  
`data/processed/source_tables/xbrl_tag_metadata.parquet`  
`data/processed/source_tables/xbrl_tag_metadata.csv`  
`data/processed/source_tables/xbrl_presentation_metadata.parquet`  
`data/processed/source_tables/xbrl_presentation_metadata.csv`

Diagnostics:

`outputs/diagnostics/sec_fsds_ingestion_diagnostics.csv`

Primary accounting fact table for later Fundamental Reality features:

`xbrl_fact_accession_raw`


## XBRL selector — `accounting_fact_selected`

After SEC FSDS source tables exist, select canonical accounting facts:

```bash
make select-accounting-facts
```

Equivalent explicit command:

```bash
python scripts/05_extract_xbrl_facts.py   --source accounting-fact-selected   --xbrl-fact-path data/processed/source_tables/xbrl_fact_accession_raw.csv   --xbrl-submission-path data/processed/source_tables/xbrl_submission_metadata.csv
```

Outputs:

`data/processed/source_tables/accounting_fact_selected.parquet`  
`data/processed/source_tables/accounting_fact_selected.csv`

Diagnostics:

`outputs/diagnostics/accounting_fact_selected_diagnostics.csv`

Canonical concepts v0:

- `revenue`
- `net_income`
- `cfo`
- `assets`
- `liabilities`
- `debt`
- `cash`
- `receivables`
- `inventory`
- `capex`
- `shares`

The selector uses tag priority, expected unit, coreg preference, period/qtrs consistency, and accession metadata. v0 does not perform YTD-to-quarter conversion; quarterly duration facts with non-quarterly `qtrs` are flagged for later controlled conversion.


## Feature build v0 — `fundamental_features_asof`

After `accounting_fact_selected` exists, build accession-level Fundamental Reality features:

```bash
make build-fundamental-features
```

Equivalent explicit command:

```bash
python scripts/06_build_features.py   --layer fundamental-features-asof   --accounting-fact-selected-path data/processed/source_tables/accounting_fact_selected.csv   --filing-availability-path data/processed/point_in_time/filing_availability.csv
```

Outputs:

`data/processed/features/fundamental_features_asof.parquet`  
`data/processed/features/fundamental_features_asof.csv`

Diagnostics:

`outputs/diagnostics/fundamental_features_asof_diagnostics.csv`

Values pivoted from `accounting_fact_selected`:

- `revenue`
- `net_income`
- `cfo`
- `assets`
- `liabilities`
- `debt`
- `cash`
- `receivables`
- `inventory`
- `capex`
- `shares`

Initial ratios v0:

- `net_margin`
- `cfo_to_net_income`
- `cfo_to_revenue`
- `liabilities_to_assets`
- `debt_to_assets`
- `cash_to_assets`
- `receivables_to_assets`
- `inventory_to_assets`
- `capex_to_revenue`
- `asset_turnover`
- `cash_minus_debt_to_assets`
- `working_capital_proxy_to_assets`

The layer also carries concept availability flags, selected tags, unit/qtrs/ddate metadata, feature-as-of date, timestamp quality, coverage ratio, and aggregate quality flags.


## Feature build v0 — `fundamental_delta_features_asof`

After `fundamental_features_asof` exists, build comparable-period YoY deltas:

```bash
make build-fundamental-deltas
```

Equivalent explicit command:

```bash
python scripts/06_build_features.py   --layer fundamental-delta-features-asof   --fundamental-features-path data/processed/features/fundamental_features_asof.csv
```

Outputs:

`data/processed/features/fundamental_delta_features_asof.parquet`  
`data/processed/features/fundamental_delta_features_asof.csv`

Diagnostics:

`outputs/diagnostics/fundamental_delta_features_asof_diagnostics.csv`

Comparable-link policy v0:

- `FY` links to prior `FY`
- `Q1` links to prior `Q1`
- `Q2` links to prior `Q2`
- `Q3` links to prior `Q3`
- `Q4` links to prior `Q4` if present

The layer computes YoY absolute, percentage, and signed-log changes for raw accounting values:

- revenue
- net income
- CFO
- assets
- liabilities
- debt
- cash
- receivables
- inventory
- capex
- shares

The layer computes YoY deltas for ratios:

- net margin
- CFO to net income
- CFO to revenue
- liabilities to assets
- debt to assets
- cash to assets
- receivables to assets
- inventory to assets
- capex to revenue
- asset turnover
- cash minus debt to assets
- working capital proxy to assets

Protocol aliases:

- `margin_yoy_delta`
- `cfo_quality_yoy_delta`
- `cash_conversion_yoy_delta`
- `leverage_yoy_delta`
- `liability_intensity_yoy_delta`
- `working_capital_proxy_yoy_delta`
- `capex_intensity_yoy_delta`


## Feature build v0 — `fundamental_composite_features_asof`

After `fundamental_delta_features_asof` exists, build Fundamental Stress / Improvement composites:

```bash
make build-fundamental-composites
```

Equivalent explicit command:

```bash
python scripts/06_build_features.py   --layer fundamental-composite-features-asof   --fundamental-delta-features-path data/processed/features/fundamental_delta_features_asof.csv
```

Outputs:

`data/processed/features/fundamental_composite_features_asof.parquet`  
`data/processed/features/fundamental_composite_features_asof.csv`

Diagnostics:

`outputs/diagnostics/fundamental_composite_features_asof_diagnostics.csv`

Composite outputs:

- `fund_stress_score`
- `fund_improve_score`
- `fund_net_stress_score`
- `fund_net_improvement_score`
- `fundamental_reality_score`
- stress/improvement component raw values
- stress/improvement component positive-part values
- component coverage counts
- aggregate composite quality flags

Stress-positive components v0 include:

- revenue decline
- net income decline
- margin deterioration
- CFO quality deterioration
- cash conversion deterioration
- asset growth pressure
- liability intensity increase
- leverage increase
- cash buffer decline
- receivables intensity increase
- inventory intensity increase
- capex intensity increase
- share dilution
- working capital proxy deterioration

Improvement-positive components v0 are the directional mirror of the stress components.


## Feature build v0 — `mismatch_features_asof`

After `fundamental_composite_features_asof` and `text_features_asof` exist, build Disclosure–Fundamental Mismatch features:

```bash
make build-mismatch-features
```

Equivalent explicit command:

```bash
python scripts/06_build_features.py   --layer mismatch-features-asof   --fundamental-composite-features-path data/processed/features/fundamental_composite_features_asof.csv   --text-features-path data/processed/features/text_features_asof.csv
```

Outputs:

`data/processed/features/mismatch_features_asof.parquet`  
`data/processed/features/mismatch_features_asof.csv`

Diagnostics:

`outputs/diagnostics/mismatch_features_asof_diagnostics.csv`

Core output scores:

- `downside_mismatch_score`
- `upside_mismatch_score`
- `net_mismatch_score`
- `dfm_score_simple`

Downside mismatch v0 combines accounting stress with optimistic, insufficiently negative, uncertain, litigious, constraining, and specific-section disclosure features.

Upside mismatch v0 combines accounting improvement with cautious, negative, uncertain, constraining, and modal language features.

The output also carries component-level interactions, component coverage, selected source features, accession lineage, as-of timestamp metadata, and mismatch quality flags.


## Model layer v0 — `model_research_panel`

After feature layers exist, assemble the modeling research panel:

```bash
make build-research-panel
```

Equivalent explicit command:

```bash
python scripts/07_build_model_matrix.py   --layer model-research-panel   --mismatch-features-path data/processed/features/mismatch_features_asof.csv   --fundamental-features-path data/processed/features/fundamental_features_asof.csv   --text-features-path data/processed/features/text_features_asof.csv   --filing-availability-path data/processed/point_in_time/filing_availability.csv
```

Outputs:

`data/processed/model/model_research_panel.parquet`  
`data/processed/model/model_research_panel.csv`

Diagnostics:

`outputs/diagnostics/model_research_panel_diagnostics.csv`

The panel assembly layer:

- uses `mismatch_features_asof` as the anchor
- joins accession-level `fundamental_features_asof`
- joins document-level `text_features_asof`
- joins filing availability metadata
- prefixes fundamental feature columns with `fund_`
- prefixes text feature columns with `text_`
- preserves DFM features as primary signal columns
- adds `panel_row_id`
- adds lineage version columns
- adds `panel_eligible`
- adds `panel_quality_flag`
- adds `panel_quality_notes`

Default quality gates require:

- valid `feature_asof_date`
- timestamp quality not red/missing
- mismatch quality green or yellow
- no red text parse quality
- no red fundamental quality
- non-missing `dfm_score_simple`


## Target layer v0 — `return_targets_asof`

Normalize a vendor-neutral adjusted price CSV:

```bash
python scripts/08_build_targets.py   --layer price-return-source   --raw-price-path data/raw/prices/adjusted_prices.csv
```

Expected price input schema:

```csv
date,ticker,cik10,sector,adj_close
2023-11-07,AAPL,0000320193,Information Technology,180.00
```

Build forward return targets for the model research panel:

```bash
make build-return-targets
```

Equivalent explicit command:

```bash
python scripts/08_build_targets.py   --layer return-targets-asof   --model-research-panel-path data/processed/model/model_research_panel.csv   --price-return-source-path data/processed/source_tables/price_return_source.csv   --horizon-trading-days 63
```

Outputs:

`data/processed/source_tables/price_return_source.parquet`  
`data/processed/source_tables/price_return_source.csv`  
`data/processed/targets/return_targets_asof.parquet`  
`data/processed/targets/return_targets_asof.csv`

Diagnostics:

`outputs/diagnostics/price_return_source_diagnostics.csv`  
`outputs/diagnostics/return_targets_asof_diagnostics.csv`

Target columns:

- `target_entry_date`
- `target_exit_date`
- `target_horizon_trading_days`
- `forward_63d_raw_return`
- `forward_63d_sector_return`
- `forward_63d_sector_adjusted_return`
- `target_available`
- `target_quality_flag`
- `target_quality_notes`

Policy v0:

- entry date is the first trading day on or after `feature_asof_date`
- exit date is 63 trading days after entry date
- raw return uses adjusted close
- sector return is equal-weight average of securities in the same sector with valid prices on both entry and exit dates
- sector-adjusted target equals raw return minus sector return
- no live vendor dependency is embedded in v0; price download remains an explicit adapter stub


## Model layer v0 — `model_dataset_v0`

After `model_research_panel` and `return_targets_asof` exist, assemble the final modeling dataset:

```bash
make build-model-dataset
```

Equivalent explicit command:

```bash
python scripts/07_build_model_matrix.py   --layer model-dataset-v0   --model-research-panel-path data/processed/model/model_research_panel.csv   --return-targets-path data/processed/targets/return_targets_asof.csv
```

Outputs:

`data/processed/model/model_dataset_v0.parquet`  
`data/processed/model/model_dataset_v0.csv`

Diagnostics:

`outputs/diagnostics/model_dataset_v0_diagnostics.csv`

The dataset assembly layer:

- joins `model_research_panel` to `return_targets_asof`
- uses `panel_row_id` as the primary join key
- creates label columns:
  - `y_forward_63d_sector_adjusted_return`
  - `y_forward_63d_raw_return`
  - `y_forward_63d_sector_return`
- enforces panel eligibility
- enforces target availability
- enforces target quality gates
- enforces non-missing primary label
- checks target entry/exit ordering against feature as-of date
- creates `sample_weight`
- creates `dataset_split_status`
- creates `model_feature_columns`
- creates `model_feature_count`
- creates `model_dataset_eligible`
- creates `model_dataset_quality_flag`
- creates `model_dataset_quality_notes`

The feature list excludes target/leakage columns and keeps model-ready numeric features such as DFM scores, mismatch components, fundamental features, and text features.


## Model layer v0 — `model_dataset_with_splits`

After `model_dataset_v0` exists, assign walk-forward train/validation/test folds:

```bash
make build-walk-forward-splits
```

Equivalent explicit command:

```bash
python scripts/07_build_model_matrix.py   --layer model-dataset-with-splits   --model-dataset-path data/processed/model/model_dataset_v0.csv   --min-train-months 24   --validation-months 12   --test-months 1   --step-months 1   --embargo-days 63
```

Outputs:

`data/processed/model/model_dataset_with_splits.parquet`  
`data/processed/model/model_dataset_with_splits.csv`

Diagnostics:

`outputs/diagnostics/model_dataset_with_splits_diagnostics.csv`

Split policy v0:

- expanding training window
- rolling validation window
- rolling test window
- calendar-day embargo between train and validation
- calendar-day embargo between validation and test
- default embargo is 63 days
- default test cadence is monthly
- ineligible `model_dataset_v0` rows are excluded by default

Added split metadata:

- `walk_forward_fold_id`
- `walk_forward_role`
- `walk_forward_train_start`
- `walk_forward_train_end`
- `walk_forward_validation_start`
- `walk_forward_validation_end`
- `walk_forward_test_start`
- `walk_forward_test_end`
- `walk_forward_embargo_days`
- `walk_forward_split_version`


## Modeling v0 — baseline model trainer

After `model_dataset_with_splits` exists, train baseline walk-forward models:

```bash
make train-baseline-models
```

Equivalent explicit command:

```bash
python scripts/09_train_models.py   --layer baseline-models-v0   --model-dataset-with-splits-path data/processed/model/model_dataset_with_splits.csv   --models ridge,elastic_net,gradient_boosting   --target-column y_forward_63d_sector_adjusted_return
```

Outputs:

`data/processed/model/baseline_fold_predictions.parquet`  
`data/processed/model/baseline_fold_predictions.csv`

Diagnostics:

`outputs/diagnostics/baseline_model_diagnostics.csv`

Models v0:

- `ridge`
- `elastic_net`
- `gradient_boosting`

Training policy v0:

- train one model per fold and model family
- fit only on `walk_forward_role == train`
- predict train, validation, and test rows for diagnostics
- use `model_feature_columns` from `model_dataset_v0`
- use median imputation
- use standard scaling for ridge and elastic-net
- no feature selection inside v0
- no hyperparameter search inside v0
- write fold-level predictions and role-level diagnostics

Prediction columns include:

- `walk_forward_fold_id`
- `walk_forward_role`
- `model_name`
- `model_row_id`
- `target_column`
- `y_true`
- `y_pred`
- `prediction_error`
- `feature_count`
- `feature_columns`

Diagnostics include role-level MSE, RMSE, MAE, R², Pearson correlation, and Spearman correlation where enough rows exist.


## Modeling v0 — model selection report

After `baseline_fold_predictions` and `baseline_model_diagnostics` exist, rank baseline models and select a primary model:

```bash
make build-model-selection-report
```

Equivalent explicit command:

```bash
python scripts/10_evaluate_models.py   --layer model-selection-report-v0   --baseline-diagnostics-path outputs/diagnostics/baseline_model_diagnostics.csv   --baseline-predictions-path data/processed/model/baseline_fold_predictions.csv
```

Outputs:

`data/processed/model/model_selection_report.parquet`  
`data/processed/model/model_selection_report.csv`  
`outputs/reports/model_selection_report.md`

Diagnostics:

`outputs/diagnostics/model_selection_report_diagnostics.csv`

Selection policy v0:

- aggregate successful fold metrics by model and role
- use validation Spearman IC as the primary criterion
- use validation MAE and validation RMSE as tie-breakers
- report test IC/MAE/RMSE for audit only
- select exactly one `is_primary_model == True`

Primary ranking columns:

- `validation_mean_spearman_ic`
- `validation_mean_mae`
- `validation_mean_rmse`
- `test_mean_spearman_ic`
- `test_mean_mae`
- `test_mean_rmse`
- `rank_validation_ic`
- `rank_validation_mae`
- `rank_validation_rmse`
- `model_selection_score`
- `model_selection_rank`
- `is_primary_model`


## Portfolio v0 — long-short decile construction

After `baseline_fold_predictions` and `model_selection_report` exist, construct monthly long-short decile portfolios from the primary model's test predictions:

```bash
make build-long-short-decile
```

Equivalent explicit command:

```bash
python scripts/11_build_portfolio.py   --layer long-short-decile-v0   --baseline-predictions-path data/processed/model/baseline_fold_predictions.csv   --model-selection-report-path data/processed/model/model_selection_report.csv   --transaction-cost-bps 10
```

Outputs:

`data/processed/portfolio/portfolio_holdings.parquet`  
`data/processed/portfolio/portfolio_holdings.csv`  
`data/processed/portfolio/portfolio_monthly_returns.parquet`  
`data/processed/portfolio/portfolio_monthly_returns.csv`

Diagnostics:

`outputs/diagnostics/portfolio_construction_diagnostics.csv`

Portfolio policy v0:

- use the primary model from `model_selection_report`
- use only `walk_forward_role == test`
- group predictions by monthly `feature_asof_date`
- long top decile by `y_pred`
- short bottom decile by `y_pred`
- equal-weight each leg
- target gross exposure: 2.0
- target net exposure: 0.0
- transaction costs default to 10 bps multiplied by one-way turnover
- portfolio return uses `y_true`, normally `y_forward_63d_sector_adjusted_return`

Return columns:

- `portfolio_gross_return`
- `portfolio_turnover`
- `transaction_cost_return`
- `portfolio_net_return`
- `long_leg_contribution`
- `short_leg_contribution`
- `long_avg_forward_return`
- `short_avg_forward_return`
- `gross_exposure`
- `net_exposure`
- `portfolio_quality_flag`


## Portfolio v0 — performance report

After `portfolio_monthly_returns` exists, build the portfolio performance report:

```bash
make build-portfolio-performance
```

Equivalent explicit command:

```bash
python scripts/11_build_portfolio.py   --layer portfolio-performance-report-v0   --portfolio-returns-path data/processed/portfolio/portfolio_monthly_returns.csv
```

Outputs:

`data/processed/portfolio/portfolio_performance_summary.parquet`  
`data/processed/portfolio/portfolio_performance_summary.csv`  
`data/processed/portfolio/portfolio_monthly_diagnostics.parquet`  
`data/processed/portfolio/portfolio_monthly_diagnostics.csv`  
`outputs/reports/portfolio_performance_report.md`

Diagnostics:

`outputs/diagnostics/portfolio_performance_report_diagnostics.csv`

Performance metrics v0:

- cumulative gross and net return
- annualized gross and net return
- gross and net Sharpe
- gross and net Sortino
- gross and net maximum drawdown
- gross and net hit rate
- profit factor
- average turnover
- transaction-cost drag
- long/short count diagnostics
- gross and net exposure diagnostics

The report treats `portfolio_monthly_returns` as the audited return stream from the OOS long-short decile portfolio layer.


## Evaluation v0 — ablation study

After `model_dataset_with_splits` exists, compare the DFM score against fundamentals-only, text-only, and naive baselines:

```bash
make build-ablation-study
```

Equivalent explicit command:

```bash
python scripts/10_evaluate_models.py   --layer ablation-study-v0   --model-dataset-with-splits-path data/processed/model/model_dataset_with_splits.csv
```

Outputs:

`data/processed/model/ablation_predictions.parquet`  
`data/processed/model/ablation_predictions.csv`  
`data/processed/model/ablation_metrics.parquet`  
`data/processed/model/ablation_metrics.csv`  
`data/processed/portfolio/ablation_portfolio_returns.parquet`  
`data/processed/portfolio/ablation_portfolio_returns.csv`  
`data/processed/model/ablation_summary.parquet`  
`data/processed/model/ablation_summary.csv`  
`outputs/reports/ablation_study_report.md`

Diagnostics:

`outputs/diagnostics/ablation_study_diagnostics.csv`

Ablations v0:

- `dfm_score`: `dfm_score_simple`
- `fundamentals_only`: hard-accounting reality score
- `text_only`: disclosure tone proxy
- `naive_baseline`: constant zero prediction

Comparison metrics:

- fold-level Spearman IC
- fold-level Pearson IC
- MAE
- RMSE
- long-short decile cumulative gross/net return
- hit rate
- turnover
- transaction cost drag

The portfolio comparison reuses the same monthly long-short decile construction rule for every ablation.


## Reporting v0 — final research verdict

After `portfolio_performance_summary`, `model_selection_report`, and `ablation_summary` exist, generate the final conservative research verdict:

```bash
make build-final-verdict
```

Equivalent explicit command:

```bash
python scripts/12_generate_reports.py   --layer final-research-verdict-v0   --portfolio-performance-summary-path data/processed/portfolio/portfolio_performance_summary.csv   --model-selection-report-path data/processed/model/model_selection_report.csv   --ablation-summary-path data/processed/model/ablation_summary.csv
```

Outputs:

`data/processed/reports/final_research_verdict.parquet`  
`data/processed/reports/final_research_verdict.csv`  
`data/processed/reports/final_research_evidence.parquet`  
`data/processed/reports/final_research_evidence.csv`  
`data/processed/reports/final_research_criteria.parquet`  
`data/processed/reports/final_research_criteria.csv`  
`outputs/reports/final_research_verdict.md`

Diagnostics:

`outputs/diagnostics/final_research_verdict_diagnostics.csv`

Conservative verdict gates v0:

- minimum OOS rebalance periods
- positive cumulative net return after costs
- minimum net Sharpe
- maximum net drawdown control
- positive primary-model validation IC
- positive DFM ablation IC
- DFM ablation must beat or tie simpler ablations by IC

The verdict is `PASS` only if every critical criterion passes. Otherwise it is `FAIL`.


## Reporting v0 — reproducibility pack

After the research pipeline has produced reports and final verdict artifacts, generate a one-command audit bundle:

```bash
make build-reproducibility-pack
```

Equivalent explicit command:

```bash
python scripts/12_generate_reports.py   --layer reproducibility-pack-v0
```

Outputs:

`outputs/audit/reproducibility_pack/README.md`  
`outputs/audit/reproducibility_pack/file_manifest.csv`  
`outputs/audit/reproducibility_pack/file_checksums.csv`  
`outputs/audit/reproducibility_pack/config_snapshot.json`  
`outputs/audit/reproducibility_pack/report_index.csv`  
`outputs/audit/reproducibility_pack/pipeline_run_order.csv`  
`outputs/audit/reproducibility_pack/pipeline_run_order.md`  
`outputs/audit/reproducibility_pack/reproducibility_pack_diagnostics.csv`  
`outputs/audit/reproducibility_pack.zip`

Additional manifest outputs:

`data/processed/reports/reproducibility_file_manifest.parquet`  
`data/processed/reports/reproducibility_file_manifest.csv`

Diagnostics:

`outputs/diagnostics/reproducibility_pack_diagnostics.csv`

Pack contents v0:

- repository file manifest
- SHA256 checksums
- config snapshot
- dependency/environment snapshot
- report index
- pipeline run order
- audit bundle index
- pack diagnostics

By default, raw and generated data files are excluded from the file manifest to keep the audit bundle lightweight. Use `--include-data` when a data-inclusive manifest is needed.


## Testing v0 — end-to-end smoke runner

Run the full research pipeline on deterministic synthetic fixture data:

```bash
make run-e2e-smoke
```

Equivalent explicit command:

```bash
python scripts/13_run_smoke_pipeline.py
```

Outputs:

`outputs/smoke/e2e_smoke_v0.zip`  
`outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_pipeline_steps.csv`  
`outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_artifact_checks.csv`  
`outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_summary.csv`  
`outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_pipeline_report.md`  
`outputs/smoke/e2e_smoke_v0/outputs/smoke/smoke_status.json`

The smoke runner creates synthetic filings, synthetic text/fundamental feature layers, synthetic adjusted prices, then executes the critical downstream pipeline in order:

1. synthetic fixture generation
2. DFM mismatch features
3. model research panel
4. price return source
5. return targets
6. model dataset
7. walk-forward splits
8. baseline model trainer
9. model selection report
10. long-short decile portfolio
11. portfolio performance report
12. ablation study
13. final research verdict
14. reproducibility pack

The smoke test verifies that every critical artifact exists and has at least the expected number of rows or units.


## Operations v0 — live-data readiness checker

Before live-data execution, run:

```bash
make check-live-readiness
```

Strict/blocking mode:

```bash
make check-live-readiness-strict
```

Equivalent explicit commands:

```bash
python scripts/14_check_live_readiness.py
python scripts/14_check_live_readiness.py --fail-on-blocked
```

Outputs:

`data/processed/reports/live_data_readiness_report.parquet`  
`data/processed/reports/live_data_readiness_report.csv`  
`data/processed/reports/live_data_readiness_summary.csv`  
`outputs/reports/live_data_readiness_report.md`

Diagnostics:

`outputs/diagnostics/live_data_readiness_diagnostics.csv`

Checks v0:

- SEC source config exists
- SEC User-Agent is not a placeholder
- SEC User-Agent includes contact details
- raw SEC submissions directory exists
- raw SEC primary documents directory exists
- SEC Financial Statement Data Sets directory and files exist
- Loughran-McDonald dictionary directory and file exist
- raw adjusted price CSV exists
- raw adjusted price CSV schema has date, identifier, and adjusted close
- sector is available or warning is emitted
- price required fields are documented in config

Live execution should be blocked when `live_readiness_status == BLOCKED`.


## Operations v0 — live pipeline execution wrapper

Run live-data pipeline stages behind the readiness gate:

```bash
make run-live-pipeline
```

Dry-run the full live command sequence:

```bash
make run-live-pipeline-dry
```

Override readiness explicitly:

```bash
make run-live-pipeline-override
```

Equivalent explicit commands:

```bash
python scripts/15_run_live_pipeline.py --stage full-live
python scripts/15_run_live_pipeline.py --stage full-live --dry-run
python scripts/15_run_live_pipeline.py --stage full-live --override-readiness
```

Outputs:

`outputs/logs/live_pipeline_execution_log.csv`  
`outputs/logs/live_pipeline_execution_summary.csv`  
`outputs/reports/live_pipeline_execution_report.md`

Execution rule v0:

- readiness is refreshed before execution by default
- commands execute only when `live_readiness_status == READY`
- `READY_WITH_WARNINGS` and `BLOCKED` are blocked by default
- `--override-readiness` allows execution with explicit audit evidence
- `--dry-run` records the command sequence without executing
- every command row logs readiness status, override flag, dry-run flag, timestamps, return code, stdout/stderr tail, and status

Available stages:

- `raw-sec`
- `source-tables`
- `text`
- `xbrl`
- `features`
- `targets`
- `modeling`
- `portfolio`
- `reports`
- `full-live`


## Reporting v0 — data lineage graph

Generate a machine-readable lineage graph across raw inputs, processed artifacts, reports, and commands:

```bash
make build-data-lineage-graph
```

Equivalent explicit command:

```bash
python scripts/12_generate_reports.py   --layer data-lineage-graph-v0
```

Outputs:

`data/processed/reports/data_lineage_nodes.parquet`  
`data/processed/reports/data_lineage_nodes.csv`  
`data/processed/reports/data_lineage_edges.parquet`  
`data/processed/reports/data_lineage_edges.csv`  
`outputs/reports/data_lineage_map.md`

Diagnostics:

`outputs/diagnostics/data_lineage_graph_diagnostics.csv`

Lineage graph v0 includes:

- command nodes
- raw input nodes
- config nodes
- processed artifact nodes
- report nodes
- diagnostic/log/audit nodes
- `consumes` edges from artifacts to commands
- `produces` edges from commands to artifacts
- `runs_before` edges between sequential pipeline commands

The graph is designed for audit review, pipeline debugging, and dependency impact analysis.


## Operations v0 — schema contract registry

Validate critical live or smoke outputs against fixed schema contracts:

```bash
make validate-schema-contracts
```

Strict mode:

```bash
make validate-schema-contracts-strict
```

Validate the synthetic smoke output tree:

```bash
make validate-smoke-schema-contracts
```

Equivalent explicit commands:

```bash
python scripts/16_validate_schema_contracts.py
python scripts/16_validate_schema_contracts.py --fail-on-blockers
python scripts/16_validate_schema_contracts.py --base-dir outputs/smoke/e2e_smoke_v0
```

Outputs:

`data/processed/reports/schema_contract_registry.parquet`  
`data/processed/reports/schema_contract_registry.csv`  
`data/processed/reports/schema_contract_validation.parquet`  
`data/processed/reports/schema_contract_validation.csv`  
`data/processed/reports/schema_contract_summary.csv`  
`outputs/reports/schema_contract_validation_report.md`

Diagnostics:

`outputs/diagnostics/schema_contract_validation_diagnostics.csv`

Schema contract registry v0 covers critical artifacts across:

- raw price inputs
- feature tables
- model research panel
- return targets
- model datasets and splits
- baseline predictions
- model selection report
- portfolio holdings and returns
- portfolio performance summary
- ablation summary
- final verdict/evidence/criteria
- reproducibility manifest
- data lineage nodes/edges
- live readiness summary
- live execution log
- smoke summary

Quality gates include:

- artifact exists
- table is readable
- minimum row count
- required columns
- non-null columns
- numeric-compatible columns
- uniqueness checks
- allowed-value checks


## Reporting v0 — release checklist

Generate the final pre-publication release gate:

```bash
make build-release-checklist
```

Strict live-readiness mode:

```bash
make build-release-checklist-strict-live
```

Equivalent explicit commands:

```bash
python scripts/12_generate_reports.py --layer release-checklist-v0
python scripts/12_generate_reports.py --layer release-checklist-v0 --require-live-readiness
```

Outputs:

`data/processed/reports/release_checklist.parquet`  
`data/processed/reports/release_checklist.csv`  
`data/processed/reports/release_gate_summary.csv`  
`outputs/reports/release_checklist.md`

Diagnostics:

`outputs/diagnostics/release_checklist_diagnostics.csv`

Release checklist v0 combines:

- final research verdict
- end-to-end smoke status
- schema contract status
- data lineage node/edge availability
- reproducibility pack ZIP and manifest diagnostics
- live-data readiness status

Release statuses:

- `PASS`: every critical gate passed and there are no warnings
- `PASS_WITH_WARNINGS`: every critical gate passed, but non-critical warnings remain
- `BLOCKED`: at least one critical gate failed

By default, live-data readiness is reviewed but not critical for code-only publication. Use `--require-live-readiness` for strict live-data/publication release gating.


## Reporting v0 — publication package

Generate a sanitized public-facing release bundle:

```bash
make build-publication-package
```

Equivalent explicit command:

```bash
python scripts/12_generate_reports.py --layer publication-package-v0
```

Outputs:

`outputs/publication/publication_package_v0/`  
`outputs/publication/publication_package_v0.zip`  
`data/processed/reports/publication_manifest.parquet`  
`data/processed/reports/publication_manifest.csv`  
`data/processed/reports/publication_exclusions.csv`  
`data/processed/reports/publication_sanitization_checks.csv`

Diagnostics:

`outputs/diagnostics/publication_package_diagnostics.csv`

Publication package v0 includes:

- public README, protocol, verdict notes, changelog, and license
- final verdict report
- portfolio performance report
- model selection report
- ablation study report
- data lineage map
- schema contract validation report
- release checklist report
- final verdict/evidence/criteria CSVs
- release gate CSVs
- schema contract summary/registry
- lineage nodes/edges
- reproducibility index and pipeline run order

Excluded by design:

- raw SEC filings
- raw prices
- intermediate feature/model/target/source-table data
- execution logs
- private runtime outputs
- nested ZIP archives

The package writes a publication README, manifest, exclusions report, sanitization checks, diagnostics, and ZIP.


## Reporting v0 — public README polish

Generate or refresh the public-facing landing README inside the publication package:

```bash
make build-public-readme-polish
```

Equivalent explicit command:

```bash
python scripts/12_generate_reports.py --layer public-readme-polish-v0
```

Output:

`outputs/publication/publication_package_v0/PUBLICATION_README.md`

Diagnostics:

`outputs/diagnostics/public_readme_polish_diagnostics.csv`

The polished public README includes:

- concise research thesis
- current release status table
- Mermaid pipeline diagram
- audit controls included in the package
- reproduction commands
- live-data execution rule
- package contents summary
- excluded raw/private data explanation
- reviewer reading order

The publication package uses this polished README automatically when `make build-publication-package` runs.


## Reporting v0 — final archive freeze

Generate immutable release metadata for library storage:

```bash
make build-final-archive-freeze
```

Relaxed mode, allowing a `PASS_WITH_WARNINGS` release gate:

```bash
make build-final-archive-freeze-relaxed
```

Equivalent explicit commands:

```bash
python scripts/12_generate_reports.py --layer final-archive-freeze-v0
python scripts/12_generate_reports.py --layer final-archive-freeze-v0 --allow-release-gate-warning
```

Outputs:

`data/processed/reports/final_archive_freeze_manifest.parquet`  
`data/processed/reports/final_archive_freeze_manifest.csv`  
`data/processed/reports/final_archive_release_metadata.csv`  
`outputs/audit/final_archive_release_metadata.json`  
`outputs/audit/final_archive_frozen_manifest.json`  
`outputs/reports/final_archive_release_notes.md`

Diagnostics:

`outputs/diagnostics/final_archive_freeze_diagnostics.csv`

Final archive freeze v0 records:

- release version tag
- release title
- final freeze status
- final verdict status
- release checklist status
- schema contract status
- publication sanitization status
- live-readiness status
- required artifact inventory
- SHA256 checksums
- artifact sizes
- frozen timestamp
- environment metadata
- release notes for library storage

The archive is `FROZEN` only when the release version is valid, required artifacts exist, the publication package exists, and the configured release gate passes. Otherwise it is `BLOCKED`.
