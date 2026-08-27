from __future__ import annotations

import json
import logging
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)


class OpenAICompatibleLLM:
    """Detached inference adapter for Ollama, standalone llama-server, vLLM, or OpenAI/Anthropic proxies.
    
    Operates without holding in-process Python GIL or llama_cpp locks.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        api_key: str = "ollama",
        model_name: str = "qwen3.5:2b",
        temperature: float = 0.1,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.timeout = timeout

    def complete_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        fallback: str = "",
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        req = urllib.request.Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choices = data.get("choices", [])
                if choices and "message" in choices[0]:
                    return str(choices[0]["message"].get("content", "")).strip()
                return fallback
        except Exception as exc:
            logger.warning("Detached LLM call to %s failed: %s", url, exc)
            return fallback
