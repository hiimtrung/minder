import sys
sys.path.insert(0, "src")
from minder.embedding.local import LocalEmbeddingProvider

print("Initializing LocalEmbeddingProvider...")
provider = LocalEmbeddingProvider(
    llama_cpp_model_repo="nomic-ai/nomic-embed-text-v1.5-GGUF",
    llama_cpp_model_file="nomic-embed-text-v1.5.Q4_K_M.gguf",
    dimensions=768,
    runtime="local",
)

print("Embedding...")
vec = provider.embed("aaaa")
print("Vector length:", len(vec))
