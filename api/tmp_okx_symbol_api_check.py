import asyncio
from api.src.adapters.driven.exchange.ccxt_adapter import CcxtAdapter


async def main():
    adapter = CcxtAdapter()
    try:
        px = await adapter.get_public_current_price('BTC/USDT', exchange_id='okx')
        print('OKX_API_SYMBOL_PRICE', px)
    finally:
        await adapter.close_all()


if __name__ == '__main__':
    asyncio.run(main())
