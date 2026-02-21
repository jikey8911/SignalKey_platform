import asyncio
from api.src.adapters.driven.persistence.mongodb import db

async def main():
    u = await db.users.find_one({'openId': 'juank8911'})
    if u:
        print('user _id:', u.get('_id'))
        c = await db.user_configs.find_one({'userId': u.get('_id')})
        if c:
            print('telegramChatId:', c.get('telegramChatId'))
            print('telegramUserId:', c.get('telegramUserId'))
        else:
            print('no user_config found')
    else:
        print('user not found')

asyncio.run(main())
