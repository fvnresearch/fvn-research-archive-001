from pathlib import Path

def test_required_top_level_dirs_exist():
    root = Path(__file__).resolve().parents[2]
    for rel in ["configs", "data", "docs", "src/fvn_dfm", "scripts", "tests", "outputs", "reports", "logs"]:
        assert (root / rel).exists()
