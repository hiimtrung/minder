"""
Milvus Collections — schema definitions.
"""
from pymilvus import CollectionSchema, DataType, FieldSchema  # type: ignore[import-not-found, import-untyped]

def get_document_schema(dimensions: int = 768) -> CollectionSchema:
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimensions),
        FieldSchema(name="project", dtype=DataType.VARCHAR, max_length=256),
        FieldSchema(name="doc_type", dtype=DataType.VARCHAR, max_length=64),
        # Payload stored as JSON string because Milvus JSON handles unstructured data
        FieldSchema(name="payload", dtype=DataType.JSON),
    ]
    return CollectionSchema(fields, description="Document chunks for RAG")
