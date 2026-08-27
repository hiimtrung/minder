# 04. Inference Engine — Qwen3.5 2B & Detached Inference Architecture

---

## 1. Standardized Local Model: Qwen3.5 2B

The project standardizes on **Qwen3.5 2B (GGUF Q4_K_M)**, replacing Gemma 4:
- **Zero Memory Leaks**: Gemma 4's Sliding Window Attention (SWA) causes unbounded KV Cache growth in llama.cpp. Qwen3.5 2B uses Standard Attention with RoPE, cleanly freeing memory after every request.
- **Compact RAM Usage**: Requires only **~1.3GB – 1.8GB RAM**, running smoothly on CPU/WSL/macOS.
- **Superior Code & JSON Quality**: Exceptional adherence to programming syntax and JSON schemas in the 2B tier.

---

## 2. Detached Inference Adapter

To eliminate `llama_cpp_lock` contention on the FastAPI server, Minder supports Detached Inference:

```
┌──────────────────────────────────────────────────────────┐
│                   MINDER CORE SERVER                     │
│  - Non-blocking async I/O                                │
│  - Fast Lean MCP endpoints (< 50ms)                      │
│  - SQLite WAL & Turbovec Index                           │
└────────────────────────────┬─────────────────────────────┘
                             │ (OpenAI-compatible HTTP client)
                             ▼
┌──────────────────────────────────────────────────────────┐
│              DETACHED INFERENCE ENGINE                   │
│  - Local: Ollama (http://localhost:11434/v1)             │
│  - Standalone: llama-server (http://localhost:8080/v1)   │
│  - Remote: OpenAI / Anthropic / OpenRouter API           │
└──────────────────────────────────────────────────────────┘
```
