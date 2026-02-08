import asyncio
import os
import sys
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from motor.motor_asyncio import AsyncIOMotorClient
from api.config import Config

async def migrate():
    print(f"Connecting to MongoDB: {Config.MONGODB_URI}...")
    client = AsyncIOMotorClient(Config.MONGODB_URI)
    db = client[Config.MONGODB_DB_NAME]

    configs = await db.app_configs.find({}).to_list(None)
    print(f"Found {len(configs)} configs to migrate.")

    migrated_count = 0

    for config in configs:
        user_id = config.get("userId")
        config_id = config.get("_id")

        if not user_id:
            print(f"Skipping config {config_id}: No userId")
            continue

        current_provider = config.get("aiProvider", "gemini")

        # Map of provider name -> config key
        # We include 'groq' even though it's new
        providers_map = {
            "gemini": "geminiApiKey",
            "openai": "openaiApiKey",
            "perplexity": "perplexityApiKey",
            "grok": "grokApiKey",
            "groq": "groqApiKey"
        }

        # Ensure we cover all 5 providers
        all_providers = ["gemini", "openai", "perplexity", "grok", "groq"]

        for provider in all_providers:
            key_field = providers_map.get(provider)

            # Logic to extract existing key
            api_key = config.get(key_field)

            # Fallback for Gemini legacy 'aiApiKey'
            if provider == "gemini" and not api_key:
                api_key = config.get("aiApiKey")

            is_primary = (provider == current_provider)

            agent_data = {
                "userId": user_id,
                "configId": config_id,
                "provider": provider,
                "apiKey": api_key,
                "isActive": bool(api_key),
                "isPrimary": is_primary,
                "updatedAt": datetime.utcnow()
            }

            # Upsert based on userId + provider
            await db.ai_agents.update_one(
                {"userId": user_id, "provider": provider},
                {"$set": agent_data, "$setOnInsert": {"createdAt": datetime.utcnow()}},
                upsert=True
            )

        migrated_count += 1

    print(f"Migration complete. Processed {migrated_count} users.")

if __name__ == "__main__":
    asyncio.run(migrate())
