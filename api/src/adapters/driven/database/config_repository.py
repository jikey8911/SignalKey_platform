from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional, Dict, Any, List
from datetime import datetime
from bson import ObjectId


class ConfigRepository:
    """Repository for user configuration database operations"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.app_configs
    
    async def get_config(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user configuration by user_id"""
        # Try to find by userId as ObjectId
        try:
            config = await self.collection.find_one({'userId': ObjectId(user_id)})
            if config:
                return config
        except:
            pass
        
        # Fallback: try to find user by openId and then get config
        user = await self.db.users.find_one({'openId': user_id})
        if user:
            config = await self.collection.find_one({'userId': user['_id']})
            return config
        
        return None
    
    async def create_config(self, user_id: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create new user configuration"""
        # Get user ObjectId
        user = await self.db.users.find_one({'openId': user_id})
        if not user:
            raise ValueError(f"User not found: {user_id}")
        
        config_data['userId'] = user['_id']
        config_data['createdAt'] = datetime.utcnow()
        config_data['updatedAt'] = datetime.utcnow()
        
        # Set defaults
        config_data.setdefault('demoMode', True)
        config_data.setdefault('isAutoEnabled', True)
        config_data.setdefault('aiProvider', 'gemini')
        config_data.setdefault('exchanges', [])
        config_data.setdefault('investmentLimits', {'cexMaxAmount': 100, 'dexMaxAmount': 1})
        config_data.setdefault('virtualBalances', {'cex': 10000, 'dex': 10})
        
        result = await self.collection.insert_one(config_data)
        config_data['_id'] = result.inserted_id
        return config_data
    
    async def update_config(self, user_id: str, updates: Dict[str, Any]) -> bool:
        """Update user configuration"""
        user = await self.db.users.find_one({'openId': user_id})
        if not user:
            return False
        
        updates['updatedAt'] = datetime.utcnow()
        result = await self.collection.update_one(
            {'userId': user['_id']},
            {'$set': updates}
        )
        return result.modified_count > 0
    
    async def get_or_create_config(self, user_id: str) -> Dict[str, Any]:
        """Get config or create if doesn't exist"""
        config = await self.get_config(user_id)
        if config:
            return config
        return await self.create_config(user_id, {})
    
    async def add_exchange(self, user_id: str, exchange_data: Dict[str, Any]) -> bool:
        """Add exchange to user configuration"""
        user = await self.db.users.find_one({'openId': user_id})
        if not user:
            return False
        
        exchange_data.setdefault('isActive', True)
        
        result = await self.collection.update_one(
            {'userId': user['_id']},
            {'$push': {'exchanges': exchange_data}, '$set': {'updatedAt': datetime.utcnow()}}
        )
        return result.modified_count > 0
    
    async def remove_exchange(self, user_id: str, exchange_id: str) -> bool:
        """Remove exchange from user configuration"""
        user = await self.db.users.find_one({'openId': user_id})
        if not user:
            return False
        
        result = await self.collection.update_one(
            {'userId': user['_id']},
            {'$pull': {'exchanges': {'exchangeId': exchange_id}}, '$set': {'updatedAt': datetime.utcnow()}}
        )
        return result.modified_count > 0
    
    async def update_exchange(self, user_id: str, exchange_id: str, updates: Dict[str, Any]) -> bool:
        """Update specific exchange in user configuration"""
        user = await self.db.users.find_one({'openId': user_id})
        if not user:
            return False
        
        # Build update query for array element
        set_updates = {f'exchanges.$.{k}': v for k, v in updates.items()}
        set_updates['updatedAt'] = datetime.utcnow()
        
        result = await self.collection.update_one(
            {'userId': user['_id'], 'exchanges.exchangeId': exchange_id},
            {'$set': set_updates}
        )
        return result.modified_count > 0

    async def update_telegram_credentials(self, user_id: str, api_id: str, api_hash: str, phone: str, session: str = None) -> bool:
        """
        Tarea 6.1: Repositorio de Credenciales Dinámicas
        Actualiza específicamente las credenciales de Telegram del usuario.
        """
        updates = {
            "telegramApiId": api_id,
            "telegramApiHash": api_hash,
            "telegramPhoneNumber": phone,
            "telegramIsConnected": True
        }
        if session:
            updates["telegramSessionString"] = session
            
        return await self.update_config(user_id, updates)
