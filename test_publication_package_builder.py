from pathlib import Path

import pandas as pd

from fvn_dfm.portfolio.portfolio_construction import PortfolioConstructionConfig, build_long_short_decile_portfolio


def test_build_long_short_decile_portfolio_outputs(tmp_path: Path):
    rows = []
    for month in ["2021-01", "2021-02", "2021-03"]:
        for i in range(30):
            rows.append(
                {
                    "walk_forward_fold_id": f"WF_{month}",
                    "walk_forward_role": "test",
                    "model_name": "gradient_boosting",
                    "model_version": "BASELINE_MODEL_TRAINER_V0",
                    "model_row_id": f"{month}_{i}",
                    "panel_row_id": f"{month}_{i}",
                    "cik": str(1000 + i),
                    "cik10": str(1000 + i).zfill(10),
                    "ticker": f"T{i}",
                    "sector": "Tech",
                    "accession_number": f"acc_{month}_{i}",
                    "primary_document": "doc.htm",
                    "feature_asof_date": f"{month}-15",
                    "target_column": "y_forward_63d_sector_adjusted_return",
                    "y_true": (i / 100) - 0.1,
                    "y_pred": i / 100,
                }
            )
    predictions = pd.DataFrame(rows)
    selection = pd.DataFrame(
        [
            {"model_name": "gradient_boosting", "model_selection_rank": 1, "is_primary_model": True},
            {"model_name": "ridge", "model_selection_rank": 2, "is_primary_model": False},
        ]
    )
    pred_path = tmp_path / "baseline_fold_predictions.csv"
    selection_path = tmp_path / "model_selection_report.csv"
    predictions.to_csv(pred_path, index=False)
    selection.to_csv(selection_path, index=False)

    config = PortfolioConstructionConfig(
        baseline_predictions_path=pred_path,
        model_selection_report_path=selection_path,
        holdings_output_table_path=tmp_path / "portfolio_holdings.parquet",
        holdings_output_csv_path=tmp_path / "portfolio_holdings.csv",
        returns_output_table_path=tmp_path / "portfolio_monthly_returns.parquet",
        returns_output_csv_path=tmp_path / "portfolio_monthly_returns.csv",
        diagnostics_path=tmp_path / "portfolio_construction_diagnostics.csv",
        min_names_per_rebalance=10,
        transaction_cost_bps=10.0,
    )
    holdings, returns = build_long_short_decile_portfolio(config)

    assert not holdings.empty
    assert len(returns) == 3
    assert (tmp_path / "portfolio_holdings.csv").exists()
    assert (tmp_path / "portfolio_monthly_returns.csv").exists()
    assert (tmp_path / "portfolio_construction_diagnostics.csv").exists()
    assert set(returns["portfolio_quality_flag"]) == {"GREEN"}
    assert all(returns["gross_exposure"] == 2.0)
    assert all(returns["net_exposure"] == 0.0)
