"""
Unit tests for HindsightCloudClient
"""

import unittest
from unittest.mock import patch, MagicMock
from hindsight.cloud_client import HindsightCloudClient

class TestHindsightCloudClient(unittest.TestCase):
    def test_initialization_with_explicit_params(self):
        client = HindsightCloudClient(
            api_key="test_key_123",
            base_url="https://api.test.vectorize.io",
            bank_id="test_bank"
        )
        self.assertEqual(client.api_key, "test_key_123")
        self.assertEqual(client.base_url, "https://api.test.vectorize.io")
        self.assertEqual(client.bank_id, "test_bank")

    @patch("urllib.request.urlopen")
    def test_retain_request_payload(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"status": "ok"}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = HindsightCloudClient(api_key="mock_key", bank_id="dealintel")
        resp = client.retain(content="Call with Acme CFO on pricing", tags=["acc_acme_001"])

        self.assertEqual(resp, {"status": "ok"})
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/v1/default/banks/dealintel/memories", req.full_url)
        self.assertEqual(req.headers["Authorization"], "Bearer mock_key")

    @patch("urllib.request.urlopen")
    def test_recall_request_payload(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = b'{"results": []}'
        mock_urlopen.return_value.__enter__.return_value = mock_response

        client = HindsightCloudClient(api_key="mock_key", bank_id="dealintel")
        resp = client.recall(query="Pricing objections Acme")

        self.assertEqual(resp, {"results": []})
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertIn("/v1/default/banks/dealintel/memories/recall", req.full_url)
