import os
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from ai_learning.openai_check import CONNECTIVITY_MESSAGE, main


class TestOpenAIConnectivityCheck(TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_requires_api_key(self) -> None:
        with self.assertRaisesRegex(SystemExit, "OPENAI_API_KEY is missing"):
            main()

    @patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_MODEL": "gpt-5.6-luna",
            "LLM_TIMEOUT_SECONDS": "10",
            "LLM_MAX_OUTPUT_TOKENS": "64",
        },
        clear=True,
    )
    @patch("ai_learning.openai_check.OpenAI")
    def test_sends_minimal_response_request(self, openai_class: Mock) -> None:
        client = openai_class.return_value
        client.responses.create.return_value = SimpleNamespace(
            model="gpt-5.6-luna",
            output_text=CONNECTIVITY_MESSAGE,
        )
        output = StringIO()

        with redirect_stdout(output):
            main()

        openai_class.assert_called_once_with(timeout=10.0, max_retries=2)
        client.responses.create.assert_called_once_with(
            model="gpt-5.6-luna",
            input=f"Reply with exactly: {CONNECTIVITY_MESSAGE}",
            max_output_tokens=64,
            reasoning={"effort": "none"},
            store=False,
        )
        self.assertEqual(
            output.getvalue(),
            "OpenAI connection successful. Model: gpt-5.6-luna.\n",
        )
