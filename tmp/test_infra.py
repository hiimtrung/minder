import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import redis.asyncio as redis
from pymilvus import connections, utility

async def test_mongodb():
    print("Testing MongoDB...")
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    try:
        await client.admin.command('ping')
        print("✅ MongoDB is reachable")
    except Exception as e:
        print(f"❌ MongoDB error: {e}")
    finally:
        client.close()

async def test_redis():
    print("Testing Redis...")
    r = redis.from_url("redis://localhost:6379/0")
    try:
        await r.ping()
        print("✅ Redis is reachable")
    except Exception as e:
        print(f"❌ Redis error: {e}")
    finally:
        await r.aclose()

async def test_milvus():
    print("Testing Milvus...")
    try:
        connections.connect("default", host="localhost", port="19530")
        print("✅ Milvus is reachable")
        # List collections as a check
        collections = utility.list_collections()
        print(f"   Collections: {collections}")
    except Exception as e:
        print(f"❌ Milvus error: {e}")
    finally:
        try:
            connections.disconnect("default")
        except:
            pass

async def main():
    await test_mongodb()
    await test_redis()
    await test_milvus()

if __name__ == "__main__":
    asyncio.run(main())
