"""Bundled, evidence-backed capabilities for exact Beta model identifiers."""

from importlib.resources import files

from .model_capabilities import ModelCapabilityRegistry


def load_beta_capability_registry() -> ModelCapabilityRegistry:
    manifest = files("pac_poc").joinpath("beta_model_capabilities.json").read_text(
        encoding="utf-8"
    )
    return ModelCapabilityRegistry.from_json(manifest)
