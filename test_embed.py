import sys
sys.path.insert(0, "src")
from minder.embedding.local import LocalEmbeddingProvider

print("Initializing LocalEmbeddingProvider...")
provider = LocalEmbeddingProvider(
    llama_cpp_model_repo="ggml-org/embeddinggemma-300M-GGUF",
    llama_cpp_model_file="embeddinggemma-300M-Q8_0.gguf",
    dimensions=768,
    runtime="local",
)

print("Embedding...")
vec = provider.embed("aaaa")
print("Vector length:", len(vec))
