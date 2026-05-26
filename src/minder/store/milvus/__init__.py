"""
Milvus Lite Vector Store — embedded vector search, no server required.

Uses pymilvus MilvusClient with a local file URI for zero-dependency ANN search.
"""

from .client import MilvusClientWrapper
from .vector_store import MilvusVectorStore

__all__ = ["MilvusClientWrapper", "MilvusVectorStore"]
