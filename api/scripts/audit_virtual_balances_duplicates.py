import asyncio
from collections import defaultdict
from api.src.adapters.driven.persistence.mongodb import db

async def main():
    docs = await db.virtual_balances.find({}).to_list(length=200000)
    buckets = defaultdict(list)
    for d in docs:
        k = (str(d.get('userId')), str(d.get('marketType')), str(d.get('asset')))
        buckets[k].append(d)

    dups = [(k, v) for k, v in buckets.items() if len(v) > 1]
    print('total docs', len(docs))
    print('duplicate keys', len(dups))

    for (userId, marketType, asset), v in sorted(dups, key=lambda x: len(x[1]), reverse=True)[:50]:
        amts = [float(x.get('amount',0) or 0) for x in v]
        ids = [str(x.get('_id')) for x in v]
        print('DUP', userId, marketType, asset, 'count', len(v), 'amounts', amts, 'ids', ids)

asyncio.run(main())
