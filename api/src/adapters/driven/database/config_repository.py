from bson import ObjectId
from typing import Optional, Dict, Any, List
from datetime import datetime
import logging
from api.src.adapters.driven.persistence.mongodb import db as db_global

logger = logging.getLogger(__name__)

def stringify_object_ids(obj):
    """Recursively converts ObjectId to string."""
    if isinstance(obj, list):
        return [stringify_object_ids(item) for item in obj]
    if isinstance(obj, dict):
        return {k: stringify_object_ids(v) for k, v in obj.items()}
    if isinstance(obj, ObjectId):
        return str(obj)
    return obj

class ConfigRepository:
    """
    Repositorio para gestionar configuraciones dinámicas de la aplicación.
    Tarea 6.1: Estructura Real de Configuración.

    Notes (2026-02):
    - Exchanges config is being migrated out of `app_configs.exchanges[]` into a new
      collection `user_exchanges` (1 document per user with an `exchanges[]` array).
    - During migration we keep a copy in `app_configs` for safety, but reads should
      prefer `user_exchanges` with fallback to `app_configs`.
    """

    def __init__(self, db_adapter=None):
        # Usamos el db_adapter si se proporciona, de lo contrario usamos la instancia global
        # IMPORTANTE: db_global ya es la base de datos (Database object), no hay que usar .db
        self.db = db_adapter if db_adapter is not None else db_global

    async def _get_user_oid(self, user_id: str) -> Optional[ObjectId]:
        """
        Resuelve un openId o un string ID de MongoDB al ObjectId correspondiente del usuario.
        """
        try:
            # Si ya es un ObjectId, retornarlo
            if isinstance(user_id, ObjectId):
                return user_id

            # 1. Intentar buscar por openId en la colección de usuarios
            user = await self.db["users"].find_one({"openId": user_id})
            if user:
                return user["_id"]

            # 2. Si no es un openId, intentar tratarlo como un ObjectId directo del usuario
            if isinstance(user_id, str) and len(user_id) == 24:
                try:
                    return ObjectId(user_id)
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"Error resolving user OID for {user_id}: {e}")

        return None

    async def get_config(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Obtiene la configuración del usuario por su ID u openId."""
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            # Fallback: intentar buscar directamente si user_id ya es el userId en app_configs
            config = await self.db["app_configs"].find_one({"userId": user_id})
            return stringify_object_ids(config) if config else None

        config = await self.db["app_configs"].find_one({"userId": user_oid})
        return stringify_object_ids(config) if config else None

    async def get_or_create_config(self, user_id: str) -> Dict[str, Any]:
        """Obtiene la configuración existente o crea una nueva con valores por defecto."""
        config = await self.get_config(user_id)
        if config:
            return config

        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
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
        return stringify_object_ids(new_config)

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

        # Eliminar userId y _id si vienen en el update_dict
        update_dict.pop("userId", None)
        update_dict.pop("_id", None)

        result = await self.db["app_configs"].update_one(
            {"userId": user_oid},
            {"$set": update_dict}
        )
        return result.modified_count > 0 or result.matched_count > 0

    async def _ensure_user_exchanges_doc(self, user_oid: ObjectId) -> Dict[str, Any]:
        """Ensure a `user_exchanges` document exists for this user.

        Keeps a copy of exchanges inside `app_configs` for backward compatibility,
        but the primary store is `user_exchanges`.
        """
        doc = await self.db["user_exchanges"].find_one({"userId": user_oid})
        if doc:
            return doc

        # Lazy migration: copy from app_configs if present
        config = await self.db["app_configs"].find_one({"userId": user_oid})
        exchanges = (config or {}).get("exchanges", [])

        new_doc = {
            "userId": user_oid,
            "exchanges": exchanges,
            "createdAt": datetime.utcnow(),
            "updatedAt": datetime.utcnow(),
        }
        await self.db["user_exchanges"].insert_one(new_doc)
        return new_doc

    async def get_exchanges_prefer_user_exchanges(self, user_id: str) -> List[Dict[str, Any]]:
        """Return exchanges for user preferring `user_exchanges`, falling back to `app_configs`."""
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            return []

        doc = await self.db["user_exchanges"].find_one({"userId": user_oid})
        if doc and "exchanges" in doc:
            return stringify_object_ids(doc.get("exchanges", []))

        # Fallback to app_configs
        config = await self.db["app_configs"].find_one({"userId": user_oid})
        return stringify_object_ids((config or {}).get("exchanges", []))

    async def _normalize_exchange_doc(self, exchange_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure exchange subdocument has a stable ObjectId `_id` (for UI edits/removes)."""
        ex = dict(exchange_dict)
        if "_id" not in ex:
            ex["_id"] = ObjectId()
        elif isinstance(ex["_id"], str) and len(ex["_id"]) == 24:
            try:
                ex["_id"] = ObjectId(ex["_id"])
            except Exception:
                pass
        return ex

    async def set_exchanges(self, user_id: str, exchanges: List[Dict[str, Any]]) -> bool:
        """Replace exchanges array for user.

        Writes to `user_exchanges` (primary) and keeps a copy in `app_configs` (secondary).
        This supports the UI behavior of saving the whole config in one call.
        """
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            return False

        await self._ensure_user_exchanges_doc(user_oid)

        normalized = [await self._normalize_exchange_doc(e) for e in exchanges]

        res_primary = await self.db["user_exchanges"].update_one(
            {"userId": user_oid},
            {"$set": {"exchanges": normalized, "updatedAt": datetime.utcnow()}},
        )
        res_secondary = await self.db["app_configs"].update_one(
            {"userId": user_oid},
            {"$set": {"exchanges": normalized, "updatedAt": datetime.utcnow()}},
        )
        return (res_primary.matched_count > 0) and (res_secondary.matched_count > 0)

    async def add_exchange(self, user_id: str, exchange_dict: Dict[str, Any]) -> bool:
        """Agrega una configuración de exchange al usuario.

        Writes to `user_exchanges` (primary) and also keeps a copy in `app_configs` (secondary).
        """
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            return False

        exchange_dict = await self._normalize_exchange_doc(exchange_dict)

        # Ensure user_exchanges exists (lazy migration)
        await self._ensure_user_exchanges_doc(user_oid)

        # Push into user_exchanges
        res_primary = await self.db["user_exchanges"].update_one(
            {"userId": user_oid},
            {
                "$push": {"exchanges": exchange_dict},
                "$set": {"updatedAt": datetime.utcnow()},
            },
        )

        # Keep copy in app_configs
        res_secondary = await self.db["app_configs"].update_one(
            {"userId": user_oid},
            {
                "$push": {"exchanges": exchange_dict},
                "$set": {"updatedAt": datetime.utcnow()},
            },
        )

        return (res_primary.modified_count > 0 or res_primary.matched_count > 0) and (
            res_secondary.modified_count > 0 or res_secondary.matched_count > 0
        )

    async def remove_exchange(self, user_id: str, exchange_id: str) -> bool:
        """Elimina un exchange de la configuración del usuario.

        Removes from `user_exchanges` (primary) and also from `app_configs` (secondary).
        Supports removing by exchangeId or by subdocument _id.
        """
        user_oid = await self._get_user_oid(user_id)
        if not user_oid:
            return False

        # Ensure user_exchanges exists (lazy migration)
        await self._ensure_user_exchanges_doc(user_oid)

        # First try by exchangeId
        res_primary = await self.db["user_exchanges"].update_one(
            {"userId": user_oid},
            {
                "$pull": {"exchanges": {"exchangeId": exchange_id}},
                "$set": {"updatedAt": datetime.utcnow()},
            },
        )
        res_secondary = await self.db["app_configs"].update_one(
            {"userId": user_oid},
            {
                "$pull": {"exchanges": {"exchangeId": exchange_id}},
                "$set": {"updatedAt": datetime.utcnow()},
            },
        )

        # If nothing removed, try by subdocument ObjectId
        if res_primary.modified_count == 0 and res_secondary.modified_count == 0:
            try:
                if len(exchange_id) == 24:
                    oid = ObjectId(exchange_id)
                    res_primary = await self.db["user_exchanges"].update_one(
                        {"userId": user_oid},
                        {
                            "$pull": {"exchanges": {"_id": oid}},
                            "$set": {"updatedAt": datetime.utcnow()},
                        },
                    )
                    res_secondary = await self.db["app_configs"].update_one(
                        {"userId": user_oid},
                        {
                            "$pull": {"exchanges": {"_id": oid}},
                            "$set": {"updatedAt": datetime.utcnow()},
                        },
                    )
            except Exception:
                pass

        return (res_primary.modified_count > 0) or (res_secondary.modified_count > 0)

    async def get_telegram_creds(self, user_id: str):
        """Busca credenciales de Telegram en la colección app_configs."""
        try:
            # get_config ya retorna strings para los ObjectIds
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
            logger.error(f"Error fetching telegram creds: {e}")
            return None
