from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class ASREvaluationScore:
    sample_count: int
    reference_chars: int
    hypothesis_chars: int
    character_errors: int
    weighted_cer: float


def normalize_asr_text(text: str) -> str:
    """Keep Unicode letters and numbers; ignore punctuation and whitespace."""
    return "".join(
        character
        for character in text
        if unicodedata.category(character)[0] in {"L", "N"}
    )


def character_edit_distance(reference: str, hypothesis: str) -> int:
    if len(reference) < len(hypothesis):
        reference, hypothesis = hypothesis, reference
    previous = list(range(len(hypothesis) + 1))
    for reference_index, reference_character in enumerate(reference, 1):
        current = [reference_index]
        for hypothesis_index, hypothesis_character in enumerate(hypothesis, 1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[hypothesis_index] + 1,
                    previous[hypothesis_index - 1]
                    + (reference_character != hypothesis_character),
                )
            )
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    normalized_reference = normalize_asr_text(reference)
    normalized_hypothesis = normalize_asr_text(hypothesis)
    if not normalized_reference:
        return 0.0 if not normalized_hypothesis else 1.0
    return character_edit_distance(
        normalized_reference, normalized_hypothesis
    ) / len(normalized_reference)


def score_asr_samples(samples: Sequence[tuple[str, str]]) -> ASREvaluationScore:
    if not samples:
        raise ValueError("at least one ASR evaluation sample is required")
    reference_chars = 0
    hypothesis_chars = 0
    character_errors = 0
    for reference, hypothesis in samples:
        normalized_reference = normalize_asr_text(reference)
        normalized_hypothesis = normalize_asr_text(hypothesis)
        reference_chars += len(normalized_reference)
        hypothesis_chars += len(normalized_hypothesis)
        character_errors += character_edit_distance(
            normalized_reference, normalized_hypothesis
        )
    weighted_cer = (
        character_errors / reference_chars if reference_chars else float(character_errors > 0)
    )
    return ASREvaluationScore(
        sample_count=len(samples),
        reference_chars=reference_chars,
        hypothesis_chars=hypothesis_chars,
        character_errors=character_errors,
        weighted_cer=weighted_cer,
    )
