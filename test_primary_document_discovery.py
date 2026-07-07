from pathlib import Path

import pandas as pd

from fvn_dfm.modeling.model_dataset import ModelDatasetConfig, build_model_dataset_v0


def test_build_model_dataset_v0_outputs(tmp_path: Path):
    panel = pd.DataFrame(
        [
            {
                "panel_row_id": "0000320193:0000320193-23-000106:aapl.htm",
                "cik": "320193",
                "cik10": "0000320193",
                "ticker": "AAPL",
                "sector": "Tech",
                "accession_number": "0000320193-23-000106",
                "primary_document": "aapl.htm",
                "accession_lineage_key": "0000320193:0000320193-23-000106:aapl.htm",
                "feature_asof_date": "2023-11-07",
                "panel_eligible": True,
                "panel_quality_flag": "YELLOW",
                "panel_quality_notes": "mismatch_quality_yellow",
                "panel_version": "MODEL_RESEARCH_PANEL_V0",
                "dfm_score_simple": -0.1,
                "downside_mismatch_score": 0.2,
                "upside_mismatch_score": 0.01,
                "fund_revenue": 1000.0,
                "fund_net_margin": 0.1,
                "text_full_lm_positive_share": 0.05,
            }
        ]
    )
    targets = pd.DataFrame(
        [
            {
                "panel_row_id": "0000320193:0000320193-23-000106:aapl.htm",
                "ticker": "AAPL",
                "sector": "Tech",
                "target_entry_date": "2023-11-07",
                "target_exit_date": "2024-02-02",
                "target_horizon_trading_days": 63,
                "forward_63d_raw_return": 0.02,
                "forward_63d_sector_return": 0.07,
                "forward_63d_sector_adjusted_return": -0.05,
                "target_available": True,
                "target_quality_flag": "YELLOW",
                "target_quality_notes": "low_sector_member_count=1",
                "target_version": "RETURN_TARGETS_V0",
            }
        ]
    )

    panel_path = tmp_path / "model_research_panel.csv"
    targets_path = tmp_path / "return_targets_asof.csv"
    panel.to_csv(panel_path, index=False)
    targets.to_csv(targets_path, index=False)

    config = ModelDatasetConfig(
        model_research_panel_path=panel_path,
        return_targets_path=targets_path,
        output_table_path=tmp_path / "model_dataset_v0.parquet",
        output_csv_path=tmp_path / "model_dataset_v0.csv",
        diagnostics_path=tmp_path / "model_dataset_v0_diagnostics.csv",
    )
    df = build_model_dataset_v0(config)

    assert len(df) == 1
    assert (tmp_path / "model_dataset_v0.csv").exists()
    assert (tmp_path / "model_dataset_v0_diagnostics.csv").exists()
    assert df.iloc[0]["model_dataset_eligible"] is True or df.iloc[0]["model_dataset_eligible"] == True
    assert df.iloc[0]["model_dataset_quality_flag"] == "GREEN"
    assert df.iloc[0]["y_forward_63d_sector_adjusted_return"] == -0.05
    assert "dfm_score_simple" in df.iloc[0]["model_feature_columns"]
