from pathlib import Path

import pytest

from pac_poc.asr_evaluation import (
    character_error_rate,
    character_edit_distance,
    normalize_asr_text,
    score_asr_samples,
)
from scripts.evaluate_synthetic_asr_poc import resolve_sample_audio


def test_normalize_asr_text_ignores_punctuation_and_whitespace() -> None:
    assert normalize_asr_text("你好，今天天气很好。 ") == "你好今天天气很好"


def test_character_edit_distance_counts_insertions_deletions_and_substitutions() -> None:
    assert character_edit_distance("中文识别", "中文辨认") == 2
    assert character_edit_distance("abc", "ab") == 1
    assert character_edit_distance("ab", "abc") == 1


def test_character_error_rate_handles_empty_hypothesis() -> None:
    assert character_error_rate("你好", "") == 1.0
    assert character_error_rate("", "") == 0.0
    assert character_error_rate("", "a") == 1.0


def test_corpus_score_uses_weighted_character_error_rate() -> None:
    result = score_asr_samples(
        [
            ("你好，世界。", "你好世界"),
            ("今天天气很好", "今天天气很坏"),
        ]
    )

    assert result.sample_count == 2
    assert result.reference_chars == 10
    assert result.character_errors == 1
    assert result.weighted_cer == 0.1


def test_corpus_score_rejects_empty_sample_collection() -> None:
    try:
        score_asr_samples([])
    except ValueError as error:
        assert "at least one" in str(error)
    else:
        raise AssertionError("empty sample collection must be rejected")


def test_explicit_manifest_cannot_escape_its_directory() -> None:
    manifest = Path(__file__).resolve().parents[1] / ".poc-data" / "audio" / "manifest.json"

    with pytest.raises(ValueError, match="must stay beside"):
        resolve_sample_audio(manifest, "../../../../private.wav")
