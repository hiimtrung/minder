from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
from typing import Any

from minder.graph.state import GraphState
from minder.runtime import load_attr, module_available

_RUNTIME_LOG_MARKERS = (
    "Using chat eos_token:",
    "Using chat bos_token:",
    "llama_perf_context_print:",
    "~llama_context:",
    "ggml_metal_free:",
)

_CHAT_TEMPLATE_MARKERS = (
    "{{- '<turn|>\\n' -}}",
    "{%- if add_generation_prompt -%}",
    "{%- endif -%}",
    "{%- endfor -%}",
)


class LocalModelLLM:
    def __init__(
        self,
        model_path: str,
        fail: bool = False,
        runtime: str = "mock",
        context_length: int = 4096,
    ) -> None:
        self._model_path = model_path
        self._fail = fail
        self._runtime = runtime
        self._context_length = max(512, context_length)
        self._client: Any | None = None

    @property
    def runtime(self) -> str:
        runtime = self._runtime
        model_exists = Path(self._model_path).expanduser().exists()
        if runtime == "auto":
            return (
                "llama_cpp"
                if model_exists and module_available("llama_cpp")
                else "mock"
            )
        return runtime

    def generate(self, state: GraphState) -> dict[str, object]:
        if self._fail:
            raise RuntimeError("Local model unavailable")

        runtime = self.runtime

        source_paths = [doc["path"] for doc in state.reranked_docs[:3]]
        guidance = state.workflow_context.get("guidance", "")
        text = (
            f"{guidance}\n"
            f"Plan intent: {state.plan.get('intent', 'unknown')}.\n"
            f"Answer: grounded response for '{state.query}'.\n"
            f"Sources: {', '.join(source_paths) if source_paths else 'none'}."
        )
        if runtime == "llama_cpp":
            text = self._generate_with_llama_cpp(state, fallback=text)

        return {
            "text": text,
            "sources": source_paths,
            "provider": "local_llm",
            "model": "gemma-4-e2b-it",
            "model_path": self._model_path,
            "runtime": runtime,
            "stream": [line for line in text.splitlines() if line],
        }

    def stream_generate(
        self, state: GraphState
    ) -> Generator[dict[str, object], None, None]:
        if self._fail:
            raise RuntimeError("Local model unavailable")

        runtime = self.runtime
        source_paths = [doc["path"] for doc in state.reranked_docs[:3]]
        guidance = state.workflow_context.get("guidance", "")
        fallback = (
            f"{guidance}\n"
            f"Plan intent: {state.plan.get('intent', 'unknown')}.\n"
            f"Answer: grounded response for '{state.query}'.\n"
            f"Sources: {', '.join(source_paths) if source_paths else 'none'}."
        )

        if runtime != "llama_cpp":
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            yield {
                "type": "result",
                "result": {
                    "text": fallback,
                    "sources": source_paths,
                    "provider": "local_llm",
                    "model": "gemma-4-e2b-it",
                    "model_path": self._model_path,
                    "runtime": runtime,
                    "stream": [fallback] if fallback else [],
                },
            }
            return

        client = self._llama_client()
        if client is None:
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            yield {
                "type": "result",
                "result": {
                    "text": fallback,
                    "sources": source_paths,
                    "provider": "local_llm",
                    "model": "gemma-4-e2b-it",
                    "model_path": self._model_path,
                    "runtime": runtime,
                    "stream": [fallback] if fallback else [],
                },
            }
            return

        reasoning_output = getattr(state, "reasoning_output", {}) or {}
        prompt = str(reasoning_output.get("prompt") or state.query)
        deltas: list[str] = []
        try:
            for delta in self._stream_with_llama_cpp(
                client,
                prompt=prompt,
                max_tokens=256,
                temperature=0.1,
            ):
                cleaned_delta = self._clean_stream_delta(delta)
                if not cleaned_delta:
                    continue
                deltas.append(cleaned_delta)
                yield {"type": "chunk", "delta": cleaned_delta}
        except Exception:
            if fallback:
                yield {"type": "chunk", "delta": fallback}
            deltas = [fallback] if fallback else []

        text = self._clean_generated_text("".join(deltas)) or fallback
        yield {
            "type": "result",
            "result": {
                "text": text,
                "sources": source_paths,
                "provider": "local_llm",
                "model": "gemma-4-e2b-it",
                "model_path": self._model_path,
                "runtime": runtime,
                "stream": deltas if deltas else ([text] if text else []),
            },
        }

    def complete_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 512,
        temperature: float = 0.1,
        fallback: str = "",
    ) -> str:
        if self._fail:
            raise RuntimeError("Local model unavailable")

        if self.runtime != "llama_cpp":
            return fallback

        client = self._llama_client()
        if client is None:
            return fallback

        try:
            response = self._complete_with_llama_cpp(
                client,
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except Exception:
            return fallback

        text = self._response_text(response, fallback=fallback)
        cleaned = self._clean_generated_text(text)
        return cleaned or fallback

    def _generate_with_llama_cpp(self, state: GraphState, *, fallback: str) -> str:
        reasoning_output = getattr(state, "reasoning_output", {}) or {}
        prompt = reasoning_output.get("prompt") or state.query
        return self.complete_text(
            str(prompt),
            max_tokens=256,
            temperature=0.1,
            fallback=fallback,
        )

    def _complete_with_llama_cpp(
        self,
        client: Any,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> Any:
        chat_completion = getattr(client, "create_chat_completion", None)
        if callable(chat_completion):
            return chat_completion(
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                max_tokens=max_tokens,
                temperature=temperature,
            )
        return client.create_completion(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def _stream_with_llama_cpp(
        self,
        client: Any,
        *,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> Generator[str, None, None]:
        chat_completion = getattr(client, "create_chat_completion", None)
        if callable(chat_completion):
            response = chat_completion(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )
            yield from self._extract_stream_deltas(response)
            return

        response = client.create_completion(
            prompt=prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            stream=True,
        )
        yield from self._extract_stream_deltas(response)

    def _extract_stream_deltas(self, response: Any) -> Generator[str, None, None]:
        for chunk in response:
            delta = self._response_delta(chunk)
            if delta:
                yield delta

    def _response_delta(self, chunk: Any) -> str:
        if isinstance(chunk, dict):
            choices = chunk.get("choices", [])
        else:
            choices = getattr(chunk, "choices", [])
        if not choices:
            return ""

        first = choices[0]
        if isinstance(first, dict):
            delta = first.get("delta")
            if isinstance(delta, dict):
                content = delta.get("content")
                if isinstance(content, str):
                    return content
            text = first.get("text")
            if isinstance(text, str):
                return text
        delta = getattr(first, "delta", None)
        content = getattr(delta, "content", None) if delta is not None else None
        if isinstance(content, str):
            return content
        text = getattr(first, "text", None)
        if isinstance(text, str):
            return text
        return ""

    def _response_text(self, response: Any, *, fallback: str) -> str:
        if isinstance(response, dict):
            choices = response.get("choices", [])
        else:
            choices = getattr(response, "choices", [])
        if not choices:
            return fallback

        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip() or fallback
                if isinstance(content, list):
                    parts = [
                        str(item.get("text", "")).strip()
                        for item in content
                        if isinstance(item, dict) and str(item.get("text", "")).strip()
                    ]
                    if parts:
                        return "\n".join(parts)
            text = first.get("text")
            if isinstance(text, str):
                return text.strip() or fallback

        message = getattr(first, "message", None)
        content = getattr(message, "content", None) if message is not None else None
        if isinstance(content, str):
            return content.strip() or fallback
        text = getattr(first, "text", None)
        if isinstance(text, str):
            return text.strip() or fallback
        return fallback

    def _clean_generated_text(self, text: str) -> str:
        if not text:
            return ""

        kept_lines: list[str] = []
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped:
                if kept_lines and kept_lines[-1] != "":
                    kept_lines.append("")
                continue
            if any(marker in stripped for marker in _RUNTIME_LOG_MARKERS):
                continue
            if any(marker in stripped for marker in _CHAT_TEMPLATE_MARKERS):
                continue
            kept_lines.append(line)

        return "\n".join(kept_lines).strip()

    def _clean_stream_delta(self, delta: str) -> str:
        stripped = delta.strip()
        if not stripped:
            return delta
        if any(marker in stripped for marker in _RUNTIME_LOG_MARKERS):
            return ""
        if any(marker in stripped for marker in _CHAT_TEMPLATE_MARKERS):
            return ""
        return delta

    def _llama_client(self) -> Any | None:
        if self._client is not None:
            return self._client
        llama_cls = load_attr("llama_cpp", "Llama")
        if llama_cls is None:
            return None
        base_kwargs = {
            "model_path": str(Path(self._model_path).expanduser()),
            "verbose": False,
            "n_ctx": self._context_length,
        }
        try:
            self._client = llama_cls(
                **base_kwargs,
                flash_attn=True,
            )
        except TypeError:
            try:
                self._client = llama_cls(**base_kwargs)
            except Exception:
                return None
        except Exception:
            return None
        return self._client
