from bson import ObjectId
from typing import Optional, Dict, Any, List
from datetime import datetime
from api.src.adapters.driven.persistence.mongodb import db

class ConfigRepository:
    """
    Repositorio para gestionar configuraciones dinámicas de la aplicación.
    Tarea 6.1: Estructura Real de Configuración.
    """
    def __init__(self, db_adapter=None):
        # Usamos el db_adapter si se proporciona, de lo contrario usamos la instancia global
        self.db = db_adapter if db_adapter else db.db

    async def _get_user_oid(self, user_id: str) -> Optional[ObjectId]:
        """
        Resuelve un openId o un string ID de MongoDB al ObjectId correspondiente del usuario.
        """
        # 1. Intentar buscar por openId en la colección de usuarios
        user = await self.db["users"].find_one({"openId": user_id})
        if user:
            return user["_id"]

        # 2. Si no es un openId, intentar tratarlo como un ObjectId directo del usuario
        try:
            if isinstance(user_id, str) and len(user_id) == 24:
                return ObjectId(user_id)
        except Exception:
            pass

        # 3. También podría ser ya un ObjectId
        if isinstance(user_id, ObjectId):
            return user_id

        return None

    async def get_config(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene la configuración del usuario por su ID u openId."""
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            return None
        return await self.db["app_configs"].find_one({"userId": user_oid})

    async def get_or_create_config(self, user_id: str) -> Dict[str, Any]:
        """Obtiene la configuración existente o crea una nueva con valores por defecto."""
        config = await self.get_config(user_id)
        if config:
            return config

        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            # Si no encontramos al usuario, no podemos crear su configuración
            raise Exception(f"Usuario no encontrado para ID: {user_id}")

        # Valores por defecto basados en AppConfigSchema
        new_config = {
            "userId": user_oid,
            "isAutoEnabled": True,
            "botTelegramActivate": False,
            "demoMode": True,
            "aiProvider": "gemini",
            "exchanges": [],
            "dexConfig": {
                "walletPrivateKey": "",
                "rpcUrl": "https://api.mainnet-beta.solana.com"
            },
            "investmentLimits": {
                "cexMaxAmount": 100.0,
                "dexMaxAmount": 1.0
            },
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow()
        }

        await self.db["app_configs"].insert_one(new_config)
        return new_config

    async def create_config(self, user_id: str, config_dict: Dict[str, Any]) -> str:
        """Crea una nueva configuración para un usuario."""
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            raise Exception(f"Usuario no encontrado para ID: {user_id}")

        config_dict["userId"] = user_oid
        if "createdAt" not in config_dict:
            config_dict["createdAt"] = datetime.utcnow()
        config_dict["updatedAt"] = datetime.utcnow()

        result = await self.db["app_configs"].insert_one(config_dict)
        return str(result.inserted_id)

    async def update_config(self, user_id: str, update_dict: Dict[str, Any]) -> bool:
        """Actualiza la configuración de un usuario."""
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            return False

        update_dict["updatedAt"] = datetime.utcnow()

        # Eliminar userId y _id si vienen en el update_dict para evitar errores de inmutabilidad
        update_dict.pop("userId", None)
        update_dict.pop("_id", None)

        result = await self.db["app_configs"].update_one(
            {"userId": user_oid},
            {"$set": update_dict}
        )
        return result.modified_count > 0 or result.matched_count > 0

    async def add_exchange(self, user_id: str, exchange_dict: Dict[str, Any]) -> bool:
        """Agrega una configuración de exchange al usuario."""
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            return False

        # Asignar un _id único al exchange si no lo tiene (estilo MongoDB)
        if "_id" not in exchange_dict:
            exchange_dict["_id"] = ObjectId()
        elif isinstance(exchange_dict["_id"], str) and len(exchange_dict["_id"]) == 24:
            exchange_dict["_id"] = ObjectId(exchange_dict["_id"])

        result = await self.db["app_configs"].update_one(
            {"userId": user_oid},
            {
                "$push": {"exchanges": exchange_dict},
                "$set": {"updatedAt": datetime.utcnow()}
            }
        )
        return result.modified_count > 0

    async def remove_exchange(self, user_id: str, exchange_id: str) -> bool:
        """Elimina un exchange de la configuración del usuario."""
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            return False

        # Intentamos eliminar por exchangeId (ej: 'binance') o por su _id único
        # Primero por exchangeId
        result = await self.db["app_configs"].update_one(
            {"userId": user_oid},
            {
                "$pull": {"exchanges": {"exchangeId": exchange_id}},
                "$set": {"updatedAt": datetime.utcnow()}
            }
        )

        if result.modified_count == 0:
            # Si no funcionó, intentamos por el _id del objeto exchange
            try:
                oid = ObjectId(exchange_id) if len(exchange_id) == 24 else None
                if oid:
                    result = await self.db["app_configs"].update_one(
                        {"userId": user_oid},
                        {
                            "$pull": {"exchanges": {"_id": oid}},
                            "$set": {"updatedAt": datetime.utcnow()}
                        }
                    )
            except Exception:
                pass

        return result.modified_count > 0

    async def get_telegram_creds(self, user_id: str):
        """
        Busca credenciales de Telegram en la colección app_configs.
        Campos: telegramApiId, telegramApiHash, telegramSessionString
        """
        try:
            config = await self.get_config(user_id)
            
            if not config: 
                return None
            
            return {
                "api_id": config.get("telegramApiId"),
                "api_hash": config.get("telegramApiHash"),
                "session": config.get("telegramSessionString"),
                "is_active": config.get("telegramIsConnected", False)
            }
        except Exception as e:
            print(f"Error fetching telegram creds: {e}")
            return None
