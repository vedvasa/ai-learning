from fastapi import Request

from app.providers.base import ProviderRegistry


def get_provider_registry(request: Request) -> ProviderRegistry:
    return request.app.state.provider_registry
