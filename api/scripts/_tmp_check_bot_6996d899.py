import asyncio
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import db

BOT_ID = ObjectId('6996d899132a5caeb10b11f6')

async def main():
    b = await db.bot_instances.find_one({'_id': BOT_ID})
    print('bot found', bool(b))
    if not b:
        return
    for k in ['name','symbol','timeframe','market_type','marketType','exchange_id','exchangeId','mode','status','amount','walletAllocated','walletAvailable','config','created_at','createdAt']:
        if k in b:
            print(k, b.get(k))

asyncio.run(main())
