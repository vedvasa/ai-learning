from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.providers.base import ProviderName

MAX_PROMPT_CHARACTERS = 8_000


class GenerationRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    provider: ProviderName
    model: str = Field(min_length=1, max_length=200)
    prompt: str = Field(min_length=1, max_length=MAX_PROMPT_CHARACTERS)

    @field_validator("prompt")
    @classmethod
    def prompt_must_contain_text(cls, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("Prompt must contain non-whitespace text.")
        return prompt.strip()


class GenerationResponse(BaseModel):
    request_id: str
    text: str
    provider: ProviderName
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    finish_reason: str
    provider_request_id: str | None
    attempt_count: int = Field(ge=1)


class StreamStart(BaseModel):
    request_id: str
    provider: ProviderName
    model: str


class StreamDelta(BaseModel):
    text: str


class StreamCompletion(BaseModel):
    request_id: str
    provider: ProviderName
    model: str
    latency_ms: float
    input_tokens: int
    output_tokens: int
    finish_reason: str
    provider_request_id: str | None


class StreamFailure(BaseModel):
    code: str
    message: str
    request_id: str
