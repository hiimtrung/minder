# ADR 0002: Standardize On Qwen3.5 2B & Detached Inference Architecture

## Status
Accepted

## Context
1. Gemma 4's Sliding Window Attention (SWA) causes memory leaks in llama.cpp's KV Cache management, driving RAM consumption from 3GB to 16GB+ until OOM crash.
2. Running `llama-cpp-python` in-process with a global `llama_cpp_lock` serializes all embedding and text generation calls, freezing the server during active generation.

## Decision
1. Standardize on **Qwen3.5 2B (GGUF Q4_K_M)**: Requires only ~1.5GB RAM and uses Standard Attention with RoPE, cleanly freeing memory after every request.
2. Support **Detached Inference Architecture**: Allow the server to connect via OpenAI-compatible HTTP API to Ollama, standalone llama-server, vLLM, or Cloud APIs, eliminating in-process thread locking.

## Consequences
- Non-blocking server I/O capable of handling concurrent MCP requests.
- Stable, bounded memory footprint eliminating OOM crashes.
