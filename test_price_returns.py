from pathlib import Path

import pandas as pd

from fvn_dfm.modeling.model_dataset import (
    ModelDatasetConfig,
    build_model_dataset_dataframe,
    build_model_dataset_diagnostics,
    candidate_model_feature_columns,
    join_panel_and_targets,
)


def config(tmp_path: Path) -> ModelDatasetConfig:
    return ModelDatasetConfig(
        model_research_panel_path=tmp_path / "model_research_panel.csv",
        return_targets_path=tmp_path / "return_targets_asof.csv",
        output_table_path=tmp_path / "model_dataset_v0.parquet",
        output_csv_path=tmp_path / "model_dataset_v0.csv",
        diagnostics_path=tmp_path / "diagnostics.csv",
    )


def make_panel() -> pd.DataFrame:
    return pd.DataFrame(
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
                "panel_quality_flag": "GREEN",
                "panel_quality_notes": "",
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


def make_targets(*, target_available=True, target_quality="GREEN", label=-0.05) -> pd.DataFrame:
    return pd.DataFrame(
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
                "target_entry_date": "2023-11-07",
                "target_exit_date": "2024-02-02",
                "target_horizon_trading_days": 63,
                "forward_63d_raw_return": 0.02,
                "forward_63d_sector_return": 0.07,
                "forward_63d_sector_adjusted_return": label,
                "target_available": target_available,
                "target_quality_flag": target_quality,
                "target_quality_notes": "",
                "target_version": "RETURN_TARGETS_V0",
            }
        ]
    )


def test_join_panel_and_targets():
    joined = join_panel_and_targets(make_panel(), make_targets())
    assert len(joined) == 1
    assert joined.iloc[0]["dfm_score_simple"] == -0.1
    assert joined.iloc[0]["forward_63d_sector_adjusted_return"] == -0.05


def test_candidate_model_feature_columns_excludes_targets():
    joined = join_panel_and_targets(make_panel(), make_targets())
    features = candidate_model_feature_columns(joined)
    assert "dfm_score_simple" in features
    assert "downside_mismatch_score" in features
    assert "fund_revenue" in features
    assert "text_full_lm_positive_share" in features
    assert "forward_63d_sector_adjusted_return" not in features
    assert "target_horizon_trading_days" not in features


def test_build_model_dataset_dataframe(tmp_path: Path):
    make_panel().to_csv(tmp_path / "model_research_panel.csv", index=False)
    make_targets().to_csv(tmp_path / "return_targets_asof.csv", index=False)

    df = build_model_dataset_dataframe(config(tmp_path))
    assert len(df) == 1
    row = df.iloc[0]
    assert row["model_row_id"] == "0000320193:0000320193-23-000106:aapl.htm"
    assert row["y_forward_63d_sector_adjusted_return"] == -0.05
    assert row["y_forward_63d_raw_return"] == 0.02
    assert row["model_dataset_eligible"] is True or row["model_dataset_eligible"] == True
    assert row["model_dataset_quality_flag"] == "GREEN"
    assert row["sample_weight"] == 1.0
    assert "dfm_score_simple" in row["model_feature_columns"]
    assert row["lineage_model_research_panel_version"] == "MODEL_RESEARCH_PANEL_V0"
    assert row["lineage_return_target_version"] == "RETURN_TARGETS_V0"


def test_missing_target_is_red(tmp_path: Path):
    make_panel().to_csv(tmp_path / "model_research_panel.csv", index=False)
    make_targets(target_available=False, target_quality="RED", label="").to_csv(tmp_path / "return_targets_asof.csv", index=False)

    df = build_model_dataset_dataframe(config(tmp_path))
    row = df.iloc[0]
    assert row["model_dataset_eligible"] is False or row["model_dataset_eligible"] == False
    assert row["model_dataset_quality_flag"] == "RED"
    assert "target_not_available" in row["model_dataset_quality_notes"]
    assert "missing_primary_label_forward_63d_sector_adjusted_return" in row["model_dataset_quality_notes"]
    assert row["sample_weight"] == 0.0


def test_build_model_dataset_diagnostics(tmp_path: Path):
    make_panel().to_csv(tmp_path / "model_research_panel.csv", index=False)
    make_targets().to_csv(tmp_path / "return_targets_asof.csv", index=False)
    df = build_model_dataset_dataframe(config(tmp_path))
    diag = build_model_dataset_diagnostics(df)
    assert "rows" in set(diag["diagnostic"])
    assert "eligible_rows" in set(diag["diagnostic"])
    assert "label_nonmissing_rows" in set(diag["diagnostic"])
