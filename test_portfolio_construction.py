from pathlib import Path

import pandas as pd

from fvn_dfm.data_ingestion.loughran_mcdonald import (
    build_lm_lexicon,
    load_lm_lexicon,
    normalize_word,
)


def test_normalize_word():
    assert normalize_word(" loss ") == "LOSS"


def test_build_lm_lexicon_from_dataframe():
    df = pd.DataFrame(
        {
            "Word": ["LOSS", "GAIN", "MAY", "LITIGATION", "RESTRICTED", "MUST"],
            "Negative": [2009, 0, 0, 0, 0, 0],
            "Positive": [0, 2009, 0, 0, 0, 0],
            "Uncertainty": [0, 0, 1, 0, 0, 0],
            "Litigious": [0, 0, 0, 1, 0, 0],
            "Constraining": [0, 0, 0, 0, 1, 0],
            "Strong_Modal": [0, 0, 0, 0, 0, 1],
            "Weak_Modal": [0, 0, 1, 0, 0, 0],
        }
    )
    lex = build_lm_lexicon(df)
    assert "LOSS" in lex.negative
    assert "GAIN" in lex.positive
    assert "MAY" in lex.uncertainty
    assert "MAY" in lex.weak_modal
    assert "MUST" in lex.strong_modal


def test_load_lm_lexicon_from_csv(tmp_path: Path):
    csv_path = tmp_path / "lm.csv"
    csv_path.write_text("""Word,Negative,Positive,Uncertainty,Litigious,Constraining,Strong_Modal,Weak_Modal
LOSS,2009,0,0,0,0,0,0
GAIN,0,2009,0,0,0,0,0
""", encoding="utf-8")
    lex = load_lm_lexicon(csv_path)
    assert "LOSS" in lex.negative
    assert "GAIN" in lex.positive
