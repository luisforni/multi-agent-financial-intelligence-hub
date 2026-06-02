from __future__ import annotations

from typing import Any

import litellm

from shared.config import Settings

# Silently drop parameters unsupported by a given provider (e.g. cache_control on Ollama).
litellm.drop_params = True


def get_completion_kwargs(settings: Settings, model: str) -> dict[str, Any]:
    """Return provider-specific kwargs to pass to litellm.acompletion."""
    kwargs: dict[str, Any] = {}

    if model.startswith("ollama/"):
        kwargs["api_base"] = settings.llm_base_url
        kwargs["request_timeout"] = 360
    elif model.startswith("gemini/"):
        if settings.gemini_api_key:
            kwargs["api_key"] = settings.gemini_api_key
    elif model.startswith("groq/"):
        if settings.groq_api_key:
            kwargs["api_key"] = settings.groq_api_key
    elif model.startswith("mistral/"):
        if settings.mistral_api_key:
            kwargs["api_key"] = settings.mistral_api_key
    elif model.startswith("together_ai/"):
        if settings.together_api_key:
            kwargs["api_key"] = settings.together_api_key
    elif model.startswith(("openai/", "gpt-", "o1", "o3")):
        if settings.openai_api_key:
            kwargs["api_key"] = settings.openai_api_key
    elif model.startswith("anthropic/"):
        if settings.anthropic_api_key:
            kwargs["api_key"] = settings.anthropic_api_key

    return kwargs


def tool_call_to_dict(tc: Any) -> dict[str, Any]:
    """Serialize a LiteLLM tool-call object to a plain dict for message history."""
    return {
        "id": tc.id,
        "type": "function",
        "function": {
            "name": tc.function.name,
            "arguments": tc.function.arguments,
        },
    }
