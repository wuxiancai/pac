from pathlib import Path
import wave

import pytest

from pac_poc.asr import ASREvent
from pac_poc.asr_evaluation import (
    character_error_rate,
    character_edit_distance,
    normalize_asr_text,
    score_asr_samples,
)
from scripts.evaluate_synthetic_asr_poc import recognize_sample, resolve_sample_audio


def test_normalize_asr_text_ignores_punctuation_and_whitespace() -> None:
    assert normalize_asr_text("你好，今天天气很好。 ") == "你好今天天气很好"
    assert normalize_asr_text("Hello, WORLD! 42") == "helloWORLD42".casefold()


def test_character_error_rate_ignores_latin_case() -> None:
    assert character_error_rate("Hello, World!", "HELLO WORLD") == 0.0


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


def test_recognize_sample_scores_every_final_segment(tmp_path: Path, monkeypatch) -> None:
    wav_path = tmp_path / "two-utterances.wav"
    with wave.open(str(wav_path), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(16_000)
        output.writeframes(b"\x01\x00" * 6_400)

    class FakeStreamingASR:
        def __init__(self, _recognizer, *, sample_rate_hz: int) -> None:
            assert sample_rate_hz == 16_000

        def accept(self, frame):
            if frame.sequence == 0:
                return ASREvent("final", "first segment", frame.sequence, "rev-1")
            return ASREvent("final", "second segment", frame.sequence, "rev-2")

    monkeypatch.setattr(
        "scripts.evaluate_synthetic_asr_poc.LocalStreamingASR", FakeStreamingASR
    )
    hypothesis, partials, finals = recognize_sample(wav_path, object(), tail_ms=0)

    assert hypothesis == "first segmentsecond segment"
    assert partials == 0
    assert finals == 2
