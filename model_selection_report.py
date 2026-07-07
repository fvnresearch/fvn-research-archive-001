from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from fvn_dfm.utils.paths import root


LM_CATEGORIES = [
    "negative",
    "positive",
    "uncertainty",
    "litigious",
    "constraining",
    "strong_modal",
    "weak_modal",
]


COLUMN_ALIASES = {
    "word": {"word", "words"},
    "negative": {"negative", "neg"},
    "positive": {"positive", "pos"},
    "uncertainty": {"uncertainty", "uncertain"},
    "litigious": {"litigious", "litigation"},
    "constraining": {"constraining", "constraint"},
    "strong_modal": {"strong_modal", "strong modal", "strongmodal"},
    "weak_modal": {"weak_modal", "weak modal", "weakmodal"},
}


@dataclass(frozen=True)
class LMLexicon:
    negative: frozenset[str]
    positive: frozenset[str]
    uncertainty: frozenset[str]
    litigious: frozenset[str]
    constraining: frozenset[str]
    strong_modal: frozenset[str]
    weak_modal: frozenset[str]

    def as_dict(self) -> dict[str, frozenset[str]]:
        return {
            "negative": self.negative,
            "positive": self.positive,
            "uncertainty": self.uncertainty,
            "litigious": self.litigious,
            "constraining": self.constraining,
            "strong_modal": self.strong_modal,
            "weak_modal": self.weak_modal,
        }


def normalize_word(value: str) -> str:
    return str(value or "").strip().upper()


def normalize_column_name(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def find_lm_dictionary_file(directory: str | Path) -> Path:
    p = Path(directory)
    if p.is_file():
        return p

    patterns = ["*.csv", "*.CSV", "*.xlsx", "*.xls", "*.txt"]
    files: list[Path] = []
    for pattern in patterns:
        files.extend(p.glob(pattern))

    if not files:
        raise FileNotFoundError(f"No Loughran-McDonald dictionary file found in {p}")

    files = sorted(files, key=lambda x: (x.suffix.lower() not in {".csv", ".txt"}, x.name.lower()))
    return files[0]


def _read_dictionary_file(path: str | Path) -> pd.DataFrame:
    p = Path(path)
    suffix = p.suffix.lower()

    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(p)

    if suffix == ".txt":
        try:
            return pd.read_csv(p, sep="\t")
        except Exception:
            return pd.read_csv(p)

    return pd.read_csv(p)


def canonicalize_lm_columns(df: pd.DataFrame) -> pd.DataFrame:
    normalized_to_original = {normalize_column_name(c): c for c in df.columns}
    rename: dict[str, str] = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = normalize_column_name(alias)
            if key in normalized_to_original:
                rename[normalized_to_original[key]] = canonical
                break

    if "word" not in rename.values():
        raise ValueError("LM dictionary must contain a Word column.")

    out = df.rename(columns=rename).copy()

    for category in LM_CATEGORIES:
        if category not in out.columns:
            out[category] = 0

    return out[["word", *LM_CATEGORIES]]


def _is_category_member(value) -> bool:
    if pd.isna(value):
        return False
    if isinstance(value, str):
        clean = value.strip()
        if not clean:
            return False
        if clean.upper() in {"0", "FALSE", "N", "NO"}:
            return False
        return True
    try:
        return float(value) != 0.0
    except Exception:
        return bool(value)


def build_lm_lexicon(df: pd.DataFrame) -> LMLexicon:
    canonical = canonicalize_lm_columns(df)
    words_by_category: dict[str, set[str]] = {c: set() for c in LM_CATEGORIES}

    for _, row in canonical.iterrows():
        word = normalize_word(row["word"])
        if not word:
            continue
        for category in LM_CATEGORIES:
            if _is_category_member(row[category]):
                words_by_category[category].add(word)

    return LMLexicon(
        negative=frozenset(words_by_category["negative"]),
        positive=frozenset(words_by_category["positive"]),
        uncertainty=frozenset(words_by_category["uncertainty"]),
        litigious=frozenset(words_by_category["litigious"]),
        constraining=frozenset(words_by_category["constraining"]),
        strong_modal=frozenset(words_by_category["strong_modal"]),
        weak_modal=frozenset(words_by_category["weak_modal"]),
    )


def load_lm_lexicon(path_or_dir: str | Path) -> LMLexicon:
    path = find_lm_dictionary_file(path_or_dir)
    df = _read_dictionary_file(path)
    return build_lm_lexicon(df)


def write_lm_summary(lexicon: LMLexicon, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"category": category, "word_count": len(words)} for category, words in lexicon.as_dict().items()]
    with p.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["category", "word_count"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Load Loughran-McDonald dictionary and write summary.")
    parser.add_argument("--dictionary-path", default="data/raw/dictionaries/loughran_mcdonald")
    parser.add_argument("--summary-output", default="outputs/diagnostics/loughran_mcdonald_summary.csv")
    args = parser.parse_args()

    lexicon = load_lm_lexicon(root() / args.dictionary_path)
    write_lm_summary(lexicon, root() / args.summary_output)


if __name__ == "__main__":
    main()
