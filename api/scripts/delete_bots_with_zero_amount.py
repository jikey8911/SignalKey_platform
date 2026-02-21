import asyncio
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import db

async def main():
    bots = await db.bot_instances.find({"$or": [{"amount": {"$lte": 0}}, {"amount": None}]}).to_list(length=100000)
    bot_ids = [b.get('_id') for b in bots if b.get('_id')]
    print('bots with amount<=0:', len(bot_ids))
    if not bot_ids:
        return

    bot_id_strs = [str(x) for x in bot_ids]

    # delete related
    res_pos = await db.positions.delete_many({'botId': {'$in': bot_ids}})
    res_tr = await db.trades.delete_many({'botId': {'$in': bot_id_strs}})
    res_sig = await db.trading_signals.delete_many({'botId': {'$in': bot_ids}})
    res_fs = await db.bot_feature_states.delete_many({'botId': {'$in': bot_ids}})
    res_fh = await db.bot_feature_history.delete_many({'botId': {'$in': bot_ids}}) if 'bot_feature_history' in await db.list_collection_names() else None

    res_bot = await db.bot_instances.delete_many({'_id': {'$in': bot_ids}})

    print('deleted positions', res_pos.deleted_count)
    print('deleted trades', res_tr.deleted_count)
    print('deleted trading_signals', res_sig.deleted_count)
    print('deleted bot_feature_states', res_fs.deleted_count)
    if res_fh is not None:
        print('deleted bot_feature_history', res_fh.deleted_count)
    print('deleted bot_instances', res_bot.deleted_count)

asyncio.run(main())
