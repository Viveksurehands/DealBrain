"""
Unit tests for GroqClient
"""

import unittest
from unittest.mock import patch, MagicMock
from hindsight.groq_client import GroqClient

class TestGroqClient(unittest.TestCase):
    def test_initialization_with_explicit_params(self):
        client = GroqClient(api_key="mock_key", model="test-model")
        self.assertEqual(client.api_key, "mock_key")
        self.assertEqual(client.model, "test-model")

    @patch("urllib.request.urlopen")
    def test_chat_completion_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"choices": [{"message": {"content": "Tactics ready"}}]}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = GroqClient(api_key="mock_key", model="test-model")
        res = client.chat_completion([{"role": "user", "content": "Counter tactic for pricing"}])

        self.assertEqual(res, "Tactics ready")
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertIn("api.groq.com", req.full_url)
        self.assertEqual(req.headers["Authorization"], "Bearer mock_key")
