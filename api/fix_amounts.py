import asyncio
import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

from motor.motor_asyncio import AsyncIOMotorClient
try:
    from api.config import Config
    MONGO_URI = Config.MONGODB_URI
    DB_NAME = Config.MONGODB_DB_NAME
except ImportError:
    print("Could not import Config, using defaults.")
    MONGO_URI = "mongodb://localhost:27017"
    DB_NAME = "trading_db"

async def migrate():
    print(f"Connecting to MongoDB at {MONGO_URI}...")
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    print(f"Using database: {DB_NAME}")

    # Buscar bots con amount <= 0, null o inexistente
    query = {"$or": [{"amount": {"$lte": 0}}, {"amount": {"$exists": False}}, {"amount": None}]}
    bots = await db.bot_instances.find(query).to_list(None)

    print(f"Detectados {len(bots)} bots para corregir.")

    for bot in bots:
        # Lógica de corrección
        new_amount = 100.0 # Default seguro

        # Intentar leer de config si existe
        if "config" in bot and isinstance(bot["config"], dict):
             bal = float(bot["config"].get("initial_balance", 0))
             if bal > 0:
                 new_amount = bal * 0.1 # 10% del balance

        update_fields = {"amount": new_amount}
        if "total_pnl" not in bot:
             update_fields["total_pnl"] = 0.0

        await db.bot_instances.update_one(
            {"_id": bot["_id"]},
            {"$set": update_fields}
        )

        print(f"✅ Bot {bot.get('name', 'Unknown')} ({bot['_id']}) -> Amount: {new_amount}")

if __name__ == "__main__":
    asyncio.run(migrate())
