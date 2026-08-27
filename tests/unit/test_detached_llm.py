import unittest
from unittest.mock import patch, MagicMock
from minder.llm.openai_compatible import OpenAICompatibleLLM
class TestOpenAICompatibleLLM(unittest.TestCase):
    def test_init_config(self):
        llm = OpenAICompatibleLLM(
            base_url="http://localhost:11434/v1",
            api_key="ollama",
            model_name="qwen3.5:2b",
        )
        self.assertEqual(llm.base_url, "http://localhost:11434/v1")
        self.assertEqual(llm.model_name, "qwen3.5:2b")

    @patch("urllib.request.urlopen")
    def test_complete_text_mock(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.read.return_value = b'{"choices": [{"message": {"content": "Hello from Qwen3.5"}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        llm = OpenAICompatibleLLM(base_url="http://localhost:11434/v1")
        response = llm.complete_text("Say hello")
        self.assertEqual(response, "Hello from Qwen3.5")

if __name__ == "__main__":
    unittest.main()
