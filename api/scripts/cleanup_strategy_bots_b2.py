import asyncio
from bson import ObjectId
from api.src.adapters.driven.persistence.mongodb import db

async def main():
    bots = await db.bot_instances.find({}).to_list(length=100000)
    bot_ids = [b.get('_id') for b in bots if b.get('_id')]
    print('bots found', len(bot_ids))
    if not bot_ids:
        return

    # Delete related first
    res_pos = await db.positions.delete_many({'botId': {'$in': bot_ids}})
    print('positions deleted', res_pos.deleted_count)

    # trades stores botId as string in many places
    bot_id_strs = [str(x) for x in bot_ids]
    res_tr = await db.trades.delete_many({'botId': {'$in': bot_id_strs}})
    print('trades deleted', res_tr.deleted_count)

    res_sig = await db.trading_signals.delete_many({'botId': {'$in': bot_ids}})
    print('trading_signals deleted', res_sig.deleted_count)

    if 'bot_feature_states' in await db.list_collection_names():
        res_fs = await db.bot_feature_states.delete_many({'botId': {'$in': bot_ids}})
        print('bot_feature_states deleted', res_fs.deleted_count)

    if 'bot_feature_history' in await db.list_collection_names():
        res_fh = await db.bot_feature_history.delete_many({'botId': {'$in': bot_ids}})
        print('bot_feature_history deleted', res_fh.deleted_count)

    # finally bots
    res_b = await db.bot_instances.delete_many({'_id': {'$in': bot_ids}})
    print('bot_instances deleted', res_b.deleted_count)

asyncio.run(main())
