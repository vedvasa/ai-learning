from __future__ import annotations

import os

from openai import (
    APIConnectionError,
    APIStatusError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

DEFAULT_MODEL = "gpt-5.6-luna"
CONNECTIVITY_MESSAGE = "OpenAI connection successful."


def _positive_number(
    name: str,
    default: str,
    cast: type[int] | type[float],
) -> int | float:
    raw_value = os.getenv(name, default)

    try:
        value = cast(raw_value)
    except ValueError as error:
        raise SystemExit(f"{name} must be a number, not {raw_value!r}.") from error

    if value <= 0:
        raise SystemExit(f"{name} must be greater than zero.")

    return value


def main() -> None:
    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is missing. Add it to the ignored local .env file."
        )

    model = os.getenv("OPENAI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    timeout = float(_positive_number("LLM_TIMEOUT_SECONDS", "30", float))
    max_output_tokens = int(
        _positive_number("LLM_MAX_OUTPUT_TOKENS", "64", int)
    )
    client = OpenAI(timeout=timeout, max_retries=2)

    try:
        response = client.responses.create(
            model=model,
            input=f"Reply with exactly: {CONNECTIVITY_MESSAGE}",
            max_output_tokens=max_output_tokens,
            reasoning={"effort": "none"},
            store=False,
        )
    except AuthenticationError as error:
        raise SystemExit(
            "OpenAI authentication failed. Check OPENAI_API_KEY."
        ) from error
    except RateLimitError as error:
        raise SystemExit(
            "OpenAI rejected the request because of a rate or spend limit."
        ) from error
    except APIConnectionError as error:
        raise SystemExit("Could not connect to the OpenAI API.") from error
    except APIStatusError as error:
        request_id = getattr(error, "request_id", None)
        request_details = f" Request ID: {request_id}." if request_id else ""
        raise SystemExit(
            f"OpenAI returned HTTP {error.status_code}.{request_details}"
        ) from error

    output = response.output_text.strip()
    if output != CONNECTIVITY_MESSAGE:
        raise SystemExit(f"OpenAI returned an unexpected response: {output!r}")

    print(f"{CONNECTIVITY_MESSAGE} Model: {response.model}.")
