import sys
import asyncio
sys.path.insert(0, "src")
from minder.config import Settings
from minder.bootstrap.providers import build_store, build_vector_store, build_graph_store
from minder.tools.query import QueryTools
from minder.graph import MinderGraph
from minder.tools.graph import GraphTools

async def main():
    print("Loading config...")
    config = Settings()
    config.llm.provider = "llama_cpp"
    config.embedding.runtime = "llama_cpp"
    
    print("Building stores...")
    store = build_store(config)
    await store.init_db()
    
    # ensure admin exists so we can run
    admin = await store.get_user_by_username("admin")
    if not admin:
        from minder.domain.models import User
        admin = User(username="admin", password_hash="hash", role="admin")
        await store.create_user(admin)
        
    vector_store = build_vector_store(config, store)
    if hasattr(vector_store, "setup"):
        await vector_store.setup()
        
    graph_store = build_graph_store(config)
    if graph_store is not None and hasattr(graph_store, "init_db"):
        await graph_store.init_db()
        
    graph_tools = GraphTools(graph_store, store)
    shared_graph = MinderGraph(store, config, graph_tools=graph_tools)
    query_tools = QueryTools(
        store,
        config,
        graph=shared_graph,
        vector_store=vector_store,
        graph_tools=graph_tools,
    )
    
    print("Running query...")
    async for chunk in query_tools.minder_query_stream(
        query="aaaa",
        repo_path=None,
        workflow_name="default",
    ):
        print(chunk)

asyncio.run(main())
