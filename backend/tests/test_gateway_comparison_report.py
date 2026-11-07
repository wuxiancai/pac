from pathlib import Path


REPORT = (
    Path(__file__).parents[2]
    / "docs"
    / "poc"
    / "phase0-gateway-comparison.md"
)


def test_gateway_comparison_covers_baseline_candidates_and_decision_boundary() -> None:
    report = REPORT.read_text(encoding="utf-8")

    for candidate in ("LiteLLM", "Bifrost", "Portkey"):
        assert candidate in report

    for required in (
        "Policy Engine",
        "Consent Manager",
        "L3",
        "Keychain",
        "默认拒绝",
        "ADR-020",
        "未定案",
        "本机",
    ):
        assert required in report


def test_gateway_comparison_uses_first_party_sources() -> None:
    report = REPORT.read_text(encoding="utf-8")

    for source in (
        "docs.litellm.ai",
        "github.com/maximhq/bifrost",
        "docs.getbifrost.ai",
        "github.com/Portkey-AI/gateway",
    ):
        assert source in report
