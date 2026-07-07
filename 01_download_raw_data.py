import argparse
from pathlib import Path
import yaml

REQUIRED_CONFIGS = [
    "00_project.yaml",
    "01_data_sources.yaml",
    "02_universe.yaml",
    "03_pipeline.yaml",
    "04_features.yaml",
    "05_model.yaml",
    "06_oos_engine.yaml",
    "07_portfolio.yaml",
    "08_baselines.yaml",
    "09_ablations.yaml",
    "10_failure_tests.yaml",
    "11_tearsheet.yaml",
    "12_verdict.yaml",
]

REQUIRED_DIRS = [
    "configs",
    "data/raw",
    "data/interim",
    "data/processed",
    "data/manifests",
    "docs/modules",
    "src/fvn_dfm",
    "scripts",
    "tests",
    "outputs",
    "reports",
    "logs",
]

def check_configs(root: Path) -> None:
    for name in REQUIRED_CONFIGS:
        path = root / "configs" / name
        if not path.exists():
            raise FileNotFoundError(f"Missing config: {path}")
        with path.open("r", encoding="utf-8") as f:
            yaml.safe_load(f)
    print("Config check passed.")

def audit_skeleton(root: Path) -> None:
    for rel in REQUIRED_DIRS:
        path = root / rel
        if not path.exists():
            raise FileNotFoundError(f"Missing directory: {path}")
    print("Skeleton audit passed.")

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-configs", action="store_true")
    parser.add_argument("--audit-skeleton", action="store_true")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]

    if args.check_configs:
        check_configs(root)
    if args.audit_skeleton:
        audit_skeleton(root)
    if not args.check_configs and not args.audit_skeleton:
        parser.print_help()

if __name__ == "__main__":
    main()
