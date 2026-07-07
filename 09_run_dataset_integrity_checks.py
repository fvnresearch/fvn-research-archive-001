from __future__ import annotations

import argparse

from fvn_dfm.data_ingestion.price_returns import PriceReturnIngestionConfig, build_price_return_source
from fvn_dfm.targets.return_targets import ReturnTargetConfig, build_return_targets
from fvn_dfm.utils.paths import root


def main() -> None:
    parser = argparse.ArgumentParser(description="Target construction entrypoint.")
    parser.add_argument(
        "--layer",
        choices=["price-return-source", "return-targets-asof"],
        required=True,
        help="Target/source layer to build.",
    )

    # Price source args
    parser.add_argument("--raw-price-path")

    # Target args
    parser.add_argument("--model-research-panel-path", default="data/processed/model/model_research_panel.csv")
    parser.add_argument("--price-return-source-path", default="data/processed/source_tables/price_return_source.csv")
    parser.add_argument("--horizon-trading-days", type=int, default=63)
    parser.add_argument("--min-sector-members", type=int, default=2)

    # Shared outputs
    parser.add_argument("--output-table")
    parser.add_argument("--output-csv")
    parser.add_argument("--diagnostics-path")
    args = parser.parse_args()

    if args.layer == "price-return-source":
        if not args.raw_price_path:
            raise SystemExit("--raw-price-path is required for price-return-source.")
        config = PriceReturnIngestionConfig(
            raw_price_path=root() / args.raw_price_path,
            output_table_path=root() / (args.output_table or "data/processed/source_tables/price_return_source.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/source_tables/price_return_source.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/price_return_source_diagnostics.csv"),
        )
        build_price_return_source(config)
        return

    if args.layer == "return-targets-asof":
        config = ReturnTargetConfig(
            model_research_panel_path=root() / args.model_research_panel_path,
            price_return_source_path=root() / args.price_return_source_path,
            output_table_path=root() / (args.output_table or "data/processed/targets/return_targets_asof.parquet"),
            output_csv_path=root() / (args.output_csv or "data/processed/targets/return_targets_asof.csv"),
            diagnostics_path=root() / (args.diagnostics_path or "outputs/diagnostics/return_targets_asof_diagnostics.csv"),
            horizon_trading_days=args.horizon_trading_days,
            min_sector_members=args.min_sector_members,
        )
        build_return_targets(config)
        return


if __name__ == "__main__":
    main()
