from __future__ import annotations

from dataclasses import dataclass


DEFAULT_MODEL = "gpt-5.6-sol"
DEFAULT_UPSTREAM_MODEL = "gpt-5.6-sol"


@dataclass(frozen=True)
class ModelInfo:
    id: str
    name: str
    context_window: int
    supports_reasoning_effort: bool


MODEL_CATALOG: tuple[ModelInfo, ...] = (
    ModelInfo("gpt-5.6-sol", "GPT-5.6 Sol", 272_000, True),
    ModelInfo("gpt-5.6-terra", "GPT-5.6 Terra", 272_000, True),
    ModelInfo("gpt-5.6-luna", "GPT-5.6 Luna", 272_000, True),
    ModelInfo("gpt-5.5", "GPT-5.5", 272_000, True),
    ModelInfo("gpt-5.4", "GPT-5.4", 272_000, True),
    ModelInfo("gpt-5.4-mini", "GPT-5.4 Mini", 272_000, True),
    ModelInfo("gpt-5.2", "GPT-5.2", 272_000, True),
    ModelInfo("grok-build", "Groc fallback via GPT-5.6 Sol", 272_000, True),
)


def upstream_model(model: str, fallback: str = DEFAULT_UPSTREAM_MODEL) -> str:
    return fallback if model == "grok-build" else model
