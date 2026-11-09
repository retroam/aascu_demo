import tempfile
import unittest
from pathlib import Path

from env_config import load_chat_env


class ChatEnvironmentTests(unittest.TestCase):
    def load(self, content, environ=None):
        result = {} if environ is None else environ
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(content)
            load_chat_env(path, result)
        return result

    def test_loads_chat_only_and_preserves_overrides(self):
        result = self.load('export DO_MODEL_INFERENCE_KEY="test-value" # comment\n'
                           'DO_ACCESS_TOKEN=unrelated\nANTHROPIC_API_KEY=unrelated\n'
                           'SANDBOX_CHAT_MODEL=from-file\n',
                           {"SANDBOX_CHAT_MODEL": "process-model"})
        self.assertEqual(result, {"DO_MODEL_INFERENCE_KEY": "test-value",
                                  "SANDBOX_CHAT_MODEL": "process-model"})

    def test_no_interpolation_or_shell_execution(self):
        result = self.load("DO_MODEL_INFERENCE_KEY='$(echo nope)$HOME`id`'\n")
        self.assertEqual(result["DO_MODEL_INFERENCE_KEY"], '$(echo nope)$HOME`id`')

    def test_invalid_value_is_not_exposed_and_no_partial_load(self):
        result = {}
        with self.assertRaises(ValueError) as error:
            self.load('SANDBOX_CHAT_MODEL=valid\nDO_MODEL_INFERENCE_KEY="secret-value\n', result)
        self.assertNotIn("secret-value", str(error.exception))
        self.assertEqual(result, {})

    def test_missing_file_is_optional(self):
        with tempfile.TemporaryDirectory() as directory:
            result = {}
            load_chat_env(Path(directory) / ".env", result)
            self.assertEqual(result, {})
