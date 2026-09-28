"""
Hindsight Cloud Client
Provides direct interaction with Vectorize.io Hindsight Cloud service:
- retain(): Ingests content into deal memory bank with fact extraction
- recall(): Queries memory bank with semantic, temporal, and keyword retrieval
- reflect(): Synthesizes high-level deal intelligence, playbooks, and retrospectives
"""

import os
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from datetime import datetime

DEFAULT_CLOUD_URL = "https://api.hindsight.vectorize.io"
DEFAULT_BANK_ID = "dealintel"

class HindsightCloudClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        bank_id: Optional[str] = None
    ):
        self.api_key = api_key or os.environ.get("HINDSIGHT_API_KEY", "")
        self.base_url = (base_url or os.environ.get("HINDSIGHT_API_URL", DEFAULT_CLOUD_URL)).rstrip("/")
        self.bank_id = bank_id or os.environ.get("HINDSIGHT_BANK_ID", DEFAULT_BANK_ID)

        if not self.api_key:
            # Check .env file if available
            env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            if os.path.exists(env_file):
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("HINDSIGHT_API_KEY="):
                            self.api_key = line.split("=", 1)[1].strip()
                        elif line.startswith("HINDSIGHT_BANK_ID="):
                            self.bank_id = line.split("=", 1)[1].strip()
                        elif line.startswith("HINDSIGHT_API_URL="):
                            self.base_url = line.split("=", 1)[1].strip().rstrip("/")

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{endpoint}"
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=body, headers=self._headers(), method=method)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp_data = resp.read().decode("utf-8")
                return json.loads(resp_data) if resp_data else {}
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            raise RuntimeError(f"Hindsight Cloud HTTP {e.code}: {err_body}")
        except Exception as e:
            raise RuntimeError(f"Hindsight Cloud connection error: {str(e)}")

    def ensure_bank_exists(self, bank_id: Optional[str] = None) -> Dict[str, Any]:
        target_bank = bank_id or self.bank_id
        payload = {
            "name": "DealIntel Sales Memory",
            "retain_mission": "Extract enterprise sales deal intelligence: account names, stakeholders, sentiment shifts, objections, competitor mentions, and commitments.",
            "reflect_mission": "Act as an elite Sales Operations manager and deal intelligence co-pilot. Synthesize deal history, win/loss patterns, objection counter-tactics, and pre-call briefings."
        }
        return self._request("PUT", f"/v1/default/banks/{target_bank}", payload)

    def retain(
        self,
        content: str,
        context: Optional[str] = None,
        document_id: Optional[str] = None,
        tags: Optional[List[str]] = None,
        timestamp: Optional[str] = None,
        bank_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Retains content into Hindsight Cloud memory bank.
        Automatically extracts semantic facts, entities, and temporal links.
        """
        target_bank = bank_id or self.bank_id
        item: Dict[str, Any] = {
            "content": content,
            "context": context or "enterprise_sales_deal_activity"
        }
        if document_id:
            item["document_id"] = document_id
        if tags:
            item["tags"] = tags
        if timestamp:
            item["timestamp"] = timestamp

        payload = {
            "items": [item],
            "async": False
        }
        return self._request("POST", f"/v1/default/banks/{target_bank}/memories", payload)

    def recall(
        self,
        query: str,
        tags: Optional[List[str]] = None,
        max_tokens: int = 4096,
        bank_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Queries Hindsight Cloud using hybrid search across semantic, keyword, graph, and temporal dimensions.
        """
        target_bank = bank_id or self.bank_id
        payload: Dict[str, Any] = {
            "query": query,
            "max_tokens": max_tokens
        }
        if tags:
            payload["tags"] = tags

        return self._request("POST", f"/v1/default/banks/{target_bank}/memories/recall", payload)

    def reflect(
        self,
        query: str,
        context: Optional[str] = None,
        bank_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Synthesizes high-level reasoning and actionable insights from retained deal memories.
        """
        target_bank = bank_id or self.bank_id
        payload = {
            "query": query,
            "context": context or "Enterprise deal intelligence analysis"
        }
        return self._request("POST", f"/v1/default/banks/{target_bank}/reflect", payload)
