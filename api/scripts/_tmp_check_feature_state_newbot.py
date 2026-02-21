import asyncio
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import db

BOT = ObjectId('6996df60a7e644f2cb0bca57')

async def main():
    st = await db.bot_feature_states.find_one({'botId': BOT})
    print('feature_state exists:', bool(st))
    if st:
        wc = st.get('windowCandles') or []
        print('windowCandles:', len(wc))
        print('lastCandleTimestamp:', st.get('lastCandleTimestamp'))

asyncio.run(main())
