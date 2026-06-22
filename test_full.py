import sys
sys.path.insert(0, "src")
from minder.config import Settings
from minder.infrastructure.hardware import get_hardware_profile

config = Settings()
hw = get_hardware_profile(max_ctx=config.llm.context_length)
print(f"HW Profile: {hw}")

from llama_cpp import Llama

print("Loading model...")
llm = Llama.from_pretrained(
    repo_id="google/gemma-4-E2B-it-qat-q4_0-gguf",
    filename="gemma-4-E2B_q4_0-it.gguf",
    n_ctx=hw.n_ctx,
    n_batch=hw.n_batch,
    n_ubatch=hw.n_ubatch,
    n_gpu_layers=hw.n_gpu_layers,
    n_threads=hw.n_threads,
    flash_attn=hw.use_flash_attn,
    verbose=True,
    use_mmap=True,
)

print("Starting generation...")
res = llm.create_chat_completion(
    messages=[{"role": "user", "content": "aaaa"}],
    max_tokens=512,
    stream=True
)
for chunk in res:
    print(chunk["choices"][0]["delta"].get("content", ""), end="", flush=True)
print("\nDone.")
