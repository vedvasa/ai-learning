from contextlib import redirect_stdout
from io import StringIO
from unittest import TestCase

from ai_learning import main


class TestMain(TestCase):
    def test_main_prints_greeting(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            main()

        self.assertEqual(output.getvalue(), "Hello from ai-learning!\n")
