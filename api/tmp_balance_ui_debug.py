import asyncio
import json
from api.src.adapters.driven.persistence.mongodb import db
from api.src.application.services.cex_service import CEXService
from api.src.adapters.driven.exchange.ccxt_adapter import CcxtAdapter


async def main():
    open_id = 'juank8911'
    user = await db.users.find_one({'openId': open_id})
    print('USER_FOUND', bool(user))
    if not user:
        return

    cfg = await db.app_configs.find_one({'userId': user['_id']}) or {}
    exs = cfg.get('exchanges', [])
    active = next((e for e in exs if e.get('isActive', True)), None)
    print('ACTIVE_EXCHANGE', (active or {}).get('exchangeId'))

    service = CEXService(ccxt_adapter=CcxtAdapter())
    bal = await service.fetch_balance(open_id)
    print('BALANCE_KEYS', list((bal or {}).keys()))
    print('EXCHANGE_USED', (bal or {}).get('exchangeId'))
    usdt_total = ((bal or {}).get('total') or {}).get('USDT')
    print('USDT_TOTAL', usdt_total)
    non_zero = {k: v for k, v in ((bal or {}).get('total') or {}).items() if float(v or 0) > 0}
    print('NON_ZERO_TOTAL', json.dumps(non_zero, ensure_ascii=False))

    await service.close_all()


if __name__ == '__main__':
    asyncio.run(main())
