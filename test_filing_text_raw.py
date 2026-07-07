from pathlib import Path
import yaml

def test_all_config_files_parse():
    root = Path(__file__).resolve().parents[2]
    configs = sorted((root / "configs").glob("*.yaml"))
    assert len(configs) == 13
    for cfg in configs:
        with cfg.open("r", encoding="utf-8") as f:
            assert yaml.safe_load(f) is not None
