from django.conf import settings

from .base import LLMError, LLMProvider, LLMRequest

__all__ = ["LLMError", "LLMProvider", "LLMRequest", "get_provider"]


def get_provider(name: str | None = None) -> LLMProvider:
    """Sozlamadagi (LLM_PROVIDER) provayderni qaytaradi."""
    from .mock import MockProvider
    from .providers import GeminiProvider, GroqProvider, OllamaProvider

    registry = {
        "gemini": GeminiProvider,
        "groq": GroqProvider,
        "ollama": OllamaProvider,
        "mock": MockProvider,
    }
    key = (name or settings.LLM_PROVIDER or "mock").lower()
    if key not in registry:
        raise LLMError(f"Noma'lum LLM provayder: {key!r}. Mumkin: {', '.join(registry)}")
    return registry[key]()
