# Final Verdict

Status: Pending

No final verdict may be assigned until Modules 001–011 are complete and the Institutional Tear Sheet has been generated.

Allowed verdicts:

A — Archive Alpha Candidate  
B — Research Insight, Not Tradable Alpha  
C — Mechanism Rejected  
D — Inconclusive Due to Data Limitations


## Final research verdict v0

The repository now includes an executable verdict generator:

```bash
make build-final-verdict
```

This generates:

- `data/processed/reports/final_research_verdict.csv`
- `data/processed/reports/final_research_evidence.csv`
- `data/processed/reports/final_research_criteria.csv`
- `outputs/reports/final_research_verdict.md`

The verdict is deliberately conservative: the project only receives a `PASS` when every configured critical criterion passes.


## Reproducibility pack v0

The repository now includes a one-command audit pack:

```bash
make build-reproducibility-pack
```

This generates file manifests, SHA256 checksums, a config snapshot, report index, pipeline run order, and an audit ZIP at:

`outputs/audit/reproducibility_pack.zip`


## End-to-end smoke runner v0

The repository now includes a one-command end-to-end synthetic smoke run:

```bash
make run-e2e-smoke
```

The smoke runner executes the critical research chain on deterministic fixture data and verifies that all key artifacts are produced in order.


## Live-data readiness checker v0

The repository now includes a live-data gatekeeper:

```bash
make check-live-readiness
make check-live-readiness-strict
```

The strict target exits non-zero when live execution is blocked by missing compliance or source prerequisites.


## Live pipeline execution wrapper v0

The repository now includes a readiness-gated live execution wrapper:

```bash
make run-live-pipeline
make run-live-pipeline-dry
make run-live-pipeline-override
```

The wrapper blocks execution unless live readiness is `READY` or an explicit override is used, and logs every planned/executed command with readiness evidence.


## Data lineage graph v0

The repository now includes a machine-readable lineage graph:

```bash
make build-data-lineage-graph
```

This generates node and edge tables plus a Markdown lineage map connecting raw inputs, commands, processed artifacts, reports, logs, and audit outputs.


## Schema contract registry v0

The repository now includes fixed schema contracts for critical live and smoke artifacts:

```bash
make validate-schema-contracts
make validate-smoke-schema-contracts
```

The validator checks existence, readability, row counts, required columns, non-null fields, numeric compatibility, uniqueness, and allowed values.


## Release checklist v0

The repository now includes a final pre-publication release checklist:

```bash
make build-release-checklist
make build-release-checklist-strict-live
```

This combines final verdict, smoke status, schema contracts, lineage graph, reproducibility pack, and live-readiness evidence into one release-gate report.


## Publication package v0

The repository now includes a sanitized public-facing publication bundle:

```bash
make build-publication-package
```

The package includes final reports, release-gate evidence, lineage map, schema summaries, reproducibility index, and pipeline run order while excluding raw/private/intermediate data.


## Public README polish v0

The repository now generates a public-facing landing README for the publication package:

```bash
make build-public-readme-polish
```

The README includes thesis, pipeline diagram, audit controls, reproduction commands, exclusions, and reviewer reading order.


## Final archive freeze v0

The repository now includes an immutable final archive freeze layer:

```bash
make build-final-archive-freeze
```

This writes release metadata, artifact checksums, frozen audit manifest, and release notes for library storage.
