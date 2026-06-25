from llama_cpp import Llama
import sys

print("Loading model...")
llm = Llama.from_pretrained(
    repo_id="unsloth/Qwen3.5-2B-GGUF",
    filename="Qwen3.5-2B-Q4_K_M.gguf",
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
