from app.core.config import Settings
from app.providers.anthropic_provider import AnthropicProvider
from app.providers.base import Provider, ProviderRegistry
from app.providers.openai_provider import OpenAIProvider


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    providers: list[Provider] = []

    if settings.openai_api_key is not None:
        openai_api_key = settings.openai_api_key.get_secret_value().strip()
        if openai_api_key:
            providers.append(
                OpenAIProvider(
                    api_key=openai_api_key,
                    model=settings.openai_model,
                    timeout_seconds=settings.llm_timeout_seconds,
                    max_output_tokens=settings.llm_max_output_tokens,
                    triage_max_output_tokens=(
                        settings.triage_max_output_tokens
                    ),
                    answer_max_output_tokens=(
                        settings.rag_answer_max_output_tokens
                    ),
                )
            )

    if settings.anthropic_api_key is not None:
        anthropic_api_key = (
            settings.anthropic_api_key.get_secret_value().strip()
        )
        if anthropic_api_key:
            providers.append(
                AnthropicProvider(
                    api_key=anthropic_api_key,
                    model=settings.anthropic_model,
                    timeout_seconds=settings.llm_timeout_seconds,
                    max_output_tokens=settings.llm_max_output_tokens,
                    triage_max_output_tokens=(
                        settings.triage_max_output_tokens
                    ),
                    answer_max_output_tokens=(
                        settings.rag_answer_max_output_tokens
                    ),
                )
            )

    return ProviderRegistry(providers)
