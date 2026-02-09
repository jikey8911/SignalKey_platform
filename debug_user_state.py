import asyncio
import os
import sys

# Añadir el path raíz al sys.path para importaciones locales
sys.path.append(os.getcwd())

from api.src.adapters.driven.persistence.mongodb import db

async def check_user_data(user_id_str):
    with open("debug_user_output.txt", "w", encoding="utf-8") as f:
        f.write(f"--- ROBUST DATA CHECK FOR USER ID: {user_id_str} ---\n")
        
        from bson import ObjectId
        ids_to_check = [user_id_str]
        if ObjectId.is_valid(user_id_str):
            ids_to_check.append(ObjectId(user_id_str))

        # Find user document to get openId if provided ObjectId or vice versa
        user_doc = await db.users.find_one({"$or": [{"openId": user_id_str}, {"_id": {"$in": [i for i in ids_to_check if isinstance(i, ObjectId)]}}]})
        if user_doc:
            f.write(f"User Document Found: _id={user_doc.get('_id')}, openId={user_doc.get('openId')}\n")
            if user_doc.get("_id") not in ids_to_check: ids_to_check.append(user_doc["_id"])
            if user_doc.get("openId") and user_doc.get("openId") not in ids_to_check: ids_to_check.append(user_doc["openId"])
        
        f.write(f"IDs to search in 'userId' fields: {ids_to_check}\n\n")

        # 1. Config
        for coll in ["app_configs", "appconfigs"]:
            config = await db[coll].find_one({"userId": {"$in": ids_to_check}})
            if config:
                f.write(f"Global Config in {coll}: demoMode={config.get('demoMode')}, isAutoEnabled={config.get('isAutoEnabled')}\n")

        # 2. Bots & Bot Instances
        for coll in ["bots", "bot_instances"]:
            items = await db[coll].find({"$or": [{"userId": {"$in": ids_to_check}}, {"user_id": {"$in": ids_to_check}}]}).to_list(None)
            f.write(f"\n[{coll}] Found {len(items)} items:\n")
            for i in items:
                f.write(f"  Name: {i.get('name')} | Symbol: {i.get('symbol')} | Mode: {i.get('mode')} | Status: {i.get('status')} | ID: {i.get('_id')}\n")

        # 3. Trades & Telegram Trades
        for coll in ["trades", "telegram_trades", "db.trades"]:
            items = await db[coll].find({"$or": [{"userId": {"$in": ids_to_check}}, {"user_id": {"$in": ids_to_check}}]}).to_list(None)
            f.write(f"\n[{coll}] Found {len(items)} items:\n")
            for i in items:
                f.write(f"  Symbol: {i.get('symbol')} | Mode: {i.get('mode')} | Status: {i.get('status')} | Side: {i.get('side')} | ID: {i.get('_id')}\n")

if __name__ == "__main__":
    from bson import ObjectId
    user_id = "6969ec789229511d1787166b"
    asyncio.run(check_user_data(user_id))
