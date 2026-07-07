from pathlib import Path

import pandas as pd

from fvn_dfm.portfolio.portfolio_construction import (
    PortfolioConstructionConfig,
    build_portfolio_diagnostics,
    build_portfolio_holdings_dataframe,
    build_portfolio_returns_dataframe,
    select_primary_model,
)


def make_predictions() -> pd.DataFrame:
    rows = []
    for month_idx, month in enumerate(["2021-01", "2021-02"]):
        for i in range(20):
            pred = i / 100
            y = pred * 0.5 - 0.02
            rows.append(
                {
                    "walk_forward_fold_id": f"WF000{month_idx+1}_{month.replace('-', '')}",
                    "walk_forward_role": "test",
                    "model_name": "elastic_net",
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
                    "y_true": y,
                    "y_pred": pred,
                }
            )
            # Add another model that must be ignored.
            rows.append(
                {
                    "walk_forward_fold_id": f"WF000{month_idx+1}_{month.replace('-', '')}",
                    "walk_forward_role": "test",
                    "model_name": "ridge",
                    "model_version": "BASELINE_MODEL_TRAINER_V0",
                    "model_row_id": f"ridge_{month}_{i}",
                    "panel_row_id": f"ridge_{month}_{i}",
                    "cik": str(1000 + i),
                    "cik10": str(1000 + i).zfill(10),
                    "ticker": f"R{i}",
                    "sector": "Tech",
                    "accession_number": f"ridge_acc_{month}_{i}",
                    "primary_document": "doc.htm",
                    "feature_asof_date": f"{month}-15",
                    "target_column": "y_forward_63d_sector_adjusted_return",
                    "y_true": y,
                    "y_pred": pred,
                }
            )
    return pd.DataFrame(rows)


def make_selection() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"model_name": "elastic_net", "model_selection_rank": 1, "is_primary_model": True},
            {"model_name": "ridge", "model_selection_rank": 2, "is_primary_model": False},
        ]
    )


def config(tmp_path: Path) -> PortfolioConstructionConfig:
    return PortfolioConstructionConfig(
        baseline_predictions_path=tmp_path / "baseline_fold_predictions.csv",
        model_selection_report_path=tmp_path / "model_selection_report.csv",
        holdings_output_table_path=tmp_path / "portfolio_holdings.parquet",
        holdings_output_csv_path=tmp_path / "portfolio_holdings.csv",
        returns_output_table_path=tmp_path / "portfolio_monthly_returns.parquet",
        returns_output_csv_path=tmp_path / "portfolio_monthly_returns.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
        min_names_per_rebalance=10,
        transaction_cost_bps=10.0,
    )


def write_inputs(tmp_path: Path):
    make_predictions().to_csv(tmp_path / "baseline_fold_predictions.csv", index=False)
    make_selection().to_csv(tmp_path / "model_selection_report.csv", index=False)


def test_select_primary_model():
    assert select_primary_model(make_selection()) == "elastic_net"


def test_build_portfolio_holdings_dataframe(tmp_path: Path):
    write_inputs(tmp_path)
    holdings = build_portfolio_holdings_dataframe(config(tmp_path))
    assert not holdings.empty
    selected = holdings[holdings["portfolio_leg"].isin(["long", "short"])]
    assert set(selected["primary_model_name"]) == {"elastic_net"}
    assert "ridge" not in set(selected["model_name"])
    for _, group in selected.groupby("rebalance_period"):
        assert round(group["portfolio_weight"].sum(), 12) == 0.0
        assert round(group["portfolio_weight"].abs().sum(), 12) == 2.0
        assert (group["portfolio_leg"] == "long").sum() == 2
        assert (group["portfolio_leg"] == "short").sum() == 2


def test_build_portfolio_returns_dataframe(tmp_path: Path):
    write_inputs(tmp_path)
    cfg = config(tmp_path)
    holdings = build_portfolio_holdings_dataframe(cfg)
    returns = build_portfolio_returns_dataframe(holdings, cfg)
    assert len(returns) == 2
    assert all(returns["gross_exposure"] == 2.0)
    assert all(returns["net_exposure"] == 0.0)
    assert returns.iloc[0]["portfolio_turnover"] == 1.0
    assert returns.iloc[0]["transaction_cost_return"] == 0.001
    assert returns.iloc[0]["portfolio_net_return"] == returns.iloc[0]["portfolio_gross_return"] - 0.001


def test_portfolio_diagnostics(tmp_path: Path):
    write_inputs(tmp_path)
    cfg = config(tmp_path)
    holdings = build_portfolio_holdings_dataframe(cfg)
    returns = build_portfolio_returns_dataframe(holdings, cfg)
    diagnostics = build_portfolio_diagnostics(holdings, returns)
    assert "holding_rows" in set(diagnostics["diagnostic"])
    assert "mean_net_return" in set(diagnostics["diagnostic"])
