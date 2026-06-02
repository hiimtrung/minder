import tempfile
import uuid
import pytest
from pathlib import Path
from unittest.mock import AsyncMock

from minder.store.turbovec.vector_store import TurbovecVectorStore
from minder.domain.entities.document import DocumentSchema


@pytest.mark.asyncio
async def test_turbovec_vector_store_lifecycle() -> None:
    # Use temporary directory for index file
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "vectors.tvim")
        
        # Mock IDocumentRepository
        mock_doc_repo = AsyncMock()
        
        doc_id1 = uuid.uuid4()
        doc_id2 = uuid.uuid4()
        
        doc1 = DocumentSchema(
            id=doc_id1,
            title="Doc 1",
            content="Content 1",
            doc_type="text",
            source_path="/path/1",
            project="proj-a"
        )
        
        doc2 = DocumentSchema(
            id=doc_id2,
            title="Doc 2",
            content="Content 2",
            doc_type="code",
            source_path="/path/2",
            project="proj-b"
        )
        
        mock_doc_repo.get_documents_by_ids.return_value = [doc1, doc2]
        
        # Initialize TurbovecVectorStore
        store = TurbovecVectorStore(
            db_path=db_path,
            document_store=mock_doc_repo,
            dimensions=8
        )
        
        # 1. Setup should create fresh index
        await store.setup()
        assert store._index is not None
        assert store._index.dim == 8
        assert len(store._id_map) == 0
        
        # 2. Upsert documents
        # Embeddings are dimension 8
        emb1 = [1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        emb2 = [0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        
        await store.upsert_document(doc_id1, emb1, {})
        await store.upsert_document(doc_id2, emb2, {})
        
        assert len(store._id_map) == 2
        
        # 3. Search documents (without filters)
        # Query close to emb1
        query = [1.0, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
        results = await store.search_documents(query, limit=2)
        
        assert len(results) == 2
        assert results[0]["id"] == doc_id1
        assert results[0]["title"] == "Doc 1"
        assert results[0]["score"] > 0.9
        assert results[1]["id"] == doc_id2
        assert results[1]["title"] == "Doc 2"
        
        # 4. Search documents with project filter
        results_proj = await store.search_documents(query, project="proj-a", limit=2)
        assert len(results_proj) == 1
        assert results_proj[0]["id"] == doc_id1
        
        # 5. Search documents with doc_types filter
        results_type = await store.search_documents(query, doc_types={"code"}, limit=2)
        assert len(results_type) == 1
        assert results_type[0]["id"] == doc_id2
        
        # 6. Load-back verification: Create a new store pointing to same db_path
        # It should load the existing index and mapping
        new_store = TurbovecVectorStore(
            db_path=db_path,
            document_store=mock_doc_repo,
            dimensions=8
        )
        await new_store.setup()
        assert len(new_store._id_map) == 2
        assert doc_id1 in new_store._id_map.values()
        assert doc_id2 in new_store._id_map.values()

        # 7. Delete documents
        await store.delete_documents([doc_id1])
        assert len(store._id_map) == 1
        
        # Search again should only return doc2
        mock_doc_repo.get_documents_by_ids.return_value = [doc2]
        results_post_del = await store.search_documents(query, limit=2)
        assert len(results_post_del) == 1
        assert results_post_del[0]["id"] == doc_id2
