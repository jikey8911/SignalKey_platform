import asyncio
from api.src.adapters.driven.persistence.mongodb import db

async def main():
    docs = await db.virtual_balances.find({}).to_list(length=1000)
    for d in docs:
        print(str(d.get('_id')), str(d.get('userId')), d.get('marketType'), d.get('asset'), d.get('amount'))

asyncio.run(main())
