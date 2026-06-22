from llama_cpp import Llama
import sys

print("Loading model...")
llm = Llama(
    model_path="/Users/trungtran/.cache/huggingface/hub/models--google--gemma-4-E2B-it-qat-q4_0-gguf/snapshots/1894d1fc0a19d86697abd40483f5983c867df03f/gemma-4-E2B_q4_0-it.gguf",
    n_ctx=8192,
    n_batch=128,
    n_gpu_layers=-1,
    flash_attn=True,
    use_mmap=True,
    verbose=True,
)
print("Generating...")
res = llm.create_chat_completion([{"role": "user", "content": "aaaa"}], max_tokens=10)
print(res)
