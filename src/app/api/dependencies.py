from fastapi import Request, status

from app.core.errors import ApplicationError
from app.providers.base import ProviderRegistry
from app.services.retrieval import SemanticRetriever
from app.services.usage import UsageRecorder


def get_provider_registry(request: Request) -> ProviderRegistry:
    return request.app.state.provider_registry


def get_usage_recorder(request: Request) -> UsageRecorder:
    return request.app.state.usage_recorder


def get_semantic_retriever(request: Request) -> SemanticRetriever:
    retriever = request.app.state.semantic_retriever
    if retriever is None:
        raise ApplicationError(
            code="retrieval_not_configured",
            message="Semantic retrieval is not configured on this server.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return retriever
