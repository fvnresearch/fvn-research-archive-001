from __future__ import annotations

import argparse

from fvn_dfm.features.comparable_deltas import ComparableDeltasConfig, build_comparable_period_deltas
from fvn_dfm.features.fundamental_composites import FundamentalCompositeConfig, build_fundamental_stress_improvement
from fvn_dfm.features.fundamental_features import FundamentalFeaturesConfig, build_fundamental_features_asof
from fvn_dfm.features.mismatch_features import MismatchFeaturesConfig, build_mismatch_features_asof
from fvn_dfm.features.text_features import TextFeaturesConfig, build_text_features_asof
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(description="Feature build entrypoint.")
    parser.add_argument(
        "--layer",
        choices=[
            "text-features-asof",
            "fundamental-features-asof",
            "fundamental-delta-features-asof",
            "fundamental-composite-features-asof",
            "mismatch-features-asof",
        ],
        required=True,
        help="Feature layer to build.",
    )

    # Text feature args
    parser.add_argument("--filing-text-raw-path", default="data/processed/source_tables/filing_text_raw.csv")
    parser.add_argument("--filing-section-text-path", default="data/processed/source_tables/filing_section_text.csv")
    parser.add_argument("--lm-dictionary-path", default="data/raw/dictionaries/loughran_mcdonald")
    parser.add_argument("--text-features-path", default="data/processed/features/text_features_asof.csv")

    # Fundamental feature args
    parser.add_argument("--accounting-fact-selected-path", default="data/processed/source_tables/accounting_fact_selected.csv")
    parser.add_argument("--fundamental-features-path", default="data/processed/features/fundamental_features_asof.csv")
    parser.add_argument("--fundamental-delta-features-path", default="data/processed/features/fundamental_delta_features_asof.csv")
    parser.add_argument("--fundamental-composite-features-path", default="data/processed/features/fundamental_composite_features_asof.csv")
    parser.add_argument("--min-valid-stress-components", type=int, default=6)
    parser.add_argument("--min-valid-improvement-components", type=int, default=6)
    parser.add_argument("--component-clip-abs", type=float, default=5.0)

    # Mismatch args
    parser.add_argument("--min-downside-components", type=int, default=8)
    parser.add_argument("--min-upside-components", type=int, default=6)

    # Shared as-of/output args
    parser.add_argument("--filing-availability-path", default="data/processed/point_in_time/filing_availability.csv")
    parser.add_argument("--output-table")
    parser.add_argument("--output-csv")
    parser.add_argument("--diagnostics-path")

    args = parser.parse_args()

    if args.layer == "text-features-asof":
        config = TextFeaturesConfig(
            filing_text_raw_path=root() / args.filing_text_raw_path,
            filing_section_text_path=root() / args.filing_section_text_path,
            filing_availability_path=root() / args.filing_availability_path if args.filing_availability_path else None,
            lm_dictionary_path=root() / args.lm_dictionary_path,
            output_table_path=root() / (args.output_table or "data/processed/features/text_features_asof.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/features/text_features_asof.csv"),
        )
        build_text_features_asof(config)
        return

    if args.layer == "fundamental-features-asof":
        config = FundamentalFeaturesConfig(
            accounting_fact_selected_path=root() / args.accounting_fact_selected_path,
            filing_availability_path=root() / args.filing_availability_path if args.filing_availability_path else None,
            output_table_path=root() / (args.output_table or "data/processed/features/fundamental_features_asof.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/features/fundamental_features_asof.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/fundamental_features_asof_diagnostics.csv"),
        )
        build_fundamental_features_asof(config)
        return

    if args.layer == "fundamental-delta-features-asof":
        config = ComparableDeltasConfig(
            fundamental_features_asof_path=root() / args.fundamental_features_path,
            output_table_path=root() / (args.output_table or "data/processed/features/fundamental_delta_features_asof.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/features/fundamental_delta_features_asof.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/fundamental_delta_features_asof_diagnostics.csv"),
        )
        build_comparable_period_deltas(config)
        return

    if args.layer == "fundamental-composite-features-asof":
        config = FundamentalCompositeConfig(
            fundamental_delta_features_path=root() / args.fundamental_delta_features_path,
            output_table_path=root() / (args.output_table or "data/processed/features/fundamental_composite_features_asof.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/features/fundamental_composite_features_asof.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/fundamental_composite_features_asof_diagnostics.csv"),
            min_valid_stress_components=args.min_valid_stress_components,
            min_valid_improvement_components=args.min_valid_improvement_components,
            component_clip_abs=args.component_clip_abs,
        )
        build_fundamental_stress_improvement(config)
        return

    if args.layer == "mismatch-features-asof":
        config = MismatchFeaturesConfig(
            fundamental_composite_features_path=root() / args.fundamental_composite_features_path,
            text_features_path=root() / args.text_features_path,
            output_table_path=root() / (args.output_table or "data/processed/features/mismatch_features_asof.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/features/mismatch_features_asof.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/mismatch_features_asof_diagnostics.csv"),
            min_downside_components=args.min_downside_components,
            min_upside_components=args.min_upside_components,
        )
        build_mismatch_features_asof(config)
        return


if __name__ == "__main__":
    main()
