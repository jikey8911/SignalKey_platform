from motor.motor_asyncio import AsyncIOMotorDatabase
from typing import Optional, Dict, Any
from datetime import datetime
import bcrypt
from bson import ObjectId


class UserRepository:
    """Repository for user database operations"""
    
    def __init__(self, db: AsyncIOMotorDatabase):
        self.db = db
        self.collection = db.users
    
    async def create_user(self, user_data: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new user"""
        # Hash password if provided
        if 'password' in user_data:
            hashed = bcrypt.hashpw(user_data['password'].encode('utf-8'), bcrypt.gensalt())
            user_data['password'] = hashed.decode('utf-8')
        
        user_data['createdAt'] = datetime.utcnow()
        user_data['updatedAt'] = datetime.utcnow()
        user_data['lastSignedIn'] = datetime.utcnow()
        
        result = await self.collection.insert_one(user_data)
        user_data['_id'] = result.inserted_id
        return user_data
    
    async def find_user_by_openid(self, openid: str, include_password: bool = False) -> Optional[Dict[str, Any]]:
        """Find user by openId"""
        projection = None if include_password else {'password': 0}
        user = await self.collection.find_one({'openId': openid}, projection)
        return user
    
    async def find_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Find user by _id"""
        user = await self.collection.find_one({'_id': ObjectId(user_id)}, {'password': 0})
        return user
    
    async def update_user(self, openid: str, updates: Dict[str, Any]) -> bool:
        """Update user by openId"""
        updates['updatedAt'] = datetime.utcnow()
        result = await self.collection.update_one(
            {'openId': openid},
            {'$set': updates}
        )
        return result.modified_count > 0
    
    async def verify_password(self, openid: str, password: str) -> bool:
        """Verify user password"""
        user = await self.collection.find_one({'openId': openid}, {'password': 1})
        if not user or 'password' not in user:
            return False
        
        stored_password = user['password']
        return bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8'))
    
    async def update_last_signed_in(self, openid: str) -> bool:
        """Update last signed in timestamp"""
        result = await self.collection.update_one(
            {'openId': openid},
            {'$set': {'lastSignedIn': datetime.utcnow()}}
        )
        return result.modified_count > 0
