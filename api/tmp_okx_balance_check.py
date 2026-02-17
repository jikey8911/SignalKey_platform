import asyncio
import json
from api.src.adapters.driven.exchange.ccxt_adapter import CcxtAdapter
from api.src.adapters.driven.persistence.mongodb import db


async def main():
    user = await db.users.find_one({'openId': 'juank8911'})
    print('USER_FOUND', bool(user))
    if not user:
        return

    cfg = await db.app_configs.find_one({'userId': user['_id']})
    print('CFG_FOUND', bool(cfg))

    exs = (cfg or {}).get('exchanges', [])
    okx = next((e for e in exs if str(e.get('exchangeId', '')).lower() == 'okx'), None)
    print('OKX_CFG', bool(okx))
    if okx:
        print(
            'OKX_ACTIVE', okx.get('isActive'),
            'HAS_KEY', bool(okx.get('apiKey')),
            'HAS_SECRET', bool(okx.get('secret')),
            'HAS_PASSWORD', bool(okx.get('password')),
        )

    adapter = CcxtAdapter()
    balances = await adapter.fetch_balance('juank8911', 'okx')
    print('BAL_COUNT', len(balances))
    sample = [
        {
            'asset': b.asset,
            'free': float(b.free),
            'used': float(b.used),
            'total': float(b.total),
        }
        for b in balances[:15]
    ]
    print(json.dumps(sample, ensure_ascii=False))
    await adapter.close_all()


if __name__ == '__main__':
    asyncio.run(main())
