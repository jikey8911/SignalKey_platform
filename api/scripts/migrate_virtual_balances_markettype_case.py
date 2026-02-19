import asyncio
from datetime import datetime
from collections import defaultdict

from api.src.adapters.driven.persistence.mongodb import db


def canon(mt: str | None) -> str:
    s = str(mt or 'CEX').strip()
    u = s.upper()
    if u in {'CEX','SPOT','FUTURES','FUTURE','SWAP','PERP','PERPETUAL'}:
        return 'CEX'
    if u == 'DEX':
        return 'DEX'
    if s.lower() in {'cex','spot'}:
        return 'CEX'
    if s.lower() == 'dex':
        return 'DEX'
    return u


async def main(dry_run: bool = False):
    docs = await db.virtual_balances.find({}).to_list(length=200000)
    groups = defaultdict(list)
    for d in docs:
        key = (d.get('userId'), canon(d.get('marketType')), d.get('asset'))
        groups[key].append(d)

    merged = 0
    removed = 0
    updated = 0

    for (userId, cmt, asset), lst in groups.items():
        if len(lst) == 1:
            d = lst[0]
            # update marketType case if needed
            if d.get('marketType') != cmt:
                updated += 1
                if not dry_run:
                    await db.virtual_balances.update_one({'_id': d['_id']}, {'$set': {'marketType': cmt, 'updatedAt': datetime.utcnow()}})
            continue

        # multiple docs differ by case -> merge into one canonical
        total_amt = sum(float(x.get('amount', 0) or 0) for x in lst)
        keep = lst[0]
        keep_id = keep['_id']
        print('MERGE', str(userId), cmt, asset, 'count', len(lst), 'sum', total_amt)
        merged += 1

        if dry_run:
            continue

        await db.virtual_balances.update_one({'_id': keep_id}, {'$set': {'marketType': cmt, 'amount': total_amt, 'updatedAt': datetime.utcnow(), 'mergedFrom': [str(x['_id']) for x in lst]}})
        for x in lst[1:]:
            await db.virtual_balances.delete_one({'_id': x['_id']})
            removed += 1

    print('done dry_run=', dry_run)
    print('groups', len(groups), 'merged', merged, 'removed', removed, 'updated', updated)


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument('--dry-run', action='store_true')
    args = p.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
