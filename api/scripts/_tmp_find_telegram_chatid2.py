import asyncio
from api.src.adapters.driven.persistence.mongodb import db

async def main():
    # Buscar en user_configs
    uc = await db.user_configs.find_one({'openId': 'juank8911'})
    if uc:
        print('user_config (by openId):', uc.get('telegramChatId'), uc.get('telegramUserId'))
    
    # Buscar en app_configs
    ac = await db.app_configs.find_one({'openId': 'juank8911'})
    if ac:
        print('app_config (by openId):', ac.get('telegramChatId'), ac.get('telegramUserId'))
    
    # Listar todos los user_configs
    all_uc = await db.user_configs.find({}).to_list(length=10)
    print('all user_configs:', len(all_uc))
    for c in all_uc:
        print(' -', c.get('openId'), 'chatId:', c.get('telegramChatId'))

asyncio.run(main())
