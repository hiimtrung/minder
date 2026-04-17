import asyncio
from minder.config import MinderConfig
from minder.bootstrap.providers import build_store

async def main():
    config = MinderConfig()
    config.relational_store.provider = "mongodb"
    config.relational_store.db_path = "mongomock://localhost"
    try:
        store = build_store(config)
        await store.init_db()
        print("Success")
    except Exception as e:
        print(f"Failed: {e}")

asyncio.run(main())
