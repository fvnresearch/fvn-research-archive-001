from fvn_dfm.data_ingestion.loughran_mcdonald import LMLexicon
from fvn_dfm.text.lm_dictionary_features import compute_lm_counts, compute_lm_feature_dict, tokenize_for_lm


def sample_lexicon():
    return LMLexicon(
        negative=frozenset({"LOSS", "WEAK"}),
        positive=frozenset({"GAIN"}),
        uncertainty=frozenset({"MAY", "UNCERTAIN"}),
        litigious=frozenset({"LITIGATION"}),
        constraining=frozenset({"RESTRICTED"}),
        strong_modal=frozenset({"MUST"}),
        weak_modal=frozenset({"MAY"}),
    )


def test_tokenize_for_lm():
    assert tokenize_for_lm("Loss, gain and may.") == ["LOSS", "GAIN", "AND", "MAY"]


def test_compute_lm_counts():
    counts = compute_lm_counts("Loss gain may litigation restricted must weak.", sample_lexicon())
    assert counts.word_count == 7
    assert counts.counts["negative"] == 2
    assert counts.counts["positive"] == 1
    assert counts.counts["uncertainty"] == 1
    assert counts.counts["litigious"] == 1
    assert counts.counts["constraining"] == 1
    assert counts.counts["strong_modal"] == 1
    assert counts.counts["weak_modal"] == 1


def test_compute_lm_feature_dict():
    features = compute_lm_feature_dict("Loss gain may.", sample_lexicon(), prefix="full_")
    assert features["full_lm_word_count"] == 3
    assert features["full_lm_negative_count"] == 1
    assert features["full_lm_positive_count"] == 1
    assert features["full_lm_uncertainty_count"] == 1
    assert features["full_lm_net_tone_count"] == 0
