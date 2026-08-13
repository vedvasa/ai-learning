import os
from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from ai_learning.anthropic_check import CONNECTIVITY_MESSAGE, main


class TestAnthropicConnectivityCheck(TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_requires_api_key(self) -> None:
        with self.assertRaisesRegex(SystemExit, "ANTHROPIC_API_KEY is missing"):
            main()

    @patch.dict(
        os.environ,
        {
            "ANTHROPIC_API_KEY": "test-key",
            "ANTHROPIC_MODEL": "claude-haiku-4-5-20251001",
            "LLM_TIMEOUT_SECONDS": "10",
            "LLM_MAX_OUTPUT_TOKENS": "64",
        },
        clear=True,
    )
    @patch("ai_learning.anthropic_check.Anthropic")
    def test_sends_minimal_message_request(self, anthropic_class: Mock) -> None:
        client = anthropic_class.return_value
        client.messages.create.return_value = SimpleNamespace(
            model="claude-haiku-4-5-20251001",
            content=[SimpleNamespace(type="text", text=CONNECTIVITY_MESSAGE)],
        )
        output = StringIO()

        with redirect_stdout(output):
            main()

        anthropic_class.assert_called_once_with(timeout=10.0, max_retries=2)
        client.messages.create.assert_called_once_with(
            model="claude-haiku-4-5-20251001",
            max_tokens=64,
            messages=[
                {
                    "role": "user",
                    "content": f"Reply with exactly: {CONNECTIVITY_MESSAGE}",
                }
            ],
        )
        self.assertEqual(
            output.getvalue(),
            "Anthropic connection successful. "
            "Model: claude-haiku-4-5-20251001.\n",
        )
