from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import db

class ConfigRepository:
    """
    Repositorio para gestionar configuraciones dinámicas de la aplicación.
    Tarea 6.1: Estructura Real de Configuración.
    """
    def __init__(self, db_adapter=None):
        self.db = db_adapter if db_adapter else db.db

    async def get_telegram_creds(self, user_id: str):
        """
        Busca credenciales de Telegram en la colección app_configs.
        Campos: telegramApiId, telegramApiHash, telegramSessionString
        """
        try:
            # Asumimos que user_id es un string válido para ObjectId, o lo manejamos
            uid = ObjectId(user_id) if isinstance(user_id, str) and len(user_id)==24 else user_id
            
            # La query busca un documento de config asociado al usuario
            # Estructura basada en snippet usuario: {"userId": ObjectId(user_id)}
            # Ojo: En algunos esquemas config es global. Asumimos esquema "por usuario".
            config = await self.db["app_configs"].find_one({"userId": uid})
            
            if not config: 
                return None
            
            return {
                "api_id": config.get("telegramApiId"),
                "api_hash": config.get("telegramApiHash"),
                "session": config.get("telegramSessionString"),
                "is_active": config.get("telegramIsConnected", False) # Usando telegramIsConnected como flag más probable según routers.ts
            }
        except Exception as e:
            print(f"Error fetching telegram creds: {e}")
            return None
