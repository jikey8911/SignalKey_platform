import asyncio
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import db

BOT_ID = ObjectId('6996db00132a5caeb10b11f7')

async def main():
    b = await db.bot_instances.find_one({'_id': BOT_ID})
    print('amount', b.get('amount'))
    print('has amount key', 'amount' in b)
    print('doc', {k: b.get(k) for k in ['symbol','timeframe','exchange_id','market_type','mode','status','amount','config'] if k in b})

asyncio.run(main())
