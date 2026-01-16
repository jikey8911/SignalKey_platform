import asyncio
from api.models.mongodb import db, MongoModel
from bson import ObjectId

async def test_mongo():
    print("Probando conexión a MongoDB...")
    try:
        # 1. Crear un usuario de prueba
        user_data = {
            "openId": "test_user_123",
            "name": "Test User",
            "email": "test@example.com",
            "role": "user"
        }
        user_id = await MongoModel.create("users", user_data)
        print(f"Usuario creado con ID: {user_id}")

        # 2. Crear una configuración de prueba
        config_data = {
            "userId": ObjectId(user_id),
            "demoMode": True,
            "exchanges": [
                {"exchangeId": "binance", "apiKey": "test_key", "secret": "test_secret", "isActive": True}
            ],
            "investmentLimits": {
                "cexMaxAmount": 500.0,
                "dexMaxAmount": 5.0
            }
        }
        await MongoModel.create("app_configs", config_data)
        print("Configuración de prueba creada")

        # 3. Recuperar configuración
        config = await db.app_configs.find_one({"userId": ObjectId(user_id)})
        print(f"Configuración recuperada: CEX Limit = {config['investmentLimits']['cexMaxAmount']}")

        # Limpieza (opcional)
        # await db.users.delete_one({"_id": ObjectId(user_id)})
        # await db.app_configs.delete_one({"userId": ObjectId(user_id)})
        
        print("Prueba completada con éxito")
    except Exception as e:
        print(f"Error en la prueba: {e}")

if __name__ == "__main__":
    asyncio.run(test_mongo())
