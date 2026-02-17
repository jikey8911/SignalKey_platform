import asyncio
import base64
import hmac
import json
from datetime import datetime, timezone
from hashlib import sha256

import requests

from api.src.adapters.driven.persistence.mongodb import db

BASE_URL = 'https://www.okx.com'


def iso_ts():
    # OKX expects RFC3339 with milliseconds and Z
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def sign(secret: str, prehash: str) -> str:
    digest = hmac.new(secret.encode(), prehash.encode(), sha256).digest()
    return base64.b64encode(digest).decode()


async def main():
    user = await db.users.find_one({'openId': 'juank8911'})
    if not user:
        print('USER_NOT_FOUND')
        return

    cfg = await db.app_configs.find_one({'userId': user['_id']}) or {}
    exs = cfg.get('exchanges', [])
    okx = next((e for e in exs if str(e.get('exchangeId', '')).lower() == 'okx'), None)
    if not okx:
        print('OKX_CONFIG_NOT_FOUND')
        return

    api_key = okx.get('apiKey') or ''
    api_secret = okx.get('secret') or ''
    passphrase = okx.get('password') or ''

    print('KEY_PRESENT', bool(api_key), 'SECRET_PRESENT', bool(api_secret), 'PASSPHRASE_PRESENT', bool(passphrase))

    ts = iso_ts()
    method = 'GET'
    path = '/api/v5/account/balance?ccy=USDT'
    prehash = f'{ts}{method}{path}'
    signature = sign(api_secret, prehash)

    headers = {
        'OK-ACCESS-KEY': api_key,
        'OK-ACCESS-SIGN': signature,
        'OK-ACCESS-TIMESTAMP': ts,
        'OK-ACCESS-PASSPHRASE': passphrase,
        'Content-Type': 'application/json',
    }

    resp = requests.get(f'{BASE_URL}{path}', headers=headers, timeout=20)
    print('HTTP_STATUS', resp.status_code)
    try:
        data = resp.json()
    except Exception:
        print('RAW', resp.text[:500])
        return

    # Print only safe debug info
    print('OKX_CODE', data.get('code'))
    print('OKX_MSG', data.get('msg'))
    if data.get('data'):
        details = data['data'][0].get('details', [])
        usdt = next((d for d in details if d.get('ccy') == 'USDT'), None)
        print('USDT_DETAIL', json.dumps(usdt, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
