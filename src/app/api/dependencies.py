from fastapi import Request

from app.providers.base import ProviderRegistry
from app.services.usage import UsageRecorder


def get_provider_registry(request: Request) -> ProviderRegistry:
    return request.app.state.provider_registry


def get_usage_recorder(request: Request) -> UsageRecorder:
    return request.app.state.usage_recorder
