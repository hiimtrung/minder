from llama_cpp import Llama
import sys

try:
    llm = Llama(model_path="/Users/trungtran/.cache/huggingface/hub/models--google--gemma-4-E2B-it-qat-q4_0-gguf/snapshots/1894d1fc0a19d86697abd40483f5983c867df03f/gemma-4-E2B_q4_0-it.gguf", n_ctx=128, verbose=True)
    print("Metadata keys:", list(llm.metadata.keys())[:10])
    for key, value in llm.metadata.items():
        if 'vocab' in key or 'head' in key or 'dim' in key or 'ctx' in key or 'length' in key:
            print(f"{key}: {value}")
except Exception as e:
    print("Error:", e)
