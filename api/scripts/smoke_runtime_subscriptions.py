import asyncio
from api.src.application.services.bot_service import SignalBotService
from api.src.application.services.cex_service import CEXService

async def main():
    s = SignalBotService(cex_service=CEXService(), dex_service=None)
    await s.start()
    # keep alive briefly to observe WS events in logs
    await asyncio.sleep(30)
    await s.stop()

if __name__ == '__main__':
    asyncio.run(main())
