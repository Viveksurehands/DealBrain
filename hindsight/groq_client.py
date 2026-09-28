"""
Groq LLM Client for DealIntel
High-speed inference for deal fact extraction, pre-call briefs, and objection playbooks.
Enforces the zero-fabrication contract: never infer facts not grounded in Hindsight or input text.
"""

import os
import json
import time
import re
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

DEFAULT_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODELS = ["qwen/qwen3.8-27b", "openai/gpt-oss-120b", "openai/gpt-oss-20b"]

class GroqClient:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "")
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODELS[0])
        self.fallback_models = DEFAULT_MODELS

        if not self.api_key:
            env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            if os.path.exists(env_file):
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("GROQ_API_KEY="):
                            self.api_key = line.split("=", 1)[1].strip()
                        elif line.startswith("GROQ_MODEL="):
                            self.model = line.split("=", 1)[1].strip()

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 750
    ) -> str:
        """
        Executes chat completion on Groq with low temperature for factual precision.
        Includes automatic 429 rate-limit backoff and failover to alternative models.
        """
        if not self.api_key:
            raise ValueError("GROQ_API_KEY is not configured.")

        # Candidate models to try in order
        candidate_models = [self.model] + [m for m in self.fallback_models if m != self.model]

        last_error = None
        for current_model in candidate_models:
            for attempt in range(2):
                payload = {
                    "model": current_model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }

                req = urllib.request.Request(
                    DEFAULT_GROQ_URL,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "User-Agent": "DealIntel/1.0"
                    }
                )

                try:
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = json.loads(resp.read().decode("utf-8"))
                        return data["choices"][0]["message"]["content"]
                except urllib.error.HTTPError as e:
                    err = e.read().decode("utf-8")
                    last_error = f"Groq HTTP {e.code} ({current_model}): {err}"
                    if e.code == 429:
                        # Parse retry delay if provided
                        wait_match = re.search(r"try again in (\d+(?:\.\d+)?)s", err)
                        wait_time = float(wait_match.group(1)) if wait_match else 5.0
                        if wait_time <= 10.0 and attempt == 0:
                            time.sleep(wait_time + 0.5)
                            continue
                        # If wait is longer or already retried, break to try next fallback model
                        break
                    else:
                        break
                except Exception as e:
                    last_error = str(e)
                    break

        raise RuntimeError(f"All Groq inference candidates exhausted. Last error: {last_error}")
